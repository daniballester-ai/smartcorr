import logging
import os
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd
import yaml
from sklearn.model_selection import train_test_split

logger = logging.getLogger(__name__)


def load_config() -> dict:
    """Carrega as configurações do arquivo params.yaml.

    Returns:
        dict: Configurações carregadas do arquivo params.yaml
    """
    with open("params.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _ensure_datetime(df: pd.DataFrame) -> pd.DataFrame:
    """Garante que DataHora seja do tipo datetime.

    Args:
        df: DataFrame com coluna DataHora

    Returns:
        pd.DataFrame: DataFrame com DataHora convertido
    """
    if not pd.api.types.is_datetime64_any_dtype(df["DataHora"]):
        df["DataHora"] = pd.to_datetime(df["DataHora"])
    return df


def _create_delta_features(df: pd.DataFrame) -> pd.DataFrame:
    """Cria features de delta (diferença entre real e previsto).

    Args:
        df: DataFrame com colunas de volume e HC

    Returns:
        pd.DataFrame: DataFrame com features de delta
    """
    df["Delta_Volume"] = df["Vol_Real"] - df["Vol_Previsto"]
    df["Delta_HC"] = df["HC_Real_Equiv"] - df["HC_Previsto"]

    df["TMA_Real_Avg"] = np.where(
        df["Vol_Atendidas"] > 0,
        df["Tempo_AHT_Real_Total"] / df["Vol_Atendidas"],
        0.0,
    )
    df["TMA_Previsto_Avg"] = np.where(
        df["Vol_Previsto"] > 0,
        df["Tempo_AHT_Previsto_Total"] / df["Vol_Previsto"],
        0.0,
    )
    df["Delta_TMA"] = df["TMA_Real_Avg"] - df["TMA_Previsto_Avg"]

    return df


def _create_synthetic_features(df: pd.DataFrame) -> pd.DataFrame:
    """Cria features sintéticas combinando variáveis.

    Features de PRESSÃO DE DEMANDA (causas raiz):
    - Vol_Por_Agente: Volume por agente (pressão de demanda)
    - Margem_Capacidade: Folga para absorver variação

    Features de ESCALA (causas raiz):
    - Desvio_Escala_Pct: Desvio de HC real vs previsto
    - Razao_Escala: Proporção real vs prevista
    - Taxa_Sobrecarga: Overload real dos agentes

    Args:
        df: DataFrame com colunas de volume e HC

    Returns:
        pd.DataFrame: DataFrame com features sintéticas
    """
    df["Pressao_Prevista_Vol_HC"] = np.where(
        df["HC_Previsto"] > 0,
        df["Vol_Previsto"] / df["HC_Previsto"],
        0.0,
    )
    df["Indicador_Sufoco"] = np.where(
        df["HC_Previsto"] > 0,
        df["Tempo_AHT_Previsto_Total"] / (df["HC_Previsto"] * 1800),
        0.0,
    )

    df["Vol_Por_Agente"] = np.where(
        df["HC_Previsto"] > 0,
        df["Vol_Previsto"] / df["HC_Previsto"],
        0.0,
    )

    capacidade_teorica = df["HC_Previsto"] * 1800
    df["Margem_Capacidade"] = np.where(
        capacidade_teorica > 0,
        (capacidade_teorica - df["Vol_Previsto"]) / capacidade_teorica,
        0.0,
    )

    df["Desvio_Escala_Pct"] = np.where(
        df["HC_Previsto"] > 0,
        (df["HC_Real_Equiv"] - df["HC_Previsto"]) / df["HC_Previsto"],
        0.0,
    )

    df["Razao_Escala"] = np.where(
        df["HC_Previsto"] > 0,
        df["HC_Real_Equiv"] / df["HC_Previsto"],
        0.0,
    )

    df["Taxa_Sobrecarga"] = np.where(
        df["HC_Real_Equiv"] > 0,
        df["Vol_Real"] / (df["HC_Real_Equiv"] * 1800),
        0.0,
    )

    return df


def _create_rate_features(df: pd.DataFrame) -> pd.DataFrame:
    """Cria features de taxas (proporções).

    Args:
        df: DataFrame com colunas de ABS, Turnover e volumes

    Returns:
        pd.DataFrame: DataFrame com features de taxa
    """
    df["ABS_Taxa_Daily"] = np.where(
        df["ABS_Escala_Sec_Daily"] > 0,
        df["ABS_Tempo_Sec_Daily"] / df["ABS_Escala_Sec_Daily"],
        0.0,
    )
    df["Turnover_Taxa_Daily"] = np.where(
        df["Turnover_Ativos_Daily"] > 0,
        df["Turnover_Desligados_Daily"] / df["Turnover_Ativos_Daily"],
        0.0,
    )
    df["Taxa_Abandono"] = np.where(
        df["Vol_Real"] > 0,
        df["Vol_Abandono"] / df["Vol_Real"],
        0.0,
    )

    df["TME_Real_Avg"] = np.where(
        df["Vol_Real"] > 0,
        df["Tempo_Espera_Total"] / df["Vol_Real"],
        0.0,
    )

    tempo_logado_total = df["HC_Real_Equiv"] * 1800
    df["Taxa_Ocupacao"] = np.where(
        tempo_logado_total > 0,
        df["Tempo_AHT_Real_Total"] / tempo_logado_total,
        0.0,
    )

    df["Taxa_Pausa_Tecnica"] = np.where(
        tempo_logado_total > 0,
        df["Pausa_Tecnica_Sec"] / tempo_logado_total,
        0.0,
    )
    df["Taxa_Pausa_Pessoal"] = np.where(
        tempo_logado_total > 0,
        df["Pausa_Pessoal_Sec"] / tempo_logado_total,
        0.0,
    )
    df["Taxa_Pausa_Gestao"] = np.where(
        tempo_logado_total > 0,
        df["Pausa_Gestao_Sec"] / tempo_logado_total,
        0.0,
    )

    df["Desvio_HC_Pct"] = np.where(
        df["HC_Previsto"] > 0,
        df["Delta_HC"] / df["HC_Previsto"],
        0.0,
    )
    df["Desvio_Volume_Pct"] = np.where(
        df["Vol_Previsto"] > 0,
        df["Delta_Volume"] / df["Vol_Previsto"],
        0.0,
    )

    return df


def _create_perda_log_features(df: pd.DataFrame) -> pd.DataFrame:
    """Cria features de perda de log (dados diários broadcast).

    Args:
        df: DataFrame com colunas de perda de log

    Returns:
        pd.DataFrame: DataFrame com features de perda de log
    """
    colunas_perda_log = [
        "PerdaLog_Total_Sec",
        "PPH_Total_Sec",
        "SysFailure_Sec_Daily",
        "ClientSysFailure_Sec_Daily",
        "SeatUnavail_Sec_Daily",
        "TechIssues_Total_Sec_Daily",
        "NewHire_Qtd_Daily",
        "HC_Total_PerdaLog_Daily",
        "AgentIssues_Sec_Daily",
    ]

    for coluna in colunas_perda_log:
        if coluna not in df.columns:
            df[coluna] = 0.0
        else:
            df[coluna] = df[coluna].fillna(0.0)

    df["PerdaLog_Taxa_Daily"] = np.where(
        df["PPH_Total_Sec"] > 0,
        df["PerdaLog_Total_Sec"] / df["PPH_Total_Sec"],
        0.0,
    )

    df["TechIssues_Taxa_Daily"] = np.where(
        df["PPH_Total_Sec"] > 0,
        df["TechIssues_Total_Sec_Daily"] / df["PPH_Total_Sec"],
        0.0,
    )

    df["NewHire_Pct_Daily"] = np.where(
        df["HC_Total_PerdaLog_Daily"] > 0,
        df["NewHire_Qtd_Daily"] / df["HC_Total_PerdaLog_Daily"],
        0.0,
    )

    df["AgentIssues_Taxa_Daily"] = np.where(
        df["PPH_Total_Sec"] > 0,
        df["AgentIssues_Sec_Daily"] / df["PPH_Total_Sec"],
        0.0,
    )

    return df


def _create_lag_features(df: pd.DataFrame) -> pd.DataFrame:
    """Cria features de lag (memória histórica).

    Evita data leakage usando apenas valores de períodos anteriores.

    Args:
        df: DataFrame ordenado por CodPrograma, Canal, DataHora

    Returns:
        pd.DataFrame: DataFrame com features de lag
    """
    group_cols = ["CodPrograma", "Canal"]

    df["NS_Lag_1"] = df.groupby(group_cols)["NS_Real"].shift(1)
    df["NS_Lag_2"] = df.groupby(group_cols)["NS_Real"].shift(2)
    df["NS_Lag_3"] = df.groupby(group_cols)["NS_Real"].shift(3)

    df["Taxa_Abandono_Lag_1"] = (
        df.groupby(group_cols)["Taxa_Abandono"].shift(1).fillna(0.0)
    )
    df["TME_Real_Avg_Lag_1"] = (
        df.groupby(group_cols)["TME_Real_Avg"].shift(1).fillna(0.0)
    )
    df["Taxa_Ocupacao_Lag_1"] = (
        df.groupby(group_cols)["Taxa_Ocupacao"].shift(1).fillna(0.0)
    )
    df["Taxa_Pausa_Tecnica_Lag_1"] = (
        df.groupby(group_cols)["Taxa_Pausa_Tecnica"].shift(1).fillna(0.0)
    )
    df["Taxa_Pausa_Pessoal_Lag_1"] = (
        df.groupby(group_cols)["Taxa_Pausa_Pessoal"].shift(1).fillna(0.0)
    )
    df["Taxa_Pausa_Gestao_Lag_1"] = (
        df.groupby(group_cols)["Taxa_Pausa_Gestao"].shift(1).fillna(0.0)
    )
    df["Desvio_HC_Pct_Lag_1"] = (
        df.groupby(group_cols)["Desvio_HC_Pct"].shift(1).fillna(0.0)
    )
    df["Desvio_Volume_Pct_Lag_1"] = (
        df.groupby(group_cols)["Desvio_Volume_Pct"].shift(1).fillna(0.0)
    )
    df["Delta_TMA_Lag_1"] = (
        df.groupby(group_cols)["Delta_TMA"].shift(1).fillna(0.0)
    )

    media_ns = df["NS_Real"].mean()
    df["NS_Lag_1"] = df["NS_Lag_1"].fillna(media_ns)
    df["NS_Lag_2"] = df["NS_Lag_2"].fillna(media_ns)
    df["NS_Lag_3"] = df["NS_Lag_3"].fillna(media_ns)

    return df


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Executa pipeline completo de engenharia de features.

    Etapas:
        1. Conversão de DataHora para datetime
        2. Deltas (erros de previsão)
        3. Features sintéticas
        4. Taxas (proporções)
        5. Features de perda de log
        6. Lags (memória histórica)

    Args:
        df: DataFrame com dados limpos do clean_data

    Returns:
        pd.DataFrame: DataFrame com features engineering aplicadas
    """
    if df is None or df.empty:
        logger.warning("DataFrame vazio. Retornando None.")
        return None

    df = df.copy()

    logger.info(f"Colunas antes do feature engineering: {len(df.columns)}")

    df = _ensure_datetime(df)
    df = _create_delta_features(df)
    df = _create_synthetic_features(df)
    df = _create_rate_features(df)
    df = _create_perda_log_features(df)

    df.sort_values(by=["CodPrograma", "Canal", "DataHora"], inplace=True)
    df = _create_lag_features(df)

    logger.info(f"Colunas após feature engineering: {len(df.columns)}")
    return df


def _split_train_future(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Separa dados em treino e futuro para predição.

    Identifica até onde existem dados reais e separa o restante
    como dados para predição.

    Args:
        df: DataFrame com dados processados

    Returns:
        tuple: (df_train, df_future)
    """
    mask_real = df["Vol_Real"] > 0

    if mask_real.any():
        ultimo_intervalo = df.loc[mask_real, "DataHora"].max()
    else:
        ultimo_intervalo = pd.to_datetime(datetime.now().date())

    filtro_futuro = df["DataHora"] > ultimo_intervalo

    hoje = pd.to_datetime(datetime.now().date())
    filtro_hoje = df["DataHora"] >= hoje

    mask_futuro_final = filtro_futuro & filtro_hoje

    df_train_future = df[~mask_futuro_final].copy()
    df_future = df[mask_futuro_final].copy()

    return df_train_future, df_future


def _split_train_test(
    df: pd.DataFrame,
    test_size: float,
    random_state: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Separa dados em treino e teste por DATA (não por registro).

    Usa a data de corte no percentil (1 - test_size) para garantir que
    treino use apenas dados ANTES da data de corte e teste use dados
    DEPOIS da data de corte.

    Args:
        df: DataFrame com dados (sem dados futuros)
        test_size: Proporção de teste (ex: 0.2 = últimos 20% das datas)
        random_state: Parâmetro para compatibilidade (não usado)

    Returns:
        tuple: (df_train, df_test)
    """
    if "DataHora" not in df.columns:
        raise ValueError("Coluna 'DataHora' não encontrada para split temporal")

    df = df.sort_values("DataHora").copy()

    datas_unicas = df["DataHora"].dt.date.unique()
    datas_unicas = sorted(datas_unicas)

    n_datas = len(datas_unicas)
    n_test_datas = max(1, int(n_datas * test_size))

    data_corte = datas_unicas[-n_test_datas]
    data_corte_dt = pd.Timestamp(data_corte)

    df_train = df[df["DataHora"] < data_corte_dt].copy()
    df_test = df[df["DataHora"] >= data_corte_dt].copy()

    logger.info(
        f"Split treino/teste por data: "
        f"treino={len(df_train)} ({df_train['DataHora'].min()} a {df_train['DataHora'].max()}), "
        f"teste={len(df_test)} ({df_test['DataHora'].min()} a {df_test['DataHora'].max()})"
    )

    return df_train, df_test


def save_data(
    df_train: pd.DataFrame,
    df_test: pd.DataFrame,
    df_future: pd.DataFrame,
    train_path: str,
    test_path: str,
    future_path: str,
) -> tuple[str, str, str]:
    """Salva os DataFrames de treino, teste e futuro em arquivos CSV.

    Args:
        df_train: DataFrame de treino
        df_test: DataFrame de teste
        df_future: DataFrame de dados futuros
        train_path: Caminho para salvar treino
        test_path: Caminho para salvar teste
        future_path: Caminho para salvar futuro

    Returns:
        tuple: Caminhos dos arquivos salvos
    """
    os.makedirs(os.path.dirname(train_path), exist_ok=True)

    if not df_train.empty:
        df_train.to_csv(train_path, index=False)
        logger.info(f"Dados de treino salvos em: {train_path}. Linhas: {len(df_train)}")
    else:
        logger.warning("Nenhum dado de treino encontrado.")
        df_train.to_csv(train_path, index=False)

    if not df_test.empty:
        df_test.to_csv(test_path, index=False)
        logger.info(f"Dados de teste salvos em: {test_path}. Linhas: {len(df_test)}")
    else:
        logger.warning("Nenhum dado de teste encontrado.")
        df_test.to_csv(test_path, index=False)

    if not df_future.empty:
        df_future.to_csv(future_path, index=False)
        logger.info(f"Dados futuros salvos em: {future_path}. Linhas: {len(df_future)}")
    else:
        logger.info("Nenhum dado futuro encontrado.")
        df_future.to_csv(future_path, index=False)

    return train_path, test_path, future_path


def main() -> None:
    """Orquestra pipeline de engenharia de features."""
    config = load_config()

    mode = config["data"].get("mode", "training")
    clean_path = config["data"]["clean_path"]
    train_path = config["data"]["processed_train_path"]
    test_path = config["data"]["processed_test_path"]
    future_path = config["data"]["processed_future_path"]

    df = pd.read_csv(clean_path)
    df = build_features(df)

    if mode == "inference":
        hoje = pd.to_datetime(datetime.now().date())
        df_futuro = df[df["DataHora"] >= hoje].copy()
        logger.info(f"Modo inference: salvando dados a partir de {hoje.date()}")
        df_futuro.to_csv(future_path, index=False)
        logger.info(f"Dados para inference salvos em: {future_path}. Linhas: {len(df_futuro)}")
    else:
        test_size = config["data"].get("test_size", 0.2)
        random_state = config["model"]["params"].get("random_state", 42)

        df_train_future, df_future = _split_train_future(df)
        df_train, df_test = _split_train_test(df_train_future, test_size, random_state)
        save_data(df_train, df_test, df_future, train_path, test_path, future_path)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
