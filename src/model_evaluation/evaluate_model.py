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
    df_eval = df_completo.iloc[y_test.index].copy()
    df_eval["y_real"] = y_test.values
    df_eval["y_pred"] = y_predito

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

        r2 = r2_score(y_test[mask], y_predito[mask])
        rmse = float(np.sqrt(mean_squared_error(y_test[mask], y_predito[mask])))
        mae = float(mean_absolute_error(y_test[mask], y_predito[mask]))

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
    X_test, y_test, df_completo = load_test_data(test_path, features, target)

    # Avaliação global
    metricas = evaluate(modelo, X_test, y_test, features)

    # Avaliação segmentada por programa
    logger.info("Avaliação por CodPrograma:")
    metricas_programa = evaluate_por_programa(modelo, X_test, y_test, df_completo)
    if metricas_programa:
        metricas["por_programa"] = metricas_programa

    # Avaliação por faixa de NS
    logger.info("Avaliação por faixa de NS_Real:")
    metricas_faixa = evaluate_por_faixa_ns(modelo, X_test, y_test)
    if metricas_faixa:
        metricas["por_faixa_ns"] = metricas_faixa

    save_metrics(metricas, metrics_path)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
