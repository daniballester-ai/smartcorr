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

    # Monta a query com a janela configurável
    query_final = QUERY_SMARTCORR.replace("{janela_dias}", str(janela_dias))
    query_final = query_final.replace("{data_base_expr}", data_base_expr)
    query_final = query_final.replace("{data_limite_expr}", data_limite_expr)

    logger.info(f"Iniciando carga de dados ({info_janela})...")
    conexao = get_connection()
    try:
        df = pd.read_sql(query_final, conexao)
        logger.info(f"Dados carregados: {len(df)} linhas, {len(df.columns)} colunas.")

        if df.empty:
            logger.warning("ATENÇÃO: Nenhum dado retornado! Verifique os filtros e a View no SQL Server.")

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
