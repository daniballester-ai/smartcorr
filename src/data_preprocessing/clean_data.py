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
    with open("params.yaml", "r", encoding="utf-8") as f:
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


def _filter_programas_inativos(df: pd.DataFrame) -> pd.DataFrame:
    """Remove programas sem nenhuma operação real na janela de dados.

    Programas onde TODOS os registros possuem Vol_Real == 0 são
    considerados inativos no período e removidos do treino para
    evitar que o modelo aprenda padrões de inatividade.

    Os programas permanecem no params.yaml para treino futuro
    quando passarem a ter operação real.

    Args:
        df: DataFrame com colunas CodPrograma e Vol_Real

    Returns:
        pd.DataFrame: DataFrame apenas com programas operacionais
    """
    volume_por_programa = df.groupby("CodPrograma")["Vol_Real"].sum()
    programas_ativos = volume_por_programa[volume_por_programa > 0].index.tolist()
    programas_inativos = volume_por_programa[volume_por_programa == 0].index.tolist()

    if programas_inativos:
        logger.warning(
            f"PROGRAMAS INATIVOS (Vol_Real=0 em toda janela): "
            f"{programas_inativos} — removidos do treino"
        )

    df_filtrado = df[df["CodPrograma"].isin(programas_ativos)].copy()

    logger.info(
        f"Programas: {len(programas_ativos)} ativos, "
        f"{len(programas_inativos)} inativos removidos"
    )

    return df_filtrado


def _filter_operacional(
    df: pd.DataFrame,
    config_filtro: dict,
) -> pd.DataFrame:
    """Filtra intervalos sem operação real para evitar viés no treino.

    PROBLEMA RESOLVIDO: 59% dos dados de treino tinham NS_Real == 0 porque
    Vol_Real == 0 (sem chamadas reais naquele intervalo). Isso fazia o modelo
    aprender milhares de "não-eventos" que distorciam as predições.

    Esta função marca os registros como operacionais ou não, e remove
    os não-operacionais do set de treino. Para inferência, mantém todos.

    Inclui diagnóstico por programa para identificar operações com dados
    anômalos ou inatividade parcial.

    Args:
        df: DataFrame com coluna Vol_Real
        config_filtro: Configuração do filtro operacional do params.yaml

    Returns:
        pd.DataFrame: DataFrame com coluna 'eh_operacional' e registros
                       não-operacionais removidos (se modo treino)
    """
    if not config_filtro.get("ativo", True):
        logger.info("Filtro operacional DESATIVADO.")
        df["eh_operacional"] = True
        return df

    vol_minimo = config_filtro.get("vol_minimo_operacional", 1)

    # Marca como operacional se Vol_Real >= vol_minimo
    df["eh_operacional"] = df["Vol_Real"] >= vol_minimo

    registros_nao_operacionais = (~df["eh_operacional"]).sum()
    total_registros = len(df)
    pct_nao_operacional = (registros_nao_operacionais / total_registros * 100) if total_registros > 0 else 0

    logger.info(
        f"Filtro operacional: {registros_nao_operacionais}/{total_registros} "
        f"({pct_nao_operacional:.1f}%) intervalos SEM operação real (Vol_Real < {vol_minimo})"
    )

    # ─── Diagnóstico por Programa (P3) ───────────────────────────
    logger.info("Diagnóstico operacional por programa:")
    for programa in sorted(df["CodPrograma"].unique()):
        df_prog = df[df["CodPrograma"] == programa]
        n_total_prog = len(df_prog)
        n_nao_op_prog = (~df_prog["eh_operacional"]).sum()
        pct_prog = (n_nao_op_prog / n_total_prog * 100) if n_total_prog > 0 else 0

        # Estatísticas de NS_Real para registros operacionais
        ns_operacional = df_prog.loc[df_prog["eh_operacional"], "NS_Real"]
        ns_mean = ns_operacional.mean() if not ns_operacional.empty else 0
        ns_zero_pct = (
            (ns_operacional == 0).mean() * 100 if not ns_operacional.empty else 0
        )

        icone = "!" if pct_prog > 50 else "*"
        logger.info(
            f"  {icone} Programa {programa}: "
            f"{n_nao_op_prog}/{n_total_prog} ({pct_prog:.1f}%) sem operação | "
            f"NS médio operac.={ns_mean:.3f}, NS==0 operac.={ns_zero_pct:.1f}%"
        )

        if pct_prog > 70:
            logger.warning(
                f"  Programa {programa}: {pct_prog:.0f}% dos intervalos são "
                f"não-operacionais. Verifique a grade horária deste programa."
            )

    # Remove não-operacionais do treino
    df_operacional = df[df["eh_operacional"]].copy()

    logger.info(
        f"Registros operacionais mantidos: {len(df_operacional)} "
        f"({len(df_operacional)/total_registros*100:.1f}%)"
    )

    return df_operacional


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
    df["NS_Real"] = np.where(
        df["Vol_Real"] > 0,
        df["Vol_Atendidas_NS_Real"] / df["Vol_Real"],
        0.0,
    )
    df["NS_Real"] = df["NS_Real"].clip(lower=0.0, upper=1.0)

    df["NS_Previsto_Erlang"] = df.get("NS_Previsto_Erlang", 0.0).fillna(0.0)
    df["NS_Previsto_Erlang"] = np.clip(df["NS_Previsto_Erlang"], 0.0, 1.0)

    if target_col == "NS_Residuo":
        df["NS_Residuo"] = df["NS_Real"] - df["NS_Previsto_Erlang"]
    elif target_col != "NS_Real":
        raise ValueError(f"Target inválido: {target_col}. Use 'NS_Real' ou 'NS_Residuo'.")

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


def clean(df: pd.DataFrame, config: Optional[dict] = None) -> pd.DataFrame:
    """Executa pipeline completo de limpeza e preparação dos dados.

    Etapas:
        1. Parsing de DataHora (DataRef + Intervalo)
        2. Extração de features temporais (Hora, DiaSemana)
        3. Filtragem de intervalos relevantes (turnos fechados)
        4. Cálculo do target (NS_Real)
        5. Filtragem operacional (remove NS=0 por falta de operação)
        6. Preenchimento de valores nulos

    Args:
        df: DataFrame com dados brutos do load_data
        config: Configuração do params.yaml (se None, carrega automaticamente)

    Returns:
        pd.DataFrame: DataFrame limpo e preparado
    """
    if config is None:
        config = load_config()

    config_filtro = config["data"].get("filtro_operacional", {"ativo": True, "vol_minimo_operacional": 1})

    logger.info(f"Linhas antes da limpeza: {len(df)}")

    df = _parse_datetime(df)
    df = _create_temporal_features(df)
    df = _filter_relevant_intervals(df)
    df = _calculate_target(df, target_col=config["data"].get("target", "NS_Real"))

    # Filtros condicionais baseados no modo
    modo = config["data"].get("mode", "training")
    if modo != "inference":
        df = _filter_programas_inativos(df)
        df = _filter_operacional(df, config_filtro)
    else:
        logger.info(
            "Modo inference: filtros de programa inativo e operacional "
            "desativados para preservar dados futuros."
        )

    df = _fill_missing_values(df)

    # Log da distribuição do target após limpeza (global + por programa)
    if "NS_Real" in df.columns:
        ns = df["NS_Real"]
        logger.info(
            f"Distribuição NS_Real pós-limpeza (GLOBAL): "
            f"mean={ns.mean():.3f}, "
            f"==0: {(ns == 0).sum()} ({(ns == 0).mean()*100:.1f}%), "
            f"==1: {(ns == 1).sum()} ({(ns == 1).mean()*100:.1f}%), "
            f"entre 0 e 1: {((ns > 0) & (ns < 1)).sum()} ({((ns > 0) & (ns < 1)).mean()*100:.1f}%)"
        )

        # ─── Diagnóstico NS_Real por programa (P3) ──────────────
        if modo != "inference":
            logger.info("Distribuição NS_Real pós-limpeza POR PROGRAMA:")
            for programa in sorted(df["CodPrograma"].unique()):
                ns_prog = df.loc[df["CodPrograma"] == programa, "NS_Real"]
                n_total = len(ns_prog)
                n_zero = (ns_prog == 0).sum()
                n_um = (ns_prog == 1).sum()
                n_entre = ((ns_prog > 0) & (ns_prog < 1)).sum()
                logger.info(
                    f"  Programa {programa}: n={n_total}, "
                    f"mean={ns_prog.mean():.3f}, "
                    f"==0: {n_zero} ({n_zero/n_total*100:.1f}%), "
                    f"==1: {n_um} ({n_um/n_total*100:.1f}%), "
                    f"entre: {n_entre} ({n_entre/n_total*100:.1f}%)"
                )

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
    df_clean = clean(df_raw, config)
    save_data(df_clean, clean_path)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
