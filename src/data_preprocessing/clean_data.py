import logging
import os
from typing import Optional

import pandas as pd
import numpy as np
import yaml

logger = logging.getLogger(__name__)


def load_config() -> dict:
    """Carrega as configurações do arquivo params.yaml.

    Returns:
        dict: Configurações carregadas do arquivo params.yaml
    """
    with open("params.yaml", "r") as f:
        return yaml.safe_load(f)


def _parse_datetime(df: pd.DataFrame) -> pd.DataFrame:
    """Constrói campo DataHora a partir de DataRef e Intervalo.

    Args:
        df: DataFrame com colunas DataRef e Intervalo

    Returns:
        pd.DataFrame: DataFrame com coluna DataHora adicionada
    """
    if "DataRef" not in df.columns or "Intervalo" not in df.columns:
        logger.warning("Colunas DataRef ou Intervalo não encontradas. Pulando parsing de DataHora.")
        return df

    df["Data_Str"] = df["DataRef"].astype(str)
    df["Intervalo_Str"] = df["Intervalo"].astype(str).str[:8]
    df["DataHora"] = pd.to_datetime(
        df["Data_Str"] + " " + df["Intervalo_Str"], errors="coerce"
    )
    df.drop(columns=["Data_Str", "Intervalo_Str"], inplace=True, errors="ignore")

    return df


def _create_temporal_features(df: pd.DataFrame) -> pd.DataFrame:
    """Extrai features temporais de DataHora.

    Args:
        df: DataFrame com coluna DataHora

    Returns:
        pd.DataFrame: DataFrame com colunas Hora e DiaSemana
    """
    if "DataHora" not in df.columns:
        logger.warning("Coluna DataHora não encontrada. Pulando criação de features temporais.")
        return df

    df["Hora"] = df["DataHora"].dt.hour
    df["DiaSemana"] = df["DataHora"].dt.dayofweek

    return df


def _filter_relevant_intervals(df: pd.DataFrame) -> pd.DataFrame:
    """Filtra intervalos relevantes para o modelo.

    Remove apenas registros de turnos fechados (sem HC, sem previsão, sem atendimento).
    Mantém:
        - Registros operacionais (com volume)
        - Registros ociosos (com equipe, sem volume)

    Args:
        df: DataFrame com colunas Vol_Previsto, Vol_Real e HC_Previsto

    Returns:
        pd.DataFrame: DataFrame filtrado
    """
    filtro = (
        (df["Vol_Previsto"] > 0) |
        (df["Vol_Real"] > 0) |
        (df["HC_Previsto"] > 0)
    )
    df_filtered = df[filtro].copy()
    logger.info(f"Linhas após filtro de relevância: {len(df_filtered)}")
    return df_filtered


def _calculate_target(df: pd.DataFrame, target_col: str = "NS_Real") -> pd.DataFrame:
    """Calcula o Nível de Serviço Real.

    Fórmula: Vol_Atendidas_NS_Real / Vol_Real
    - Divisão por zero retorna 0
    - Valores são limitados entre 0 e 1

    Args:
        df: DataFrame com colunas Vol_Real e Vol_Atendidas_NS_Real
        target_col: Nome da coluna alvo

    Returns:
        pd.DataFrame: DataFrame com coluna de target calculada
    """
    df[target_col] = np.where(
        df["Vol_Real"] > 0,
        df["Vol_Atendidas_NS_Real"] / df["Vol_Real"],
        0.0,
    )
    df[target_col] = df[target_col].clip(lower=0.0, upper=1.0)

    return df


def _fill_missing_values(df: pd.DataFrame, fill_value: float = 0.0) -> pd.DataFrame:
    """Preenche valores nulos em colunas numéricas.

    Args:
        df: DataFrame a ser preenchido
        fill_value: Valor para preenchimento (default: 0.0)

    Returns:
        pd.DataFrame: DataFrame com valores nulos preenchidos
    """
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    df[numeric_cols] = df[numeric_cols].fillna(fill_value)
    return df


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """Executa pipeline completo de limpeza e preparação dos dados.

    Etapas:
        1. Parsing de DataHora (DataRef + Intervalo)
        2. Extração de features temporais (Hora, DiaSemana)
        3. Filtragem de intervalos relevantes
        4. Cálculo do target (NS_Real)
        5. Preenchimento de valores nulos

    Args:
        df: DataFrame com dados brutos do load_data

    Returns:
        pd.DataFrame: DataFrame limpo e preparado
    """
    logger.info(f"Linhas antes da limpeza: {len(df)}")

    df = _parse_datetime(df)
    df = _create_temporal_features(df)
    df = _filter_relevant_intervals(df)
    df = _calculate_target(df)
    df = _fill_missing_values(df)

    logger.info(f"Linhas após limpeza: {len(df)}")
    return df


def save_data(df: pd.DataFrame, output_path: str) -> str:
    """Salva os dados limpos em arquivo CSV.

    Args:
        df: DataFrame com dados limpos
        output_path: Caminho do arquivo CSV

    Returns:
        str: Caminho do arquivo salvo
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    df.to_csv(output_path, index=False)
    logger.info(f"Dados limpos salvos em: {output_path}")
    return output_path


def main() -> None:
    """Orquestra pipeline de carregamento, limpeza e salvamento."""
    config = load_config()

    raw_path = config["data"]["raw_path"]
    clean_path = config["data"]["clean_path"]

    df_raw = pd.read_csv(raw_path)
    df_clean = clean(df_raw)
    save_data(df_clean, clean_path)

 
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
