import pandas as pd
from src.database import get_connection

def main():
    conn = get_connection()
    query = """
    WITH Base_Erlang AS (
        SELECT 
            CAST([DataRef] AS DATE) as DataRef,
            CAST([Intervalo] AS TIME) as Intervalo,
            [CodPrograma],
            [NS_Previsto_Erlang],
            [Vol_Previsto],
            [HC_Previsto]
        FROM [OdsCorp].[SmartCorr].[vw_SmartCorr_Principal]
        WHERE CAST([DataRef] AS DATE) = CAST(GETDATE() AS DATE)
          AND [CodPrograma] = 347851
    ),
    Base_SmartCorr AS (
        SELECT 
            CAST([DataRef] AS DATE) as DataRef,
            CAST([Intervalo] AS TIME) as Intervalo,
            [CodPrograma],
            [NS_Previsto_SmartCorr],
            [Ofensor_1_Nome],
            [Impulsionador_1_Nome]
        FROM [OdsCorp].[SmartCorr].[FactSmartCorr_Previsao]
        WHERE CAST([DataRef] AS DATE) = CAST(GETDATE() AS DATE)
          AND [CodPrograma] = 347851
    ),
    Base_Real AS (
        SELECT 
            CAST([DataRef] AS DATE) as DataRef,
            CAST([Intervalo] AS TIME) as Intervalo,
            [CodPrograma],
            [Vol_Real],
            -- Calcular NS Real on the fly se necessário ou pegar pronto
            CASE WHEN ISNULL([Vol_Real], 0) > 0 THEN CAST([Vol_Atendidas_NS_Real] AS FLOAT) / CAST([Vol_Real] AS FLOAT) ELSE 0 END as NS_Real
        FROM [OdsCorp].[SmartCorr].[vw_SmartCorr_Principal]
        WHERE CAST([DataRef] AS DATE) = CAST(GETDATE() AS DATE)
          AND [CodPrograma] = 347851
    )
    SELECT 
        e.Intervalo,
        MAX(e.Vol_Previsto) as Vol_Previsto,
        MAX(ISNULL(r.Vol_Real, 0)) as Vol_Real,
        MAX(e.HC_Previsto) as HC_Previsto,
        -- Aplica regra de negocio do WFM (Vol_Real = 0 => NS_Real = 0)
        MAX(CASE 
            WHEN ISNULL(r.Vol_Real, 0) = 0 THEN 0.0
            ELSE ISNULL(r.NS_Real, 0) 
        END) as NS_Real_WFM,
        MAX(e.NS_Previsto_Erlang) as NS_Previsto_Erlang,
        MAX(s.NS_Previsto_SmartCorr) as NS_Previsto_SmartCorr,
        MAX(s.Ofensor_1_Nome) as Ofensor_1_Nome
    FROM Base_Erlang e
    LEFT JOIN Base_SmartCorr s 
        ON e.DataRef = s.DataRef 
        AND e.Intervalo = s.Intervalo 
        AND e.CodPrograma = s.CodPrograma
    LEFT JOIN Base_Real r
        ON e.DataRef = r.DataRef 
        AND e.Intervalo = r.Intervalo 
        AND e.CodPrograma = r.CodPrograma
    GROUP BY e.Intervalo
    ORDER BY e.Intervalo
    """
    
    df = pd.read_sql(query, conn)
    conn.close()
    
    print("\n" + "="*80)
    print(f"COMPARAÇÃO DE HOJE: Erlang vs SmartCorr vs NS Real WFM")
    print("="*80)
    
    # Vamos mostrar intervalos das 09h às 15h para ter uma amostra clara dos horários de pico
    df_amostra = df[(df['Intervalo'].astype(str) >= '09:00:00') & (df['Intervalo'].astype(str) <= '15:00:00')]
    
    # Formataçao para visualizaçao no terminal
    df_show = df_amostra.copy()
    df_show['NS_Real_WFM'] = df_show['NS_Real_WFM'].apply(lambda x: f"{x:.1%}")
    df_show['NS_Erlang'] = df_show['NS_Previsto_Erlang'].apply(lambda x: f"{x:.1%}" if pd.notnull(x) else "N/A")
    df_show['NS_SmartCorr'] = df_show['NS_Previsto_SmartCorr'].apply(lambda x: f"{x:.1%}" if pd.notnull(x) else "N/A")
    
    # Seleciona colunas para exibir
    colunas = ['Intervalo', 'Vol_Real', 'Vol_Previsto', 'HC_Previsto', 'NS_Real_WFM', 'NS_Erlang', 'NS_SmartCorr', 'Ofensor_1_Nome']
    print(df_show[colunas].to_string(index=False))
    
if __name__ == "__main__":
    main()