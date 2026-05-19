import logging
import os
from configparser import ConfigParser
from typing import Optional

import pandas as pd
import yaml
from sqlalchemy import create_engine

from src.database import get_connection

logger = logging.getLogger("src.data_loading.load_data")


def load_config() -> dict:
    """Carrega as configurações do arquivo params.yaml.

    Returns:
        dict: Configurações carregadas do arquivo params.yaml
    """
    with open("params.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_queries(queries_file: str) -> dict:
    """Carrega as queries SQL do arquivo .ini.

    Args:
        queries_file: Caminho para o arquivo de queries

    Returns:
        dict: Dicionário com as queries 'smartcorr' e 'perda_log'
    """
    config = ConfigParser()
    config.read(queries_file)
    return {
        "smartcorr": config.get("smartcorr", "query"),
        "perda_log": config.get("perda_log", "query"),
    }


def _build_programas_filter(programas: list[int]) -> str:
    """Constrói a cláusula IN para filtrar programas dinamicamente.

    Permite escalar para qualquer cliente/operação apenas adicionando
    novos CodPrograma no params.yaml, sem alterar código ou SQL.

    Args:
        programas: Lista de CodPrograma ativos

    Returns:
        str: Cláusula SQL formatada (ex: '366845, 370587, 370588')

    Raises:
        ValueError: Se a lista estiver vazia
    """
    if not programas:
        raise ValueError(
            "Lista de programas vazia em params.yaml -> data.programas. "
            "Adicione pelo menos um CodPrograma."
        )

    filtro = ", ".join(str(p) for p in programas)
    logger.info(f"Filtro dinâmico de programas: {len(programas)} programa(s) configurado(s)")
    return filtro


def _build_data_expressions(
    janela_dias: int,
    data_corte_final: Optional[str],
    mode: str = "training",
    future_days: int = 7,
) -> tuple[str, str, str, str]:
    """Constrói as expressões de data para as queries SQL.

    Args:
        janela_dias: Quantidade de dias para janela de consulta (training)
        data_corte_final: Data de corte no formato DD/MM/YYYY ou None
        mode: Modo de operação ('training' ou 'inference')
        future_days: Dias futuros para inference

    Returns:
        Tupla contendo (data_base_expr, data_limite_smartcorr, data_limite_perda_log, info_janela)
    """
    if mode == "inference":
        data_base_expr = "GETDATE()"
        data_limite_smartcorr = f"AND [DataRef] <= DATEADD(DAY, {future_days}, CAST(GETDATE() AS DATE))"
        data_limite_perda_log = f"AND F.[Date] <= DATEADD(DAY, {future_days}, CAST(GETDATE() AS DATE))"
        info_janela = f"Inference: {future_days} dias futuros"
    elif data_corte_final:
        data_base_expr = f"CONVERT(DATETIME, '{data_corte_final}', 103)"
        data_limite_smartcorr = f"AND [DataRef] < DATEADD(DAY, 1, CONVERT(DATETIME, '{data_corte_final}', 103))"
        data_limite_perda_log = f"AND F.[Date] < DATEADD(DAY, 1, CONVERT(DATETIME, '{data_corte_final}', 103))"
        info_janela = f"Janela: {janela_dias} dias (corte em {data_corte_final})"
    else:
        data_base_expr = "GETDATE()"
        data_limite_smartcorr = ""
        data_limite_perda_log = ""
        info_janela = f"Janela: {janela_dias} dias (atual)"

    return data_base_expr, data_limite_smartcorr, data_limite_perda_log, info_janela


def _fetch_smartcorr_data(
    engine,
    query: str,
    janela_dias: int,
    data_base_expr: str,
    data_limite_expr: str,
    programas_filter: str,
    canal_filter: int,
) -> pd.DataFrame:
    """Busca dados principais da View SmartCorr.

    Args:
        engine: SQLAlchemy engine
        query: Query SQL a ser executada
        janela_dias: Quantidade de dias para janela de consulta
        data_base_expr: Expressão SQL para data base
        data_limite_expr: Expressão SQL para limite de data
        programas_filter: Cláusula IN com CodPrograma
        canal_filter: Código do canal de atendimento

    Returns:
        pd.DataFrame: Dados carregados da View SmartCorr
    """
    query = (
        query.replace("{janela_dias}", str(janela_dias))
        .replace("{data_base_expr}", data_base_expr)
        .replace("{data_limite_expr}", data_limite_expr)
        .replace("{programas_filter}", programas_filter)
        .replace("{canal_filter}", str(canal_filter))
    )
    df = pd.read_sql(query, engine)
    logger.info(f"Dados SmartCorr carregados: {len(df)} linhas, {len(df.columns)} colunas.")
    return df


def _fetch_perda_log_data(
    engine,
    query: str,
    janela_dias: int,
    data_base_expr: str,
    data_limite_expr: str,
    programas_filter: str,
) -> pd.DataFrame:
    """Busca dados complementares de perda de log (FatoTempoSistemas).

    Args:
        engine: SQLAlchemy engine
        query: Query SQL a ser executada
        janela_dias: Quantidade de dias para janela de consulta
        data_base_expr: Expressão SQL para data base
        data_limite_expr: Expressão SQL para limite de data (usa F.[Date])
        programas_filter: Cláusula IN com CodPrograma

    Returns:
        pd.DataFrame: Dados de perda de log agregados por dia
    """
    query = (
        query.replace("{janela_dias}", str(janela_dias))
        .replace("{data_base_expr}", data_base_expr)
        .replace("{data_limite_expr_perda_log}", data_limite_expr)
        .replace("{programas_filter}", programas_filter)
    )
    df = pd.read_sql(query, engine)
    logger.info(f"Dados Perda de Log carregados: {len(df)} linhas.")
    return df


def _merge_daily_data(df_main: pd.DataFrame, df_daily: pd.DataFrame) -> pd.DataFrame:
    """Realiza merge broadcast dos dados diários para os intervalos intraday.

    Args:
        df_main: DataFrame principal com dados por intervalo
        df_daily: DataFrame com dados agregados por dia

    Returns:
        pd.DataFrame: DataFrame mesclado com dados de ambos os sources
    """
    if df_daily.empty:
        logger.warning("Perda de Log vazio. As features de Perda de Log serão preenchidas com 0.")
        return df_main

    df_main["DataRef_Str"] = pd.to_datetime(df_main["DataRef"]).dt.strftime("%Y-%m-%d")
    df_daily["DataRef_Str"] = pd.to_datetime(df_daily["DataRef"]).dt.strftime("%Y-%m-%d")
    df_daily["CodPrograma"] = df_daily["CodPrograma"].astype(df_main["CodPrograma"].dtype)

    df_merged = df_main.merge(
        df_daily.drop(columns=["DataRef"]),
        on=["CodPrograma", "DataRef_Str"],
        how="left",
    )
    df_merged.drop(columns=["DataRef_Str"], inplace=True)
    logger.info(f"Merge concluído. Colunas totais: {len(df_merged.columns)}")
    return df_merged


def fetch_data(
    janela_dias: int,
    queries_file: str,
    programas: list[int],
    canal: int = 7,
    data_corte_final: Optional[str] = None,
    mode: str = "training",
    future_days: int = 7,
) -> pd.DataFrame:
    """Busca e consolida dados da View SmartCorr e FatoTempoSistemas.

    Executa queries no banco de dados SQL Server via SQLAlchemy, aplica filtros de janela
    temporal configurados, realiza merge dos dados diários (broadcast)
    com os dados por intervalo e retorna o DataFrame consolidado.

    Args:
        janela_dias: Quantidade de dias para janela de consulta (training)
        queries_file: Caminho para o arquivo de queries
        programas: Lista de CodPrograma ativos (dinâmico via params.yaml)
        canal: Código do canal de atendimento (default: 7 = Voz)
        data_corte_final: Data de corte no formato DD/MM/YYYY ou None
        mode: Modo de operação ('training' ou 'inference')
        future_days: Dias futuros para inference

    Returns:
        pd.DataFrame: Dados consolidados de volumetria, capacidade e KPIs
    """
    queries = load_queries(queries_file)
    programas_filter = _build_programas_filter(programas)

    data_base_expr, data_limite_smartcorr, data_limite_perda_log, info_janela = _build_data_expressions(
        janela_dias, data_corte_final, mode, future_days
    )

    logger.info(f"Iniciando carga de dados via SQLAlchemy ({info_janela})...")
    engine = get_connection()

    try:
        df_smartcorr = _fetch_smartcorr_data(
            engine, queries["smartcorr"], janela_dias,
            data_base_expr, data_limite_smartcorr,
            programas_filter, canal,
        )

        if df_smartcorr.empty:
            logger.warning("ATENÇÃO: Nenhum dado retornado! Verifique os filtros e a View no SQL Server.")

        df_perda_log = _fetch_perda_log_data(
            engine, queries["perda_log"], janela_dias,
            data_base_expr, data_limite_perda_log,
            programas_filter,
        )

        df = _merge_daily_data(df_smartcorr, df_perda_log)
        
        # Ordenar dados na origem (DataRef e Intervalo)
        sort_cols = [col for col in ['DataRef', 'Intervalo'] if col in df.columns]
        if sort_cols:
            df = df.sort_values(by=sort_cols).reset_index(drop=True)
            logger.info(f"Dados consolidados e ordenados por: {', '.join(sort_cols)}")
        
        return df
    
    finally:
        engine.dispose()


def save_data(data: pd.DataFrame, output_path: str) -> str:
    """Salva os dados brutos em arquivo CSV.

    Args:
        data: DataFrame com os dados a serem salvos
        output_path: Caminho do arquivo CSV

    Returns:
        str: Caminho do arquivo CSV onde os dados foram salvos
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    data.to_csv(output_path, index=False)
    logger.info(f"Dados brutos salvos em: {output_path}")

    return output_path


def main() -> None:
    """Orquestra o pipeline de extração e salvamento dos dados."""
    config = load_config()

    mode = config["data"].get("mode", "training")
    if mode == "inference":
        janela_dias = config["data"].get("janela_dias_inference", 30)
    else:
        janela_dias = config["data"].get("janela_dias", 180)
    future_days = config["data"].get("future_days", 7)
    data_corte_final = config["data"].get("data_corte_final")
    queries_file = config["data"]["queries_file"]
    raw_path = config["data"]["raw_path"]
    programas = config["data"]["programas"]
    canal = config["data"].get("canal", 7)

    df = fetch_data(
        janela_dias,
        queries_file,
        programas=programas,
        canal=canal,
        data_corte_final=data_corte_final,
        mode=mode,
        future_days=future_days,
    )
    save_data(df, raw_path)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
