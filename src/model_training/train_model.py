import json
import logging
import os
import contextlib
from datetime import datetime
from typing import Any

import joblib
import mlflow
import numpy as np
import pandas as pd
import yaml
from sklearn.metrics import (
    mean_absolute_error, mean_squared_error, r2_score,
    accuracy_score, precision_score, recall_score, f1_score,
    confusion_matrix
)
from sklearn.model_selection import train_test_split, TimeSeriesSplit
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge

try:
    from xgboost import XGBRegressor, XGBClassifier, callback

    HAS_XGB = True
except ImportError:
    HAS_XGB = False

try:
    from src.config import get_features_for_program
    HAS_FEATURE_REGISTRY = True
except ImportError:
    HAS_FEATURE_REGISTRY = False
    pass

logger = logging.getLogger(__name__)


def calculate_sample_weights(y: pd.Series, weight_below_one: int = 10) -> np.ndarray:
    """Calcula sample weights para lidar com desbalanceamento.

    Args:
        y: Target (NS_Real)
        weight_below_one: Peso para observações onde NS < 1

    Returns:
        np.ndarray: Array de pesos
    """
    weights = np.where(y < 1, weight_below_one, 1.0)
    return weights


def train_hybrid_model(X_train, y_train, X_val, y_val, params_clf, params_reg):
    """Abordagem híbrida: Classificação + Regressão para dados desbalanceados.
    
    1. Classificador: NS=1 vs NS<1
    2. Regressor: Prediz valor absoluto para casos NS<1
    
    Args:
        X_train, y_train: Dados de treino
        X_val, y_val: Dados de validação
        params_clf: Parâmetros do classificador
        params_reg: Parâmetros do regressor
        
    Returns:
        (clf, reg, predictions)
    """
    y_clf = (y_train < 1).astype(int)
    y_clf_val = (y_val < 1).astype(int)
    
    clf = XGBClassifier(**params_clf)
    clf.fit(X_train, y_clf, verbose=False)
    
    mask_below_one = y_train < 1
    X_below = X_train[mask_below_one]
    y_below = y_train[mask_below_one]
    
    if len(X_below) < 10:
        logger.warning("Poucos dados NS<1 para treinar regressor dedicado.")
        reg = XGBRegressor(**params_reg)
        reg.fit(X_train, y_train, verbose=False)
        preds = reg.predict(X_val)
        return clf, reg, preds
    
    reg = XGBRegressor(**params_reg)
    reg.fit(X_below, y_below, verbose=False)
    
    preds = np.full(len(y_val), 1.0)
    prob_below = clf.predict_proba(X_val)[:, 1]
    
    X_below_val = X_val[y_clf_val == 1]
    if len(X_below_val) > 0:
        preds_below = reg.predict(X_below_val)
        preds[y_clf_val == 1] = preds_below
    
    return clf, reg, preds


def calculate_psi(expected: np.ndarray, actual: np.ndarray, buckets: int = 10) -> float:
    """Calcula Population Stability Index (PSI) para detecção de drift.

    PSI < 0.1: Sem drift significativo
    PSI 0.1-0.2: Drift moderado
    PSI > 0.2: Drift significativo

    Args:
        expected: Distribuição esperada (baseline)
        actual: Distribuição atual
        buckets: Número de buckets para discretização

    Returns:
        float: PSI score
    """
    try:
        bins = np.linspace(min(expected.min(), actual.min()),
                         max(expected.max(), actual.max()), buckets + 1)

        expected_bins = np.digitize(expected, bins) - 1
        expected_bins = np.clip(expected_bins, 0, buckets - 1)

        actual_bins = np.digitize(actual, bins) - 1
        actual_bins = np.clip(actual_bins, 0, buckets - 1)

        expected_pct = np.bincount(expected_bins, minlength=buckets) / len(expected)
        actual_pct = np.bincount(actual_bins, minlength=buckets) / len(actual)

        expected_pct = np.where(expected_pct == 0, 0.0001, expected_pct)
        actual_pct = np.where(actual_pct == 0, 0.0001, actual_pct)

        psi = np.sum((actual_pct - expected_pct) * np.log(actual_pct / expected_pct))
        return float(psi)
    except Exception:
        return 0.0


def detect_drift(train_data: pd.Series, test_data: pd.Series, threshold: float = 0.15) -> dict:
    """Detecta drift entre dados de treino e teste.

    Args:
        train_data: Dados de treino
        test_data: Dados de teste
        threshold: Limiar PSI para considerar drift

    Returns:
        dict: Resultados da detecção de drift
    """
    psi_target = calculate_psi(train_data.values, test_data.values)

    has_drift = psi_target > threshold

    return {
        "psi": psi_target,
        "has_drift": has_drift,
        "threshold": threshold,
        "drift_status": "DRIFT" if has_drift else "STABLE"
    }


def clipar_residuo(
    residuo_pred: np.ndarray,
    limite_correcao: float = 0.15,
) -> np.ndarray:
    """Limita a correção do resíduo ML para evitar viés excessivo.

    Impede que o modelo "exagere" na correção do Erlang, mantendo
    a predição do resíduo dentro de [-limite, +limite].
    Isso reduz o viés sistemático que causa R² negativo no teste.

    Args:
        residuo_pred: Resíduo previsto pelo modelo (NS_Real - NS_Erlang)
        limite_correcao: Limite máximo absoluto da correção em pontos
                         percentuais de NS (ex: 0.15 = ±15pp)

    Returns:
        np.ndarray: Resíduo clipado dentro do limite
    """
    residuo_arr = np.asarray(residuo_pred)
    residuo_clipado = np.clip(residuo_arr, -limite_correcao, limite_correcao)

    n_clipados = int(np.sum(np.abs(residuo_arr) > limite_correcao))
    if n_clipados > 0:
        logger.info(
            f"Threshold clipping: {n_clipados}/{len(residuo_arr)} predições "
            f"limitadas a ±{limite_correcao:.2f}"
        )

    return residuo_clipado


def calcular_metricas_ns_final(
    y_residuo_real: pd.Series,
    y_residuo_pred: np.ndarray,
    ns_erlang_base: pd.Series,
    limite_correcao: float = None,
) -> dict:
    """Calcula métricas no espaço final de negócio (NS_Final).

    NS_Final = clip(NS_Previsto_Erlang + Residuo_clipado, 0, 1)

    Args:
        y_residuo_real: Resíduo real (NS_Real - NS_Erlang)
        y_residuo_pred: Resíduo previsto pelo modelo
        ns_erlang_base: Base Erlang para reconstruir NS_Final
        limite_correcao: Se não None, aplica threshold clipping ao resíduo
    """
    ns_erlang = pd.to_numeric(ns_erlang_base, errors="coerce").fillna(0.0).clip(0.0, 1.0)
    y_residuo_real_arr = pd.Series(y_residuo_real).values
    y_residuo_pred_arr = np.asarray(y_residuo_pred)

    # Aplica threshold clipping se configurado
    if limite_correcao is not None:
        y_residuo_pred_arr = clipar_residuo(y_residuo_pred_arr, limite_correcao)

    y_real_final = np.clip(ns_erlang.values + y_residuo_real_arr, 0.0, 1.0)
    y_pred_final = np.clip(ns_erlang.values + y_residuo_pred_arr, 0.0, 1.0)
    y_baseline = ns_erlang.values

    mae_baseline = float(mean_absolute_error(y_real_final, y_baseline))
    mae_final = float(mean_absolute_error(y_real_final, y_pred_final))
    rmse_baseline = float(np.sqrt(mean_squared_error(y_real_final, y_baseline)))
    rmse_final = float(np.sqrt(mean_squared_error(y_real_final, y_pred_final)))

    uplift_mae = ((mae_baseline - mae_final) / mae_baseline * 100.0) if mae_baseline > 0 else 0.0
    uplift_rmse = ((rmse_baseline - rmse_final) / rmse_baseline * 100.0) if rmse_baseline > 0 else 0.0

    return {
        "r2_test_ns_final": float(r2_score(y_real_final, y_pred_final)),
        "rmse_test_ns_final": rmse_final,
        "mae_test_ns_final": mae_final,
        "rmse_test_erlang_baseline": rmse_baseline,
        "mae_test_erlang_baseline": mae_baseline,
        "uplift_mae_vs_erlang_pct": float(uplift_mae),
        "uplift_rmse_vs_erlang_pct": float(uplift_rmse),
        "ns_erlang_medio_test": float(np.mean(y_baseline)),
        "ns_final_medio_test": float(np.mean(y_pred_final)),
        "ns_real_medio_test": float(np.mean(y_real_final)),
        "limite_correcao_aplicado": limite_correcao,
    }


def apply_rolling_window(df: pd.DataFrame, target: str, window_days: int) -> pd.DataFrame:
    """Aplica janela móvel para usar apenas dados mais recentes.

    Args:
        df: DataFrame completo
        target: Nome da coluna target
        window_days: Número de dias para janela

    Returns:
        DataFrame filtrado pela janela móvel
    """
    if "DataHora" not in df.columns:
        logger.warning("Coluna DataHora não encontrada. Rolling window ignorado.")
        return df

    df = df.copy()
    df["DataHora"] = pd.to_datetime(df["DataHora"])
    data_max = df["DataHora"].max()
    data_min_window = data_max - pd.Timedelta(days=window_days)

    df_filtrado = df[df["DataHora"] >= data_min_window].copy()

    logger.info(
        f"Rolling window ({window_days} dias): {len(df)} -> {len(df_filtrado)} registros "
        f"(de {data_min_window.date()} a {data_max.date()})"
    )

    return df_filtrado


def load_config() -> dict:
    """Carrega as configurações do arquivo params.yaml.

    Returns:
        dict: Configurações carregadas do arquivo params.yaml
    """
    with open("params.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def carregar_dados_completos(
    caminho: str, features: list, target: str
) -> pd.DataFrame:
    """Carrega o DataFrame completo de treino/teste e valida colunas.

    Args:
        caminho: Caminho para o CSV
        features: Lista de colunas de features
        target: Nome da coluna target

    Returns:
        pd.DataFrame: DataFrame completo com todas as colunas

    Raises:
        ValueError: Se colunas estiverem faltando
    """
    logger.info(f"Carregando dados: {caminho}")
    df = pd.read_csv(caminho)

    colunas_ausentes = [col for col in features + [target] if col not in df.columns]
    if colunas_ausentes:
        raise ValueError(f"Colunas ausentes no dataset: {colunas_ausentes}")

    if "DataHora" in df.columns:
        df["DataHora"] = pd.to_datetime(df["DataHora"])
        df.sort_values(by="DataHora", inplace=True)

    logger.info(f"Dados carregados: {len(df)} registros, {len(features)} features")
    return df


def _log_diagnostico_target(y: pd.Series, programa: int = None) -> None:
    """Loga diagnóstico da distribuição do target para monitoramento.

    Args:
        y: Series com valores do target
        programa: CodPrograma para identificação no log
    """
    total = len(y)
    n_zero = (y == 0).sum()
    n_um = (y == 1).sum()
    n_entre = ((y > 0) & (y < 1)).sum()

    prefixo = f"Programa {programa} - " if programa else ""
    logger.info(
        f"{prefixo}Distribuição NS_Real: "
        f"total={total}, "
        f"==0: {n_zero} ({n_zero/total*100:.1f}%), "
        f"==1: {n_um} ({n_um/total*100:.1f}%), "
        f"entre: {n_entre} ({n_entre/total*100:.1f}%)"
    )

    # Alertas de qualidade
    if n_zero / total > 0.30:
        logger.warning(
            f"{prefixo}ALERTA: {n_zero/total*100:.0f}% dos registros têm NS_Real=0."
        )

    if total < 100:
        logger.warning(
            f"{prefixo}ALERTA: Apenas {total} registros de treino."
        )


def treinar_modelo_programa(
    X_treino: pd.DataFrame,
    y_treino: pd.Series,
    config_modelo: dict,
    programa: int,
    target: str,
    val_size: float = 0.1,
    features: list = None,
    use_cv: bool = True,
    n_splits: int = 5,
) -> tuple[Any, pd.DataFrame, pd.Series, pd.DataFrame, pd.Series, dict]:
    """Treina o modelo XGBoost para um programa específico.

    Cada programa recebe seu próprio modelo, permitindo que cada operação
    tenha hiperparâmetros e padrões independentes.

    Args:
        X_treino: Features de treino (apenas deste programa)
        y_treino: Target de treino (apenas deste programa)
        config_modelo: Configurações do modelo do params.yaml
        programa: CodPrograma do programa sendo treinado
        val_size: Proporção para validação interna (early stopping)
        features: Lista de features para log de importância
        use_cv: Se True, usa TimeSeriesSplit cross-validation
        n_splits: Número de folds para CV

    Returns:
        tuple: (modelo, X_train, y_train, X_val, y_val, metricas_val)
    """
    import mlflow
    
    # mlflow.set_experiment("ml_regression")
    # mlflow.xgboost.autolog()

    with mlflow.start_run(run_name=f"programa_{programa}") as run:
        # Log de parâmetros no MLflow
        params = config_modelo.get("params", {}).copy()
        params.pop("early_stopping_rounds", None)
        mlflow.log_params(params)
        mlflow.log_param("programa", programa)
        mlflow.log_param("val_size", val_size)
        mlflow.log_param("model_type", config_modelo.get("type", "XGBRegressor"))
        mlflow.log_param("n_registros_treino", len(X_treino))
        mlflow.log_param("use_cv", use_cv)
        mlflow.log_param("n_splits", n_splits if use_cv else 1)

        tipo_modelo = config_modelo.get("type", "XGBRegressor")
        parametros = config_modelo.get("params", {}).copy()
        early_stopping_rounds = parametros.pop("early_stopping_rounds", 15)

        if "n_jobs" in parametros:
            parametros["n_jobs"] = int(parametros["n_jobs"])

        weight_below_one = parametros.pop("sample_weight_below_one", 10)

        use_hybrid = config_modelo.get("use_hybrid", False)

        target_transformation = config_modelo.get("target_transformation", False)
        optimize_hyperparameters = config_modelo.get("optimize_hyperparameters", False)
        
        if target_transformation and target != "NS_Residuo":
            mlflow.log_param("target_transformation", "log1p(1.0-y)")
        if optimize_hyperparameters:
            mlflow.log_param("optimize_hyperparameters", True)
            mlflow.log_param("optuna_n_trials", config_modelo.get("optuna_n_trials", 20))

        logger.info(f"Programa {programa} - Algoritmo: {tipo_modelo}")

        if tipo_modelo == "XGBRegressor" and HAS_XGB:
            if use_cv and len(X_treino) >= n_splits * 10:
                # Cross-validation com TimeSeriesSplit
                tscv = TimeSeriesSplit(n_splits=n_splits)
                cv_scores = []
                cv_predictions = []

                X_treino_arr = X_treino.values
                y_treino_arr = y_treino.values
                
                # Aplica transformação no target se configurado
                if target_transformation and target != "NS_Residuo":
                    logger.info(f"Programa {programa} - Aplicando Transformação do Target log1p(1.0 - y)")
                    y_treino_arr = np.log1p(1.0 - y_treino_arr)

                # Optuna Otimização de Hiperparâmetros
                if optimize_hyperparameters:
                    logger.info(f"Programa {programa} - Otimizando hiperparâmetros com Optuna")
                    import optuna
                    
                    def objective(trial):
                        param_trial = {
                            "n_estimators": trial.suggest_int("n_estimators", 50, 300),
                            "max_depth": trial.suggest_int("max_depth", 3, 7),
                            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
                            "min_child_weight": trial.suggest_int("min_child_weight", 1, 20),
                            "alpha": trial.suggest_float("alpha", 0.0, 30.0),
                            "reg_lambda": trial.suggest_float("reg_lambda", 0.0, 30.0),
                            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
                            "subsample": trial.suggest_float("subsample", 0.5, 1.0),
                            "random_state": 42,
                            "n_jobs": -1
                        }
                        
                        tscv_opt = TimeSeriesSplit(n_splits=3)
                        cv_scores_opt = []
                        
                        for train_idx_opt, val_idx_opt in tscv_opt.split(X_treino_arr):
                            X_tr_opt = X_treino_arr[train_idx_opt]
                            y_tr_opt = y_treino_arr[train_idx_opt]
                            X_va_opt = X_treino_arr[val_idx_opt]
                            y_va_opt = y_treino_arr[val_idx_opt]
                            
                            model_opt = XGBRegressor(**param_trial)
                            model_opt.fit(X_tr_opt, y_tr_opt, eval_set=[(X_va_opt, y_va_opt)], verbose=False)
                            
                            preds_opt_trans = model_opt.predict(X_va_opt)
                            if target_transformation and target != "NS_Residuo":
                                preds_opt = 1.0 - np.expm1(preds_opt_trans)
                                y_va_orig = 1.0 - np.expm1(y_va_opt)
                            else:
                                preds_opt = preds_opt_trans
                                y_va_orig = y_va_opt
                                
                            cv_scores_opt.append(mean_absolute_error(y_va_orig, preds_opt))
                            
                        return np.mean(cv_scores_opt)

                    optuna.logging.set_verbosity(optuna.logging.WARNING)
                    study = optuna.create_study(direction="minimize")
                    study.optimize(objective, n_trials=config_modelo.get("optuna_n_trials", 20))
                    
                    logger.info(f"Programa {programa} - Melhores parâmetros Optuna: {study.best_params}")
                    parametros.update(study.best_params)
                    mlflow.log_params({"optuna_" + k: v for k, v in study.best_params.items()})

                for fold, (train_idx, val_idx) in enumerate(tscv.split(X_treino_arr)):
                    X_train_fold = X_treino_arr[train_idx]
                    y_train_fold = y_treino_arr[train_idx]
                    X_val_fold = X_treino_arr[val_idx]
                    y_val_fold = y_treino_arr[val_idx]

                    fold_model = XGBRegressor(**parametros)
                    fold_model.fit(
                        X_train_fold, y_train_fold,
                        eval_set=[(X_val_fold, y_val_fold)],
                        verbose=False,
                    )

                    y_pred_trans = fold_model.predict(X_val_fold)
                    
                    if target_transformation and target != "NS_Residuo":
                        y_pred = 1.0 - np.expm1(y_pred_trans)
                        y_val_fold_orig = 1.0 - np.expm1(y_val_fold)
                    else:
                        y_pred = y_pred_trans
                        y_val_fold_orig = y_val_fold
                        
                    fold_r2 = r2_score(y_val_fold_orig, y_pred)
                    cv_scores.append(fold_r2)
                    cv_predictions.extend(y_pred)

                    logger.info(
                        f"Programa {programa} - Fold {fold+1}/{n_splits}: "
                        f"R2={fold_r2:.4f} (train={len(train_idx)}, val={len(val_idx)})"
                    )

                mean_cv_r2 = np.mean(cv_scores)
                std_cv_r2 = np.std(cv_scores)
                logger.info(
                    f"Programa {programa} - CV Results: R2 mean={mean_cv_r2:.4f} "
                    f"(+/-{std_cv_r2:.4f})"
                )
                mlflow.log_metrics({
                    "cv_r2_mean": mean_cv_r2,
                    "cv_r2_std": std_cv_r2,
                })

                # Treina modelo final com todos os dados
                logger.info(
                    f"Programa {programa} - Treinando modelo final com todos os dados"
                )
                modelo = XGBRegressor(**parametros)
                modelo.fit(X_treino_arr, y_treino_arr, verbose=False)

                # Usa última fold para validação
                X_train, X_val, y_train, y_val = (
                    X_treino.iloc[train_idx],
                    X_treino.iloc[val_idx],
                    y_treino.iloc[train_idx],
                    y_treino.iloc[val_idx],
                )

            else:
                # Split simples (sem CV)
                X_train, X_val, y_train, y_val = train_test_split(
                    X_treino, y_treino, test_size=val_size, shuffle=False
                )
                logger.info(
                    f"Programa {programa} - Split interno: "
                    f"treino={len(X_train)}, validação={len(X_val)}"
                )

                y_train_arr = y_train.values
                y_val_arr = y_val.values
                if target_transformation and target != "NS_Residuo":
                    y_train_arr = np.log1p(1.0 - y_train_arr)
                    y_val_arr = np.log1p(1.0 - y_val_arr)

                modelo = XGBRegressor(**parametros)
                modelo.fit(X_train, y_train_arr)
        else:
            raise ValueError(f"Tipo de modelo {tipo_modelo} não suportado.")

        # Métricas de validação interna
        predicoes_train_trans = modelo.predict(X_train)
        predicoes_val_trans = modelo.predict(X_val)
        
        if target_transformation and target != "NS_Residuo":
            predicoes_train = 1.0 - np.expm1(predicoes_train_trans)
            predicoes_val = 1.0 - np.expm1(predicoes_val_trans)
        else:
            predicoes_train = predicoes_train_trans
            predicoes_val = predicoes_val_trans

        if target == "NS_Residuo":
            pred_train_eval = predicoes_train
            pred_val_eval = predicoes_val
        else:
            pred_train_eval = np.clip(predicoes_train, 0.0, 1.0)
            pred_val_eval = np.clip(predicoes_val, 0.0, 1.0)

        r2_train = r2_score(y_train, pred_train_eval)
        r2_val = r2_score(y_val, pred_val_eval)
        mae_train = float(mean_absolute_error(y_train, pred_train_eval))
        rmse_train = float(np.sqrt(mean_squared_error(y_train, pred_train_eval)))

        mse_val = float(mean_squared_error(y_val, pred_val_eval))
        rmse_val = float(np.sqrt(mse_val))
        mae_val = float(mean_absolute_error(y_val, pred_val_eval))

        if target == "NS_Residuo":
            metricas_val = {
                "r2_train_residuo": r2_train,
                "mae_train_residuo": mae_train,
                "rmse_train_residuo": rmse_train,
                "r2_val_residuo": r2_val,
                "mse_val_residuo": mse_val,
                "rmse_val_residuo": rmse_val,
                "mae_val_residuo": mae_val,
            }
        else:
            metricas_val = {
                "r2_train": r2_train,
                "mae_train": mae_train,
                "rmse_train": rmse_train,
                "r2_val": r2_val,
                "mse_val": mse_val,
                "rmse_val": rmse_val,
                "mae_val": mae_val,
            }
        mlflow.log_metrics(metricas_val)

        # Log de importância das features
        if hasattr(modelo, "feature_importances_") and features:
            importancias = dict(
                zip(features, [float(v) for v in modelo.feature_importances_])
            )
            mlflow.log_dict(importancias, "feature_importances.json")

            top_features = sorted(
                importancias.items(), key=lambda x: x[1], reverse=True
            )[:5]
            logger.info(f"Programa {programa} - Top 5 features:")
            for nome, imp in top_features:
                logger.info(f"  {nome}: {imp:.4f}")

        logger.info(
            f"Programa {programa} - Validação: "
            f"R²(treino)={r2_train:.4f}, R²(val)={r2_val:.4f}, "
            f"RMSE={rmse_val:.4f}, MAE={mae_val:.4f}"
        )

        # Gravação manual do modelo no MLflow para substituir o autolog
        if tipo_modelo == "XGBRegressor":
            import mlflow.xgboost
            mlflow.xgboost.log_model(modelo, artifact_path="model")
        else:
            import mlflow.sklearn
            mlflow.sklearn.log_model(modelo, artifact_path="model")

        return modelo, X_train, y_train, X_val, y_val, metricas_val


def treinar_ensemble(
    X_treino: pd.DataFrame,
    y_treino: pd.Series,
    config_modelo: dict,
    programa: int,
) -> tuple[dict, list]:
    """Treina ensemble de modelos com diferentes algoritmos.

    Args:
        X_treino: Features de treino
        y_treino: Target de treino
        config_modelo: Configurações do modelo
        programa: CodPrograma

    Returns:
        tuple: (dicionário de modelos, lista de nomes)
    """
    params = config_modelo.get("params", {}).copy()
    ensemble_models = config_modelo.get("ensemble_models", ["XGBRegressor"])
    weights = config_modelo.get("ensemble_weights", [0.5])

    modelos = {}
    nomes = []

    xgb_params = {k: v for k, v in params.items() if k not in ["objective", "tree_method"]}
    xgb_params["objective"] = params.get("objective", "reg:absoluteerror")
    xgb_params["tree_method"] = params.get("tree_method", "hist")

    for model_type in ensemble_models:
        if model_type == "XGBRegressor" and HAS_XGB:
            modelos[model_type] = XGBRegressor(**xgb_params)
            modelos[model_type].fit(X_treino, y_treino)
            nomes.append(model_type)
            logger.info(f"Programa {programa} - {model_type} treinado")

        elif model_type == "RandomForest":
            rf_params = {
                "n_estimators": int(params.get("n_estimators", 100) * 0.5),
                "max_depth": min(int(params.get("max_depth", 4) + 2), 10),
                "min_samples_leaf": params.get("min_child_weight", 15),
                "random_state": params.get("random_state", 42),
                "n_jobs": int(params.get("n_jobs", -1)),
            }
            modelos[model_type] = RandomForestRegressor(**rf_params)
            modelos[model_type].fit(X_treino, y_treino)
            nomes.append(model_type)
            logger.info(f"Programa {programa} - {model_type} treinado")

        elif model_type == "Ridge":
            from sklearn.preprocessing import StandardScaler

            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(X_treino)

            ridge_params = {
                "alpha": params.get("reg_lambda", 10),
                "random_state": params.get("random_state", 42),
            }
            modelos[model_type] = Ridge(**ridge_params)
            modelos[model_type].fit(X_scaled, y_treino)
            modelos[f"{model_type}_scaler"] = scaler
            nomes.append(model_type)
            logger.info(f"Programa {programa} - {model_type} treinado")

    logger.info(
        f"Programa {programa} - Ensemble: {nomes} com pesos {weights[:len(nomes)]}"
    )

    return modelos, nomes


def predict_ensemble(
    modelos: dict,
    nomes: list,
    X: pd.DataFrame,
    weights: list,
) -> np.ndarray:
    """Faz predição com ensemble de modelos.

    Args:
        modelos: Dicionário de modelos treinados
        nomes: Lista de nomes dos modelos
        X: Features para predição
        weights:Lista de pesos para cada modelo

    Returns:
        np.ndarray: Predição ponderada
    """
    predictions = []
    total_weight = sum(weights[:len(nomes)])

    for nome in nomes:
        if nome == "Ridge":
            scaler = modelos.get(f"{nome}_scaler")
            if scaler:
                X_scaled = scaler.transform(X)
            else:
                X_scaled = X
        else:
            X_scaled = X

        pred = modelos[nome].predict(X_scaled)
        predictions.append(pred)

    weighted_pred = np.zeros_like(predictions[0])
    for i, pred in enumerate(predictions):
        weight = weights[i] if i < len(weights) else weights[-1]
        weighted_pred += (weight / total_weight) * pred

    return weighted_pred


def avaliar_modelo_teste(
    modelo: Any,
    X_treino: pd.DataFrame,
    X_teste: pd.DataFrame,
    y_treino: pd.Series,
    y_teste: pd.Series,
    df_teste: pd.DataFrame,
    features: list,
    programa: int,
    target: str,
    limite_correcao: float = None,
    target_transformation: bool = False,
) -> dict:
    """Avalia o modelo no conjunto de teste para um programa específico.

    Args:
        modelo: Modelo treinado
        X_treino: Features de treino
        X_teste: Features de teste
        y_treino: Target de treino
        y_teste: Target de teste
        features: Lista de features
        programa: CodPrograma para identificação no log
        target_transformation: Se True, aplica a inversa da transformação log1p

    Returns:
        dict: Métricas do modelo no conjunto de teste
    """
    predicoes_train_trans = modelo.predict(X_treino)
    predicoes_test_trans = modelo.predict(X_teste)

    if target_transformation and target != "NS_Residuo":
        predicoes_train = 1.0 - np.expm1(predicoes_train_trans)
        predicoes_test = 1.0 - np.expm1(predicoes_test_trans)
    else:
        predicoes_train = predicoes_train_trans
        predicoes_test = predicoes_test_trans

    if target == "NS_Residuo":
        pred_train_eval = predicoes_train
        pred_test_eval = predicoes_test
    else:
        pred_train_eval = np.clip(predicoes_train, 0.0, 1.0)
        pred_test_eval = np.clip(predicoes_test, 0.0, 1.0)

    score_r2_train = r2_score(y_treino, pred_train_eval)
    mae_train = float(mean_absolute_error(y_treino, pred_train_eval))
    rmse_train = float(np.sqrt(mean_squared_error(y_treino, pred_train_eval)))

    score_r2_test = r2_score(y_teste, pred_test_eval)
    rmse_test = float(np.sqrt(mean_squared_error(y_teste, pred_test_eval)))
    mae_test = float(mean_absolute_error(y_teste, pred_test_eval))

    logger.info(
        f"Programa {programa} - TESTE: "
        f"R²={score_r2_test:.4f}, RMSE={rmse_test:.4f}, "
        f"MAE={mae_test:.4f}"
    )

    importancias = {}
    if hasattr(modelo, "feature_importances_"):
        importancias = dict(
            zip(features, [float(v) for v in modelo.feature_importances_])
        )

    if target == "NS_Residuo":
        metricas = {
            "target": target,
            "target_metric_space": "residuo",
            "r2_train_residuo": score_r2_train,
            "mae_train_residuo": mae_train,
            "rmse_train_residuo": rmse_train,
            "r2_test_residuo": score_r2_test,
            "rmse_test_residuo": rmse_test,
            "mae_test_residuo": mae_test,
            "feature_importances": importancias,
        }

        if "NS_Previsto_Erlang" in df_teste.columns:
            metricas_ns_final = calcular_metricas_ns_final(
                y_residuo_real=y_teste,
                y_residuo_pred=predicoes_test,
                ns_erlang_base=df_teste["NS_Previsto_Erlang"],
                limite_correcao=limite_correcao,
            )
            metricas.update(metricas_ns_final)

            logger.info(
                f"Programa {programa} - NS_FINAL: "
                f"R²={metricas_ns_final['r2_test_ns_final']:.4f}, "
                f"RMSE={metricas_ns_final['rmse_test_ns_final']:.4f}, "
                f"MAE={metricas_ns_final['mae_test_ns_final']:.4f}, "
                f"Uplift_MAE_vs_Erlang={metricas_ns_final['uplift_mae_vs_erlang_pct']:.2f}%"
            )
    else:
        metricas = {
            "target": target,
            "target_metric_space": "ns_direto",
            "r2_train": score_r2_train,
            "mae_train": mae_train,
            "rmse_train": rmse_train,
            "r2_test": score_r2_test,
            "rmse_test": rmse_test,
            "mae_test": mae_test,
            "feature_importances": importancias,
        }

        if "NS_Previsto_Erlang" in df_teste.columns:
            ns_erlang = pd.to_numeric(df_teste["NS_Previsto_Erlang"], errors="coerce").fillna(0.0)
            ns_erlang = ns_erlang.clip(0.0, 1.0)
            mae_baseline = float(mean_absolute_error(y_teste, ns_erlang))
            rmse_baseline = float(np.sqrt(mean_squared_error(y_teste, ns_erlang)))
            uplift_mae = ((mae_baseline - mae_test) / mae_baseline * 100.0) if mae_baseline > 0 else 0.0
            uplift_rmse = ((rmse_baseline - rmse_test) / rmse_baseline * 100.0) if rmse_baseline > 0 else 0.0
            metricas.update(
                {
                    "mae_erlang_baseline": mae_baseline,
                    "rmse_erlang_baseline": rmse_baseline,
                    "uplift_mae_vs_erlang_pct": float(uplift_mae),
                    "uplift_rmse_vs_erlang_pct": float(uplift_rmse),
                }
            )

    return metricas


def salvar_modelo_programa(
    modelo: Any,
    metricas: dict,
    programa: int,
    tipo_utilizado: str,
    duracao: float,
    n_treino: int,
    diretorio_modelos: str = "models",
    diretorio_metricas: str = "metrics",
) -> tuple[str, str]:
    """Salva modelo e métricas de um programa específico em disco.

    Convenção de nomes:
        - Modelo: models/model_{CodPrograma}.pkl
        - Métricas: metrics/train_metrics_{CodPrograma}.json

    Args:
        modelo: Modelo treinado
        metricas: Métricas calculadas
        programa: CodPrograma
        tipo_utilizado: Nome do algoritmo usado
        duracao: Tempo de treinamento em segundos
        n_treino: Número de amostras de treino
        diretorio_modelos: Diretório dos modelos
        diretorio_metricas: Diretório das métricas

    Returns:
        tuple: (caminho_modelo, caminho_metricas)
    """
    os.makedirs(diretorio_modelos, exist_ok=True)
    os.makedirs(diretorio_metricas, exist_ok=True)

    caminho_modelo = os.path.join(diretorio_modelos, f"model_{programa}.pkl")
    caminho_metricas = os.path.join(
        diretorio_metricas, f"train_metrics_{programa}.json"
    )

    joblib.dump(modelo, caminho_modelo)
    logger.info(f"Programa {programa} - Modelo salvo: {caminho_modelo}")

    metricas_completas = {
        "programa": programa,
        "algoritmo": tipo_utilizado,
        "duracao_treino_segundos": duracao,
        "linhas_treino": n_treino,
        **metricas,
    }

    with open(caminho_metricas, "w", encoding="utf-8") as f:
        json.dump(metricas_completas, f, indent=4, default=str)
    logger.info(f"Programa {programa} - Métricas salvas: {caminho_metricas}")

    return caminho_modelo, caminho_metricas


def main() -> None:
    """Orquestra pipeline de treinamento por programa.

    Para cada programa em params.yaml -> data.programas:
        1. Filtra dados de treino/teste do programa
        2. Valida se há dados operacionais suficientes
        3. Treina modelo XGBoost dedicado
        4. Avalia no conjunto de teste
        5. Salva modelo e métricas com sufixo do programa
    """
    import mlflow
    mlflow.set_tracking_uri("file:./mlruns")
    mlflow.set_experiment("smartcorr_model_training")
    
    config = load_config()

    train_path = config["data"]["processed_train_path"]
    test_path = config["data"]["processed_test_path"]
    features_global = config["data"]["features"]
    target = config["data"]["target"]
    programas = config["data"]["programas"]
    use_feature_registry = config["data"].get("use_feature_registry", False)
    diretorio_modelos = config["model"].get("models_dir", "models")
    diretorio_metricas = config["model"].get("metrics_dir", "metrics")
    min_registros = config["model"].get("min_registros_operacionais", 50)
    tipo_utilizado = config["model"].get("type", "XGBRegressor")
    limite_correcao = config["model"].get("limite_correcao_residuo", None)
    if target != "NS_Residuo":
        limite_correcao = None
    elif limite_correcao is not None:
        logger.info(
            f"Threshold clipping ATIVADO: correção limitada a "
            f"±{limite_correcao:.2f} pontos de NS"
        )

    logger.info("Carregando dados de treino e teste...")
    df_treino_completo = carregar_dados_completos(train_path, features_global, target)

    df_teste_completo = None
    if os.path.exists(test_path):
        df_teste_completo = pd.read_csv(test_path)
        if "DataHora" in df_teste_completo.columns:
            df_teste_completo["DataHora"] = pd.to_datetime(
                df_teste_completo["DataHora"]
            )
        logger.info(f"Dados de teste carregados: {len(df_teste_completo)} registros")

    resumo_programas = []

    for programa in programas:
        logger.info(f"\n{'='*60}")
        logger.info(f"PROGRAMA {programa} — INICIANDO TREINAMENTO")
        logger.info(f"{'='*60}")

        if use_feature_registry and HAS_FEATURE_REGISTRY:
            features = get_features_for_program(programa, features_global)
            logger.info(f"Programa {programa}: usando {len(features)} features do registry")
        else:
            features = features_global

        df_treino_prog = df_treino_completo[
            df_treino_completo["CodPrograma"] == programa
        ].copy()

        rolling_window_days = config["model"].get("rolling_window_days")
        use_rolling_window = config["model"].get("use_rolling_window", False)

        if use_rolling_window and rolling_window_days:
            df_treino_prog = apply_rolling_window(
                df_treino_prog, target, rolling_window_days
            )

        if df_treino_prog.empty:
            logger.warning(f"Programa {programa}: sem dados de treino. Pulando.")
            resumo_programas.append({
                "programa": programa, "status": "sem_dados",
            })
            continue

        # Verifica registros operacionais usando NS_Real quando disponível.
        coluna_operacional = "NS_Real" if "NS_Real" in df_treino_prog.columns else target
        registros_operacionais = int((df_treino_prog[coluna_operacional] > 0).sum())
        total_registros = len(df_treino_prog)

        if registros_operacionais == 0:
            logger.warning(
                f"Programa {programa}: 0% de registros operacionais "
                f"(todos {coluna_operacional}=0). Programa inativo no período. Pulando."
            )
            resumo_programas.append({
                "programa": programa,
                "status": "inativo",
                "n_total": total_registros,
            })
            continue

        if registros_operacionais < min_registros:
            logger.warning(
                f"Programa {programa}: apenas {registros_operacionais} registros "
                f"operacionais (mínimo: {min_registros}). Pulando."
            )
            resumo_programas.append({
                "programa": programa,
                "status": "dados_insuficientes",
                "n_operacionais": registros_operacionais,
            })
            continue

        X_treino = df_treino_prog[features]
        y_treino = df_treino_prog[target]

        # Diagnóstico do target
        _log_diagnostico_target(y_treino, programa)

        # Treina modelo específico para este programa
        inicio = datetime.now()
        use_cv = config["model"].get("use_cv", True)
        n_splits = config["model"].get("cv_n_splits", 5)
        modelo, X_tr, y_tr, X_val, y_val, metricas_val = treinar_modelo_programa(
            X_treino, y_treino, config["model"],
            programa=programa, val_size=0.2, features=features,
            target=target,
            use_cv=use_cv, n_splits=n_splits,
        )
        duracao = (datetime.now() - inicio).total_seconds()

        # Detecção de drift
        enable_drift = config["model"].get("enable_drift_detection", False)
        drift_result = {}
        if enable_drift and X_val is not None and len(X_val) > 10:
            drift_result = detect_drift(
                y_tr, y_val, config["model"].get("drift_threshold", 0.15)
            )
            logger.info(
                f"Programa {programa} - Drift: PSI={drift_result.get('psi', 0):.4f} "
                f"({drift_result.get('drift_status', 'N/A')})"
            )

        # Ensemble (se configurado)
        use_ensemble = config["model"].get("use_ensemble", False)
        ensemble_models = None
        ensemble_nomes = None
        if use_ensemble:
            ensemble_models, ensemble_nomes = treinar_ensemble(
                X_tr, y_tr, config["model"], programa
            )

        # Avalia no conjunto de teste (se disponível para este programa)
        metricas_teste = {}
        if df_teste_completo is not None:
            df_teste_prog = df_teste_completo[
                df_teste_completo["CodPrograma"] == programa
            ].copy()

            coluna_teste_operacional = "NS_Real" if "NS_Real" in df_teste_prog.columns else target
            n_teste_operacionais = (
                int((df_teste_prog[coluna_teste_operacional] > 0).sum())
                if not df_teste_prog.empty else 0
            )

            if not df_teste_prog.empty and n_teste_operacionais > 0:
                X_teste = df_teste_prog[features]
                y_teste = df_teste_prog[target]

                if use_ensemble and ensemble_models:
                    weights = config["model"].get("ensemble_weights", [0.5, 0.3, 0.2])
                    y_pred_ensemble = predict_ensemble(
                        ensemble_models, ensemble_nomes, X_teste, weights
                    )

                    metricas_teste = {
                        "r2_train": r2_score(y_tr, modelo.predict(X_tr)),
                        "r2_test": r2_score(y_teste, y_pred_ensemble),
                        "rmse_test": float(np.sqrt(mean_squared_error(y_teste, y_pred_ensemble))),
                        "mae_test": float(mean_absolute_error(y_teste, y_pred_ensemble)),
                    }
                    logger.info(
                        f"Programa {programa} - ENSEMBLE: R2={metricas_teste['r2_test']:.4f}, "
                        f"RMSE={metricas_teste['rmse_test']:.4f}, MAE={metricas_teste['mae_test']:.4f}"
                    )
                else:
                    metricas_teste = avaliar_modelo_teste(
                        modelo, X_tr, X_teste, y_tr, y_teste,
                        df_teste_prog, features, programa, target,
                        limite_correcao=limite_correcao,
                        target_transformation=config["model"].get("target_transformation", False),
                    )
            else:
                logger.info(
                    f"Programa {programa}: sem dados de teste operacionais. "
                    f"Avaliação de teste ignorada."
                )

        # Salva modelo e métricas no disco
        metricas_completas = {
            "target": target,
            "target_metric_space": "residuo" if target == "NS_Residuo" else "ns_direto",
            **metricas_val,
            **metricas_teste,
        }
        salvar_modelo_programa(
            modelo, metricas_completas, programa, tipo_utilizado,
            duracao, len(X_treino), diretorio_modelos, diretorio_metricas,
        )

        resumo_programas.append({
            "programa": programa,
            "status": "treinado",
            "n_treino": len(X_treino),
            "n_operacionais": registros_operacionais,
            "r2_val": metricas_val.get("r2_val") if target != "NS_Residuo" else metricas_val.get("r2_val_residuo"),
            "mae_val": metricas_val.get("mae_val") if target != "NS_Residuo" else metricas_val.get("mae_val_residuo"),
            "r2_test": metricas_teste.get("r2_test") if target != "NS_Residuo" else metricas_teste.get("r2_test_residuo"),
            "mae_test": metricas_teste.get("mae_test") if target != "NS_Residuo" else metricas_teste.get("mae_test_residuo"),
            "duracao": duracao,
        })

    # ─── Resumo Final ────────────────────────────────────────────
    logger.info(f"\n{'='*60}")
    logger.info("RESUMO DO TREINAMENTO POR PROGRAMA")
    logger.info(f"{'='*60}")

    treinados = 0
    pulados = 0

    for r in resumo_programas:
        if r["status"] == "treinado":
            r2_val = r.get("r2_val")
            mae_val = r.get("mae_val")
            r2 = r.get("r2_test")
            mae = r.get("mae_test")
            r2_val_str = f"{r2_val:.4f}" if r2_val is not None else "N/A"
            mae_val_str = f"{mae_val:.4f}" if mae_val is not None else "N/A"
            r2_str = f"{r2:.4f}" if r2 is not None else "N/A"
            mae_str = f"{mae:.4f}" if mae is not None else "N/A"
            logger.info(
                f"  * {r['programa']}: {r['n_treino']} regs "
                f"({r['n_operacionais']} operac.), "
                f"R²_val={r2_val_str}, MAE_val={mae_val_str}, "
                f"R²_teste={r2_str}, MAE_teste={mae_str}, "
                f"tempo={r['duracao']:.1f}s"
            )
            treinados += 1
        else:
            logger.info(f"  > {r['programa']}: {r['status']}")
            pulados += 1

    logger.info(
        f"\nTotal: {treinados} modelos treinados, {pulados} programas pulados"
    )

    # Salva resumo geral (compatível com DVC metrics)
    resumo_path = os.path.join(diretorio_metricas, "train_metrics.json")
    os.makedirs(diretorio_metricas, exist_ok=True)
    with open(resumo_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "total_modelos_treinados": treinados,
                "total_programas_pulados": pulados,
                "detalhes": resumo_programas,
            },
            f,
            indent=4,
            default=str,
        )
    logger.info(f"Resumo geral salvo em: {resumo_path}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
    main()
