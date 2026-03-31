import pandas as pd
import logging
import os
import yaml
from src.database import get_connection

logger = logging.getLogger(__name__)

def load_config():
    """Carrega as configurações do arquivo params.yaml."""
    with open("params.yaml", "r") as f:
        return yaml.safe_load(f)

# Query que consome a View SmartCorr Principal (Fase 1 - Core)
# Filtros:
#   - CodPrograma: Operações Pagbank
#   - Canal: 7 (Voz)
#   - Janela: Configurável via params.yaml (janela_dias e data_corte_final)
QUERY_SMARTCORR = """
    SELECT
        [DataRef],
        [Intervalo],
        [CodPrograma],
        [Canal],

        -- Volumetria
        [Vol_Previsto],
        [Vol_Real],
        [Vol_Atendidas],
        [Vol_Atendidas_NS_Real],
        [Vol_Abandono],

        -- Capacidade (HC)
        [HC_Previsto],
        [HC_Real_Equiv],

        -- TMA (Tempos Totais em Segundos)
        [Tempo_AHT_Previsto_Total],
        [Tempo_AHT_Real_Total],
        [Tempo_Espera_Total],

        -- Pausas Agrupadas (Ineficiência)
        [Pausa_Tecnica_Sec],
        [Pausa_Pessoal_Sec],
        [Pausa_Gestao_Sec],

        -- KPIs de Pessoas (Diários - Broadcast para Intervalos)
        [ABS_Tempo_Sec_Daily],
        [ABS_Escala_Sec_Daily],
        [Turnover_Ativos_Daily],
        [Turnover_Desligados_Daily],
        [Ferias_Qtd_Daily],
        [Faltas_Qtd_Daily],
        [WAHA_Qtd_Daily]

    FROM [OdsCorp].[SmartCorr].[vw_SmartCorr_Principal] WITH (NOLOCK)
    WHERE 1=1
        -- Filtro de Janela Temporal
        AND [DataRef] >= DATEADD(DAY, -{janela_dias}, {data_base_expr})
        {data_limite_expr}

        -- Filtro de Operações Pagbank
        AND [CodPrograma] IN (
            366845, 370587, 370588, 548619, 581345,
            581346, 589266, 589360, 589361, 591529,
            347851, 347858, 353059, 355491, 355492
        )

        -- Filtro de Canal (7 = Voz)
        AND [Canal] = 7
"""

# Query que consome a FatoTempoSistemas (Perda de Log)
# Agregação por CellCode (Programa) e Date (Dia)
# Dados diários: serão mesclados via broadcast nos intervalos intraday
QUERY_PERDA_LOG = """
    SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED;

    SELECT
        F.[Date]                                    AS DataRef,
        F.[CellCode]                                AS CodPrograma,

        -- Perda de Log Agregada (Gap de Log - Pilar Pessoas)
        SUM(ISNULL(F.[TempoLogadoCRM],0)
          - ISNULL(F.[PPH_Value],0))                AS PerdaLog_Total_Sec,
        SUM(F.[PPH_Value])                          AS PPH_Total_Sec,

        -- Indisponibilidade Sistêmica (Pilar Pessoas)
        SUM(ISNULL(F.[SystemFailure],0))            AS SysFailure_Sec_Daily,
        SUM(ISNULL(F.[ClientSystemFailure],0))      AS ClientSysFailure_Sec_Daily,
        SUM(ISNULL(F.[SeatUnavailable],0))          AS SeatUnavail_Sec_Daily,
        SUM(ISNULL(F.[SystemFailure],0)
          + ISNULL(F.[ClientSystemFailure],0)
          + ISNULL(F.[SeatUnavailable],0))          AS TechIssues_Total_Sec_Daily,

        -- Qualidade do Staff (Pilar Pessoas)
        SUM(CASE WHEN FT.IsNewHire = 1 THEN 1 ELSE 0 END)  AS NewHire_Qtd_Daily,
        COUNT(DISTINCT F.[FpwId])                            AS HC_Total_PerdaLog_Daily,

        -- Problemas do Agente (Pilar Pessoas)
        SUM(ISNULL(F.[AgentIssues],0))              AS AgentIssues_Sec_Daily

    FROM [OdsCorp].[DataMart].[FatoTempoSistemas] F WITH (NOLOCK)
    LEFT JOIN [OdsCorp].[DataMart].[factMicroGestao] FT WITH (NOLOCK)
        ON F.[Date] = FT.[Date]
        AND F.[FpwId] = FT.[FpwIdHierarchyLevel1]
    WHERE 1=1
        AND F.[Date] >= DATEADD(DAY, -{janela_dias}, {data_base_expr})
        {data_limite_expr}
        AND F.[CellCode] IN (
            366845, 370587, 370588, 548619, 581345,
            581346, 589266, 589360, 589361, 591529,
            347851, 347858, 353059, 355491, 355492
        )
    GROUP BY F.[Date], F.[CellCode]
"""

def main():
    """Função principal de extração de dados da View SmartCorr."""
    config = load_config()
    caminho_raw = config['data']['raw_path']
    janela_dias = config['data'].get('janela_dias', 60)
    data_corte_final = config['data'].get('data_corte_final')

    # Configura expressões de data para a query
    if data_corte_final:
        data_base_expr = f"CONVERT(DATETIME, '{data_corte_final}', 103)"
        data_limite_expr = f"AND [DataRef] < DATEADD(DAY, 1, CONVERT(DATETIME, '{data_corte_final}', 103))"
        info_janela = f"Janela: {janela_dias} dias (corte em {data_corte_final})"
    else:
        data_base_expr = "GETDATE()"
        data_limite_expr = ""
        info_janela = f"Janela: {janela_dias} dias (atual)"

    # Cria diretório se não existir
    os.makedirs(os.path.dirname(caminho_raw), exist_ok=True)

    # Monta a query principal com a janela configurável
    query_final = QUERY_SMARTCORR.replace("{janela_dias}", str(janela_dias))
    query_final = query_final.replace("{data_base_expr}", data_base_expr)
    query_final = query_final.replace("{data_limite_expr}", data_limite_expr)

    # Monta a query do Perda de Log com os mesmos filtros de janela
    query_perda_log = QUERY_PERDA_LOG.replace("{janela_dias}", str(janela_dias))
    query_perda_log = query_perda_log.replace("{data_base_expr}", data_base_expr)
    query_perda_log = query_perda_log.replace("{data_limite_expr}", data_limite_expr)

    logger.info(f"Iniciando carga de dados ({info_janela})...")
    conexao = get_connection()
    try:
        # 1. Carga principal (View SmartCorr)
        df = pd.read_sql(query_final, conexao)
        logger.info(f"Dados SmartCorr carregados: {len(df)} linhas, {len(df.columns)} colunas.")

        if df.empty:
            logger.warning("ATENÇÃO: Nenhum dado retornado! Verifique os filtros e a View no SQL Server.")

        # 2. Carga complementar (Perda de Log - FatoTempoSistemas)
        logger.info("Carregando dados do Perda de Log (FatoTempoSistemas)...")
        df_perda_log = pd.read_sql(query_perda_log, conexao)
        logger.info(f"Dados Perda de Log carregados: {len(df_perda_log)} linhas.")

        # 3. Merge: Broadcast diário (mesmo valor para todos os intervalos do dia)
        if not df_perda_log.empty and not df.empty:
            # Normalizar DataRef para date string (sem hora) em ambos os lados
            df['DataRef_Str'] = pd.to_datetime(df['DataRef']).dt.strftime('%Y-%m-%d')
            df_perda_log['DataRef_Str'] = pd.to_datetime(df_perda_log['DataRef']).dt.strftime('%Y-%m-%d')
            df_perda_log['CodPrograma'] = df_perda_log['CodPrograma'].astype(df['CodPrograma'].dtype)

            df = df.merge(
                df_perda_log.drop(columns=['DataRef']),
                on=['CodPrograma', 'DataRef_Str'],
                how='left'
            )
            df.drop(columns=['DataRef_Str'], inplace=True)
            logger.info(f"Merge concluído. Colunas totais: {len(df.columns)}")
        else:
            logger.warning("Perda de Log vazio. As features de Perda de Log serão preenchidas com 0.")

        df.to_csv(caminho_raw, index=False)
        logger.info(f"Dados brutos salvos em: {caminho_raw}")

    except Exception as e:
        logger.error(f"Erro ao carregar dados: {e}")
        raise
    finally:
        conexao.close()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
