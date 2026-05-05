import json
import logging
import os
from typing import Any

import joblib
import numpy as np
import pandas as pd
import yaml
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

logger = logging.getLogger(__name__)


def load_config() -> dict:
    """Carrega as configurações do arquivo params.yaml.

    Returns:
        dict: Configurações carregadas do arquivo params.yaml
    """
    with open("params.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_model(model_path: str) -> Any:
    """Carrega modelo treinado do disco.

    Args:
        model_path: Caminho para o arquivo .pkl

    Returns:
        Modelo carregado

    Raises:
        FileNotFoundError: Se modelo não existir
    """
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Modelo não encontrado: {model_path}")

    logger.info(f"Carregando modelo de: {model_path}")
    return joblib.load(model_path)


def load_test_data(test_path: str, features: list, target: str) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame]:
    """Carrega dados de teste separados.

    Retorna o DataFrame completo junto com X e y para permitir
    análise por segmentos (CodPrograma, faixas de NS, etc.)

    Args:
        test_path: Caminho para CSV de teste
        features: Lista de features
        target: Nome do target

    Returns:
        tuple: (X_test, y_test, df_completo)

    Raises:
        FileNotFoundError: Se arquivo não existir
        ValueError: Se colunas estiverem faltando
    """
    if not os.path.exists(test_path):
        raise FileNotFoundError(
            f"Dados de teste não encontrados: {test_path}. "
            "Execute feature_engineering primeiro."
        )

    logger.info(f"Carregando dados de teste de: {test_path}")
    df = pd.read_csv(test_path)

    colunas_faltantes = [col for col in features + [target] if col not in df.columns]
    if colunas_faltantes:
        raise ValueError(f"Colunas ausentes: {colunas_faltantes}")

    X_test = df[features]
    y_test = df[target]

    logger.info(f"Dados de teste: {len(X_test)} amostras")
    return X_test, y_test, df


def evaluate(
    modelo: Any,
    X_test: pd.DataFrame,
    y_test: pd.Series,
    features: list,
    df_test: pd.DataFrame,
    target: str,
) -> dict:
    """Avalia modelo no dataset de teste.

    Args:
        modelo: Modelo treinado
        X_test: Features de teste
        y_test: Target de teste
        features: Lista de features para importâncias

    Returns:
        dict: Métricas de avaliação
    """
    y_predito = modelo.predict(X_test)
    metricas = {"n_amostras_teste": len(X_test)}

    if target == "NS_Residuo" and "NS_Previsto_Erlang" in df_test.columns:
        ns_erlang = pd.to_numeric(df_test["NS_Previsto_Erlang"], errors="coerce").fillna(0.0)
        ns_erlang = ns_erlang.clip(0.0, 1.0)

        y_real_res = y_test.values
        y_pred_res = y_predito

        metricas.update({
            "target": target,
            "target_metric_space": "residuo",
            "r2_score_residuo": float(r2_score(y_real_res, y_pred_res)),
            "rmse_residuo": float(np.sqrt(mean_squared_error(y_real_res, y_pred_res))),
            "mse_residuo": float(mean_squared_error(y_real_res, y_pred_res)),
            "mae_residuo": float(mean_absolute_error(y_real_res, y_pred_res)),
        })

        y_real_final = np.clip(ns_erlang.values + y_real_res, 0.0, 1.0)
        y_pred_final = np.clip(ns_erlang.values + y_pred_res, 0.0, 1.0)
        y_baseline = ns_erlang.values

        mae_baseline = float(mean_absolute_error(y_real_final, y_baseline))
        rmse_baseline = float(np.sqrt(mean_squared_error(y_real_final, y_baseline)))
        mae_final = float(mean_absolute_error(y_real_final, y_pred_final))
        rmse_final = float(np.sqrt(mean_squared_error(y_real_final, y_pred_final)))

        uplift_mae = ((mae_baseline - mae_final) / mae_baseline * 100.0) if mae_baseline > 0 else 0.0
        uplift_rmse = ((rmse_baseline - rmse_final) / rmse_baseline * 100.0) if rmse_baseline > 0 else 0.0

        metricas.update({
            "r2_score_ns_final": float(r2_score(y_real_final, y_pred_final)),
            "rmse_ns_final": rmse_final,
            "mse_ns_final": float(mean_squared_error(y_real_final, y_pred_final)),
            "mae_ns_final": mae_final,
            "rmse_erlang_baseline": rmse_baseline,
            "mae_erlang_baseline": mae_baseline,
            "uplift_mae_vs_erlang_pct": float(uplift_mae),
            "uplift_rmse_vs_erlang_pct": float(uplift_rmse),
        })

        logger.info(
            f"Métricas Resíduo: R²={metricas['r2_score_residuo']:.4f}, "
            f"RMSE={metricas['rmse_residuo']:.4f}, MAE={metricas['mae_residuo']:.4f}"
        )
        logger.info(
            f"Métricas NS_Final: R²={metricas['r2_score_ns_final']:.4f}, "
            f"RMSE={metricas['rmse_ns_final']:.4f}, MAE={metricas['mae_ns_final']:.4f}, "
            f"Uplift_MAE={metricas['uplift_mae_vs_erlang_pct']:.2f}%"
        )
    else:
        y_predito_capped = np.clip(y_predito, 0, 1)
        metricas.update({
            "target": target,
            "target_metric_space": "ns_direto",
            "r2_score": float(r2_score(y_test, y_predito_capped)),
            "rmse": float(mean_squared_error(y_test, y_predito_capped) ** 0.5),
            "mse": float(mean_squared_error(y_test, y_predito_capped)),
            "mae": float(mean_absolute_error(y_test, y_predito_capped)),
        })

        if "NS_Previsto_Erlang" in df_test.columns:
            ns_erlang = pd.to_numeric(df_test["NS_Previsto_Erlang"], errors="coerce").fillna(0.0)
            ns_erlang = ns_erlang.clip(0.0, 1.0)
            mae_baseline = float(mean_absolute_error(y_test, ns_erlang))
            rmse_baseline = float(mean_squared_error(y_test, ns_erlang) ** 0.5)
            uplift_mae = ((mae_baseline - metricas["mae"]) / mae_baseline * 100.0) if mae_baseline > 0 else 0.0
            uplift_rmse = ((rmse_baseline - metricas["rmse"]) / rmse_baseline * 100.0) if rmse_baseline > 0 else 0.0
            metricas.update(
                {
                    "mae_erlang_baseline": mae_baseline,
                    "rmse_erlang_baseline": rmse_baseline,
                    "uplift_mae_vs_erlang_pct": float(uplift_mae),
                    "uplift_rmse_vs_erlang_pct": float(uplift_rmse),
                }
            )

    if hasattr(modelo, "feature_importances_"):
        importancias = dict(
            zip(features, [float(v) for v in modelo.feature_importances_])
        )
        importancias_sorted = dict(
            sorted(importancias.items(), key=lambda x: x[1], reverse=True)
        )
        metricas["feature_importances"] = importancias_sorted
        metricas["feature_importances_context"] = (
            "impacto_na_predicao_do_residuo"
            if target == "NS_Residuo"
            else "impacto_na_predicao_direta_do_ns"
        )

    if target != "NS_Residuo":
        logger.info(
            f"Métricas Globais: R²={metricas['r2_score']:.4f}, "
            f"RMSE={metricas['rmse']:.4f}, MAE={metricas['mae']:.4f}"
        )

    return metricas


def evaluate_por_programa(
    modelo: Any,
    X_test: pd.DataFrame,
    y_test: pd.Series,
    df_completo: pd.DataFrame,
) -> dict:
    """Avalia modelo segmentado por CodPrograma.

    Identifica programas com performance abaixo da média para
    ação corretiva (retrain, mais dados, features específicas).

    Args:
        modelo: Modelo treinado
        X_test: Features de teste
        y_test: Target de teste
        df_completo: DataFrame com CodPrograma e demais colunas

    Returns:
        dict: Métricas por programa
    """
    if "CodPrograma" not in df_completo.columns:
        logger.warning("CodPrograma não encontrado. Pulando avaliação segmentada.")
        return {}

    y_predito = modelo.predict(X_test)
    y_predito_capped = np.clip(y_predito, 0, 1)
    df_eval = df_completo.iloc[y_test.index].copy()
    df_eval["y_real"] = y_test.values
    df_eval["y_pred"] = y_predito_capped

    metricas_por_programa = {}

    for programa, grupo in df_eval.groupby("CodPrograma"):
        if len(grupo) < 10:
            logger.warning(f"Programa {programa}: apenas {len(grupo)} amostras (mínimo: 10)")
            continue

        r2 = r2_score(grupo["y_real"], grupo["y_pred"])
        rmse = float(np.sqrt(mean_squared_error(grupo["y_real"], grupo["y_pred"])))
        mae = float(mean_absolute_error(grupo["y_real"], grupo["y_pred"]))
        ns_medio_real = grupo["y_real"].mean()

        metricas_por_programa[str(programa)] = {
            "r2_score": round(r2, 4),
            "rmse": round(rmse, 4),
            "mae": round(mae, 4),
            "n_amostras": len(grupo),
            "ns_medio_real": round(ns_medio_real, 3),
        }

        status = "✅" if r2 > 0.3 else "⚠️" if r2 > 0 else "❌"
        logger.info(
            f"  {status} Programa {programa}: R²={r2:.4f}, "
            f"RMSE={rmse:.4f}, MAE={mae:.4f}, "
            f"NS_médio={ns_medio_real:.3f}, n={len(grupo)}"
        )

    return metricas_por_programa


def evaluate_por_faixa_ns(
    modelo: Any,
    X_test: pd.DataFrame,
    y_test: pd.Series,
) -> dict:
    """Avalia modelo segmentado por faixa de NS_Real.

    Mostra onde o modelo erra mais: nos NS baixos, médios ou altos.

    Args:
        modelo: Modelo treinado
        X_test: Features de teste
        y_test: Target de teste

    Returns:
        dict: Métricas por faixa de NS
    """
    y_predito = modelo.predict(X_test)
    y_predito_capped = np.clip(y_predito, 0, 1)

    faixas = {
        "ns_0_30": (0.0, 0.3),
        "ns_30_60": (0.3, 0.6),
        "ns_60_80": (0.6, 0.8),
        "ns_80_100": (0.8, 1.01),
    }

    metricas_por_faixa = {}

    for nome_faixa, (inf_val, sup_val) in faixas.items():
        mask = (y_test >= inf_val) & (y_test < sup_val)
        n_amostras = mask.sum()

        if n_amostras < 10:
            logger.info(f"  Faixa {nome_faixa}: {n_amostras} amostras (insuficiente)")
            continue

        r2 = r2_score(y_test[mask], y_predito_capped[mask])
        rmse = float(np.sqrt(mean_squared_error(y_test[mask], y_predito_capped[mask])))
        mae = float(mean_absolute_error(y_test[mask], y_predito_capped[mask]))

        metricas_por_faixa[nome_faixa] = {
            "r2_score": round(r2, 4),
            "rmse": round(rmse, 4),
            "mae": round(mae, 4),
            "n_amostras": int(n_amostras),
        }

        logger.info(
            f"  Faixa NS [{inf_val:.0%}-{sup_val:.0%}): R²={r2:.4f}, "
            f"RMSE={rmse:.4f}, MAE={mae:.4f}, n={n_amostras}"
        )

    return metricas_por_faixa


def save_metrics(metricas: dict, metrics_path: str) -> str:
    """Salva métricas em arquivo JSON.

    Args:
        metricas: Métricas calculadas
        metrics_path: Caminho para salvar

    Returns:
        str: Caminho onde foi salvo
    """
    os.makedirs(os.path.dirname(metrics_path), exist_ok=True)

    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(metricas, f, indent=4)
    logger.info(f"Métricas salvas em: {metrics_path}")

    return metrics_path


def main() -> None:
    """Orquestra pipeline de avaliação do modelo."""
    config = load_config()

    models_dir = config["model"].get("models_dir", "models")
    test_path = config["data"]["processed_test_path"]
    metrics_path = config["model"]["metrics_path"].replace("train_metrics", "evaluation")
    features_global = config["data"]["features"]
    target = config["data"]["target"]
    programas = config["data"]["programas"]
    use_feature_registry = config["data"].get("use_feature_registry", False)

    try:
        from src.config import get_features_for_program
        HAS_FEATURE_REGISTRY = True
    except ImportError:
        HAS_FEATURE_REGISTRY = False

    X_test, y_test, df_completo = load_test_data(test_path, features_global, target)

    metricas_global = {}

    for programa in programas:
        model_path = os.path.join(models_dir, f"model_{programa}.pkl")

        if not os.path.exists(model_path):
            logger.warning(f"Modelo não encontrado: {model_path}. Pulando.")
            continue

        logger.info(f"Avaliando modelo do programa {programa}...")

        modelo = load_model(model_path)

        if use_feature_registry and HAS_FEATURE_REGISTRY:
            features = get_features_for_program(programa, features_global)
        else:
            features = features_global

        df_prog = df_completo[df_completo["CodPrograma"] == programa]
        if df_prog.empty:
            logger.warning(f"Programa {programa}: sem dados de teste. Pulando.")
            continue

        features_missing = set(features) - set(df_prog.columns)
        for f in features_missing:
            df_prog[f] = 0.0

        X_prog = df_prog[features]
        y_prog = df_prog[target]

        metricas_prog = evaluate(modelo, X_prog, y_prog, features, df_prog, target)
        metricas_global[f"programa_{programa}"] = metricas_prog

        if target == "NS_Residuo":
            r2_val = metricas_prog.get("r2_score_ns_final")
            mae_val = metricas_prog.get("mae_ns_final")
        else:
            r2_val = metricas_prog.get("r2_score")
            mae_val = metricas_prog.get("mae")
        
        r2_str = f"{r2_val:.4f}" if isinstance(r2_val, (int, float)) else str(r2_val)
        mae_str = f"{mae_val:.4f}" if isinstance(mae_val, (int, float)) else str(mae_val)

        logger.info(
            f"Programa {programa}: R2={r2_str}, "
            f"MAE={mae_str}"
        )

    save_metrics(metricas_global, metrics_path)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
