import json
import logging
import os
from typing import Any

import joblib
import pandas as pd
import yaml
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

logger = logging.getLogger(__name__)


def load_config() -> dict:
    """Carrega as configurações do arquivo params.yaml.

    Returns:
        dict: Configurações carregadas do arquivo params.yaml
    """
    with open("params.yaml", "r") as f:
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


def load_test_data(test_path: str, features: list, target: str) -> tuple[pd.DataFrame, pd.Series]:
    """Carrega dados de teste separados.

    Args:
        test_path: Caminho para CSV de teste
        features: Lista de features
        target: Nome do target

    Returns:
        tuple: (X_test, y_test)

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
    return X_test, y_test


def evaluate(modelo: Any, X_test: pd.DataFrame, y_test: pd.Series, features: list) -> dict:
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

    metricas = {
        "r2_score": r2_score(y_test, y_predito),
        "rmse": float(mean_squared_error(y_test, y_predito) ** 0.5),
        "mse": mean_squared_error(y_test, y_predito),
        "mae": mean_absolute_error(y_test, y_predito),
        "n_amostras_teste": len(X_test),
    }

    if hasattr(modelo, "feature_importances_"):
        importancias = dict(
            zip(features, [float(v) for v in modelo.feature_importances_])
        )
        importancias_sorted = dict(
            sorted(importancias.items(), key=lambda x: x[1], reverse=True)
        )
        metricas["feature_importances"] = importancias_sorted

    logger.info(
        f"Métricas: R²={metricas['r2_score']:.4f}, "
        f"RMSE={metricas['rmse']:.4f}, MAE={metricas['mae']:.4f}"
    )

    return metricas


def save_metrics(metricas: dict, metrics_path: str) -> str:
    """Salva métricas em arquivo JSON.

    Args:
        metricas: Métricas calculadas
        metrics_path: Caminho para salvar

    Returns:
        str: Caminho onde foi salvo
    """
    os.makedirs(os.path.dirname(metrics_path), exist_ok=True)

    with open(metrics_path, "w") as f:
        json.dump(metricas, f, indent=4)
    logger.info(f"Métricas salvas em: {metrics_path}")

    return metrics_path


def main() -> None:
    """Orquestra pipeline de avaliação do modelo."""
    config = load_config()

    model_path = config["model"]["path"]
    test_path = config["data"]["processed_test_path"]
    metrics_path = config["model"]["metrics_path"].replace("train_metrics", "evaluation")
    features = config["data"]["features"]
    target = config["data"]["target"]

    modelo = load_model(model_path)
    X_test, y_test = load_test_data(test_path, features, target)
    metricas = evaluate(modelo, X_test, y_test, features)
    save_metrics(metricas, metrics_path)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
