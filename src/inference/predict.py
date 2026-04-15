import logging
import os
from typing import Any

import joblib
import numpy as np
import pandas as pd
import shap
import yaml

from src.database import get_connection

logger = logging.getLogger(__name__)

PILARES: dict[str, list[str]] = {
    "Volumetria": [
        "Vol_Previsto",
        "Taxa_Abandono_Lag_1",
        "Desvio_Volume_Pct_Lag_1",
    ],
    "Pessoas": [
        "HC_Previsto",
        "ABS_Taxa_Daily",
        "Turnover_Taxa_Daily",
        "Ferias_Qtd_Daily",
        "Faltas_Qtd_Daily",
        "WAHA_Qtd_Daily",
        "PerdaLog_Taxa_Daily",
        "TechIssues_Taxa_Daily",
        "NewHire_Pct_Daily",
        "AgentIssues_Taxa_Daily",
    ],
    "TMA": [
        "Tempo_AHT_Previsto_Total",
        "TME_Real_Avg_Lag_1",
        "Delta_TMA_Lag_1",
    ],
    "Causas_Raiz": [
        "Pressao_Prevista_Vol_HC",
        "Indicador_Sufoco",
        "Vol_Por_Agente",
        "Margem_Capacidade",
        "Desvio_Escala_Pct",
        "Razao_Escala",
        "Taxa_Sobrecarga",
    ],
    "Contexto_Temporal": [
        "Hora",
        "DiaSemana",
    ],
}


def load_config() -> dict:
    """Carrega as configurações do arquivo params.yaml.

    Returns:
        dict: Configurações carregadas
    """
    with open("params.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_pilar(feature_name: str) -> str:
    """Retorna o pilar analítico ao qual uma feature pertence.

    Args:
        feature_name: Nome da feature

    Returns:
        str: Nome do pilar ou 'Geral' se não encontrada
    """
    for pilar, variaveis in PILARES.items():
        if feature_name in variaveis:
            return pilar
    return "Geral"

def calcular_explicabilidade_shap(
    modelo: Any, X: pd.DataFrame
) -> np.ndarray:
    """Gera os valores SHAP para explicabilidade do modelo.

    Args:
        modelo: Modelo treinado (XGBoost)
        X: DataFrame com features

    Returns:
        np.ndarray: Valores SHAP para cada sample e feature
    """
    explainer = shap.TreeExplainer(modelo)
    shap_values = explainer.shap_values(X)
    return shap_values


def processar_previsoes(
    df: pd.DataFrame,
    predicoes: np.ndarray,
    shap_values: np.ndarray,
    features: list[str],
) -> list[tuple]:
    """Transforma predições em tuplas para gravação no banco.

    Args:
        df: DataFrame com dados originais
        predicoes: Array de predições do modelo
        shap_values: Array de valores SHAP
        features: Lista de nomes das features

    Returns:
        list[tuple]: Tuplas formatadas para insert no banco
    """
    resultados: list[tuple] = []

    if "DataRef" not in df.columns:
        df["DataRef"] = df["DataHora"].astype(str).str[:10]
    if "Intervalo" not in df.columns:
        df["Intervalo"] = df["DataHora"].astype(str).str[11:19]

    for i in range(len(df)):
        linha = df.iloc[i]
        valores_shap = shap_values[i]

        impacto_volumetria = 0.0
        impacto_pessoas = 0.0
        impacto_tma = 0.0
        impacto_causas = 0.0
        impacto_contexto = 0.0

        feature_impactos: list[dict[str, Any]] = []

        for j, feature in enumerate(features):
            impacto = float(valores_shap[j])
            pilar = get_pilar(feature)

            if pilar == "Volumetria":
                impacto_volumetria += impacto
            elif pilar == "Pessoas":
                impacto_pessoas += impacto
            elif pilar == "TMA":
                impacto_tma += impacto
            elif pilar == "Causas_Raiz":
                impacto_causas += impacto
            elif pilar == "Contexto_Temporal":
                impacto_contexto += impacto

            feature_impactos.append({"nome": feature, "pilar": pilar, "impacto": impacto})

        feature_impactos.sort(key=lambda x: x["impacto"])

        ofensores = feature_impactos[:3]
        impulsionadores = feature_impactos[-3:]
        impulsionadores.reverse()

        ofensores = [o if o["impacto"] < -0.001 else None for o in ofensores]
        impulsionadores = [i if i["impacto"] > 0.001 else None for i in impulsionadores]

        ns_previsto = min(max(float(predicoes[i]), 0.0), 1.0)

        def_nome = "Sem Impacto Relevante"
        def_pilar = "N/A"
        def_val = 0.000

        resultados.append(
            (
                linha["DataRef"],
                linha["Intervalo"],
                int(linha["CodPrograma"]),
                int(linha.get("Canal", 7)),
                ns_previsto,
                int(linha.get("Vol_Previsto", 0)),
                int(linha.get("HC_Previsto", 0)),
                float(linha.get("TMA_Previsto_Avg", 0.0)),
                float(linha.get("NS_Lag_1", 0.0)),
                float(linha.get("TME_Real_Avg_Lag_1", 0.0)),
                float(linha.get("Desvio_Volume_Pct_Lag_1", 0.0)),
                impacto_volumetria,
                impacto_pessoas,
                impacto_tma,
                impacto_contexto,
                ofensores[0]["nome"] if ofensores[0] else def_nome,
                ofensores[0]["pilar"] if ofensores[0] else def_pilar,
                ofensores[0]["impacto"] if ofensores[0] else def_val,
                ofensores[1]["nome"] if ofensores[1] else def_nome,
                ofensores[1]["pilar"] if ofensores[1] else def_pilar,
                ofensores[1]["impacto"] if ofensores[1] else def_val,
                ofensores[2]["nome"] if ofensores[2] else def_nome,
                ofensores[2]["pilar"] if ofensores[2] else def_pilar,
                ofensores[2]["impacto"] if ofensores[2] else def_val,
                impulsionadores[0]["nome"] if impulsionadores[0] else def_nome,
                impulsionadores[0]["pilar"] if impulsionadores[0] else def_pilar,
                impulsionadores[0]["impacto"] if impulsionadores[0] else def_val,
                impulsionadores[1]["nome"] if impulsionadores[1] else def_nome,
                impulsionadores[1]["pilar"] if impulsionadores[1] else def_pilar,
                impulsionadores[1]["impacto"] if impulsionadores[1] else def_val,
                impulsionadores[2]["nome"] if impulsionadores[2] else def_nome,
                impulsionadores[2]["pilar"] if impulsionadores[2] else def_pilar,
                impulsionadores[2]["impacto"] if impulsionadores[2] else def_val,
            )
        )

    return resultados

def salvar_no_banco(tuplas_dados: list[tuple]) -> None:
    """Salva tuplas de predição no banco de dados SQL Server.

    Args:
        tuplas_dados: Lista de tuplas com dados de predição

    Raises:
        Exception: Se ocorrer erro na transação
    """
    conn = get_connection()
    cursor = conn.cursor()

    query = """
    INSERT INTO [OdsCorp].[SmartCorr].[FactSmartCorr_Previsao]
    ([DataRef], [Intervalo], [CodPrograma], [Canal], [NS_Previsto_SmartCorr],
     [Vol_Previsto], [HC_Previsto], [TMA_Previsto_Avg], [NS_Lag_1],
     [TME_Real_Lag_1], [Desvio_Volume_Pct_Lag_1],
     [Impacto_Pilar_Volumetria], [Impacto_Pilar_Pessoas], [Impacto_Pilar_TMA], [Impacto_Pilar_Contexto],
     [Ofensor_1_Nome], [Ofensor_1_Pilar], [Ofensor_1_Impacto],
     [Ofensor_2_Nome], [Ofensor_2_Pilar], [Ofensor_2_Impacto],
     [Ofensor_3_Nome], [Ofensor_3_Pilar], [Ofensor_3_Impacto],
     [Impulsionador_1_Nome], [Impulsionador_1_Pilar], [Impulsionador_1_Impacto],
     [Impulsionador_2_Nome], [Impulsionador_2_Pilar], [Impulsionador_2_Impacto],
     [Impulsionador_3_Nome], [Impulsionador_3_Pilar], [Impulsionador_3_Impacto])
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    try:
        if tuplas_dados:
            df_tuplas = pd.DataFrame(tuplas_dados)
            agrupado = df_tuplas.groupby(0)[1].min().reset_index()

            logger.info("Limpando previsões antigas (Rolling Forecast) no BD...")
            for _, row in agrupado.iterrows():
                dt_ref = str(row[0])
                min_int = str(row[1])
                query_del = f"""DELETE FROM [OdsCorp].[SmartCorr].[FactSmartCorr_Previsao]
                                WHERE [DataRef] = '{dt_ref}' AND [Intervalo] >= '{min_int}'"""
                cursor.execute(query_del)
                logger.info(f"Limpo Data={dt_ref} >= Intervalo {min_int}")

            logger.info(
                f"Gravando {len(tuplas_dados)} registros SHAP. "
                "(fast_executemany=True)"
            )
            cursor.fast_executemany = True
            cursor.executemany(query, tuplas_dados)
            conn.commit()
            logger.info("Transação no Banco efetuada com sucesso!")
    except Exception as e:
        conn.rollback()
        logger.error(f"Erro ao salvar Fato no SQL Server: {e}")
        raise
    finally:
        conn.close()


def main() -> None:
    """Orquestra pipeline de inferência do modelo."""
    config = load_config()
    caminho_modelo = config["model"]["path"]
    caminho_futuro = config["data"]["processed_future_path"]
    features = config["data"]["features"]

    if not os.path.exists(caminho_futuro):
        logger.warning(f"Arquivo {caminho_futuro} ausente. Fim da rotina.")
        return

    logger.info("1. Carregando modelo Preditivo Treinado (XGBoost)...")
    modelo = joblib.load(caminho_modelo)

    logger.info("2. Lendo dados Futuros da Gestão...")
    df_futuro = pd.read_csv(caminho_futuro)

    if df_futuro.empty:
        logger.warning("Base do Futuro vazia. Nenhum intervalo projetado hoje.")
        return

    X = df_futuro[features]

    logger.info("3. Predição do Nível de Serviço...")
    predicoes = modelo.predict(X)

    logger.info("4. SHAP Values para Explicabilidade...")
    shap_values = calcular_explicabilidade_shap(modelo, X)

    logger.info("5. Processando impactos por pilar...")
    tuplas_finais = processar_previsoes(df_futuro, predicoes, shap_values, features)

    salvar_no_banco(tuplas_finais)

    logger.info("Pipeline Finalizado!")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
    main()
