import json
import logging
import os
from datetime import datetime
from typing import Any

import joblib
import mlflow
import numpy as np
import pandas as pd
import yaml
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split

try:
    from xgboost import XGBRegressor, callback

    HAS_XGB = True
except ImportError:
    HAS_XGB = False

logger = logging.getLogger(__name__)


def load_config() -> dict:
    """Carrega as configurações do arquivo params.yaml.

    Returns:
        dict: Configurações carregadas do arquivo params.yaml
    """
    with open("params.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_data(train_path: str, features: list, target: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Carrega dados de treino e valida colunas.

    Args:
        train_path: Caminho para o CSV de treino
        features: Lista de colunas de features
        target: Nome da coluna target

    Returns:
        tuple: (X, y) DataFrames

    Raises:
        ValueError: Se colunas estiverem faltando
    """
    logger.info(f"Carregando dados de treino: {train_path}")
    df = pd.read_csv(train_path)

    colunas_ausentes = [col for col in features + [target] if col not in df.columns]
    if colunas_ausentes:
        raise ValueError(f"Colunas ausentes no dataset de treino: {colunas_ausentes}")

    if "DataHora" in df.columns:
        df["DataHora"] = pd.to_datetime(df["DataHora"])
        df.sort_values(by="DataHora", inplace=True)

    X = df[features]
    y = df[target]

    logger.info(f"Dados carregados: {len(X)} registros, {len(features)} features")
    return X, y


def _log_diagnostico_target(y: pd.Series) -> None:
    """Loga diagnóstico da distribuição do target para monitoramento.

    Args:
        y: Series com valores do target
    """
    total = len(y)
    n_zero = (y == 0).sum()
    n_um = (y == 1).sum()
    n_entre = ((y > 0) & (y < 1)).sum()

    logger.info(
        f"Distribuição NS_Real no treino: "
        f"total={total}, "
        f"==0: {n_zero} ({n_zero/total*100:.1f}%), "
        f"==1: {n_um} ({n_um/total*100:.1f}%), "
        f"entre: {n_entre} ({n_entre/total*100:.1f}%)"
    )

    # Alertas de qualidade
    if n_zero / total > 0.30:
        logger.warning(
            f"ALERTA: {n_zero/total*100:.0f}% dos registros têm NS_Real=0. "
            "Verifique se o filtro operacional está ativo em params.yaml. "
            "Intervalos sem operação real distorcem o modelo."
        )

    if total < 1000:
        logger.warning(
            f"ALERTA: Apenas {total} registros de treino. "
            "Considere aumentar janela_dias em params.yaml."
        )


def prepare_data(
    X: pd.DataFrame,
    y: pd.Series,
    test_size: float = 0.2,
    random_state: int = 42,
) -> tuple[pd.DataFrame, pd.Series]:
    """Prepara dados para treino (sem split - teste já está separado).

    Args:
        X: DataFrame de features
        y: Series do target
        test_size: Proporção (mantido para compatibilidade, não usado)
        random_state: Seed para reprodutibilidade

    Returns:
        tuple: (X_train, y_train)
    """
    logger.info(f"Treino: {len(X)} linhas.")
    return X, y


def train(
    X: pd.DataFrame,
    y: pd.Series,
    config_modelo: dict,
    val_size: float = 0.1,
    features: list = None,
) -> tuple[Any, pd.DataFrame, pd.Series, pd.DataFrame, pd.Series]:
    """Treina o modelo (XGBoost ou Random Forest).

    Args:
        X: Features de treino
        y: Target de treino
        config_modelo: Configurações do modelo do params.yaml
        val_size: Proporção para validação interna (default: 0.1)

    Returns:
        tuple: (modelo, X_train, y_train, X_val, y_val)
    """

    # Set up MLflow experiment
    mlflow.set_experiment("ml_regression")

    # Set up XGBoost autolog
    mlflow.xgboost.autolog()

    # aqui inicializo o context manager do mlflow
    with mlflow.start_run() as run:
        # Log parameters to MLflow (removendo early_stopping_rounds que é tratado internamente)
        params = config_modelo.get("params", {}).copy()
        params.pop("early_stopping_rounds", None)
        mlflow.log_params(params)
        mlflow.log_param("val_size", val_size)
        mlflow.log_param("model_type", config_modelo.get("type", "XGBRegressor"))

        tipo_modelo = config_modelo.get("type", "RandomForestRegressor")
        parametros = config_modelo.get("params", {}).copy()
        early_stopping_rounds = parametros.pop("early_stopping_rounds", 15)

        if "n_jobs" in parametros:
            parametros["n_jobs"] = int(parametros["n_jobs"])

        logger.info(f"Iniciando treinamento com algoritmo: {tipo_modelo}")
        logger.info(f"Parâmetros: {parametros}")

        if tipo_modelo == "XGBRegressor" and HAS_XGB:
            X_train, X_val, y_train, y_val = train_test_split(
                X, y, test_size=val_size, shuffle=False
            )
            logger.info(
                f"Split interno para EarlyStopping: treino={len(X_train)}, "
                f"validação={len(X_val)}"
            )

            if early_stopping_rounds > 0:
                modelo = XGBRegressor(
                    **parametros,
                    callbacks=[callback.EarlyStopping(early_stopping_rounds)],
                )
                logger.info(f"EarlyStopping ativo: {early_stopping_rounds} rounds")
                modelo.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)
            else:
                modelo = XGBRegressor(**parametros)
                modelo.fit(X_train, y_train)

        elif tipo_modelo == "RandomForestRegressor":
            X_train, X_val, y_train, y_val = X, X, y, y
            modelo = RandomForestRegressor(**parametros)
            modelo.fit(X_train, y_train)
        else:
            raise ValueError(f"Tipo de modelo {tipo_modelo} não suportado.")

        predicoes_train = modelo.predict(X_train)
        predicoes_val = modelo.predict(X_val)

        r2_train = r2_score(y_train, predicoes_train)
        r2_val = r2_score(y_val, predicoes_val)
        mse_val = float(mean_squared_error(y_val, predicoes_val))
        rmse_val = float(np.sqrt(mse_val))
        mae_val = float(mean_absolute_error(y_val, predicoes_val))

        metrics = {
            "r2_train": r2_train,
            "r2_val": r2_val,
            "mse_val": mse_val,
            "rmse_val": rmse_val,
            "mae_val": mae_val,
        }
        mlflow.log_metrics(metrics)

        if hasattr(modelo, "feature_importances_"):
            importancias = dict(zip(features, [float(v) for v in modelo.feature_importances_]))
            mlflow.log_dict(importancias, "feature_importances.json")

            # Log top 10 features
            top_features = sorted(importancias.items(), key=lambda x: x[1], reverse=True)[:10]
            logger.info("Top 10 features por importância:")
            for nome, imp in top_features:
                logger.info(f"  {nome}: {imp:.4f}")

        logger.info(f"R² (Treino): {r2_train:.4f}")
        logger.info(f"R² (Validação): {r2_val:.4f}")
        logger.info(f"RMSE (Validação): {rmse_val:.4f}")
        logger.info(f"MAE (Validação): {mae_val:.4f}")

        return modelo, X_train, y_train, X_val, y_val


def evaluate(
    modelo: Any,
    X_train: pd.DataFrame,
    X_test: pd.DataFrame,
    y_train: pd.Series,
    y_test: pd.Series,
    features: list,
) -> dict:
    """Avalia o modelo e calcula métricas.

    Args:
        modelo: Modelo treinado
        X_train: Features de treino
        X_test: Features de teste
        y_train: Target de treino
        y_test: Target de teste
        features: Lista de features

    Returns:
        dict: Métricas do modelo
    """
    predicoes_train = modelo.predict(X_train)
    predicoes_test = modelo.predict(X_test)

    score_r2_train = r2_score(y_train, predicoes_train)
    score_r2_test = r2_score(y_test, predicoes_test)
    rmse_test = np.sqrt(mean_squared_error(y_test, predicoes_test))
    mae_test = mean_absolute_error(y_test, predicoes_test)

    logger.info(f"R² (Treino): {score_r2_train:.4f}")
    logger.info(f"R² (Teste): {score_r2_test:.4f}")
    logger.info(f"RMSE: {rmse_test:.4f}")
    logger.info(f"MAE: {mae_test:.4f} pontos percentuais de NS")

    if hasattr(modelo, "feature_importances_"):
        importancias = dict(
            zip(features, [float(v) for v in modelo.feature_importances_])
        )
    else:
        importancias = {}

    return {
        "r2_train": score_r2_train,
        "r2_test": score_r2_test,
        "rmse_test": rmse_test,
        "mae_test": mae_test,
        "feature_importances": importancias,
    }


def save_model(
    modelo: Any,
    metricas: dict,
    tipo_utilizado: str,
    duracao: float,
    n_train: int,
    model_path: str,
    metrics_path: str,
) -> tuple[str, str]:
    """Salva modelo e métricas em disco.

    Args:
        modelo: Modelo treinado
        metricas: Métricas calculadas
        tipo_utilizado: Nome do algoritmo usado
        duracao: Tempo de treinamento em segundos
        n_train: Número de amostras de treino
        model_path: Caminho para salvar modelo
        metrics_path: Caminho para salvar métricas

    Returns:
        tuple: (model_path, metrics_path)
    """
    os.makedirs(os.path.dirname(model_path), exist_ok=True)
    os.makedirs(os.path.dirname(metrics_path), exist_ok=True)

    joblib.dump(modelo, model_path)
    logger.info(f"Modelo salvo em: {model_path}")

    metricas_completas = {
        "algoritmo": tipo_utilizado,
        "duracao_treino_segundos": duracao,
        "linhas_treino": n_train,
        **metricas,
    }

    with open(metrics_path, "w") as f:
        json.dump(metricas_completas, f, indent=4)
    logger.info(f"Métricas salvas em: {metrics_path}")

    return model_path, metrics_path


def main() -> None:
    """Orquestra pipeline de treinamento do modelo."""
    config = load_config()

    train_path = config["data"]["processed_train_path"]
    model_path = config["model"]["path"]
    metrics_path = config["model"]["metrics_path"]
    features = config["data"]["features"]
    target = config["data"]["target"]

    X, y = load_data(train_path, features, target)

    # Diagnóstico do target para monitoramento contínuo
    _log_diagnostico_target(y)

    start_time = datetime.now()
    modelo, X_train, y_train, X_val, y_val = train(X, y, config["model"], val_size=0.1, features=features)
    duracao = (datetime.now() - start_time).total_seconds()

    tipo_utilizado = config["model"].get("type", "XGBRegressor")

    # Métricas já foram calculadas e logadas no MLflow dentro da função train()
    metricas = {"duracao_treino_segundos": duracao}

    experiment = mlflow.get_experiment_by_name("ml_regression")
    runs = mlflow.search_runs(
        experiment_ids=[experiment.experiment_id], order_by=["start_time DESC"], max_results=1
    )
    run_id = runs.iloc[0].run_id

    with mlflow.start_run(run_id=run_id):
        mlflow.log_param("train_data_path", train_path)
        mlflow.log_param("n_features", len(features))
        mlflow.log_param("n_train_samples", len(X_train))

    logger.info(f"MLflow Run ID: {run_id}")
    logger.info(f"MLflow Experiment: {experiment.name}")

    save_model(
        modelo,
        metricas,
        tipo_utilizado,
        duracao,
        len(X_train),
        model_path,
        metrics_path,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
