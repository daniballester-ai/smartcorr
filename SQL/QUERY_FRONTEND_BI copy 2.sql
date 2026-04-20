/*
    Dashboard / Frontend Query (Single Source of Truth)
    ---------------------------------------------------
    Objetivo: Unir os dados Reais advindos da CTI (via View Base)
    com a Inteligência Artificial e Ofensores (via Fact Preditiva).

    CTI é a sigla em inglês para Computer Telephony Integration (Integração Computador-Telefonia).
    
    Esta é a querie recomendada para ser consumida pela API (Next.js)
    ou pelo Import Data do Power BI para desenhar a tela final do gestor.
*/

SELECT 
    -- 1. Chaves da Operação
    v.[DataRef], 
    v.[Intervalo], 
    v.[CodPrograma], 
    v.[Canal],
    
    -- 2. Métricas de Volume (Real vs Previsto)
    v.[Vol_Real], 
    v.[Vol_Previsto],
    (v.[Vol_Real] - v.[Vol_Previsto]) AS [Delta_Volume],
    v.[Vol_Atendidas],
    v.[Vol_Atendidas_NS_Real],
    v.[Vol_Abandono],
    CASE WHEN v.[Vol_Real] > 0 THEN CAST(v.[Vol_Abandono] AS FLOAT) / v.[Vol_Real] ELSE 0 END AS [Taxa_Abandono_Atual],
    
    -- 3. Métricas de Capacidade / Pessoas (Real vs Previsto)
    v.[HC_Real_Equiv],
    v.[HC_Previsto],
    (v.[HC_Real_Equiv] - v.[HC_Previsto]) AS [Delta_HC],
    
    -- Métricas Diárias de Pessoas do Relatório Go!
    v.[Faltas_Qtd_Daily],
    v.[Ferias_Qtd_Daily],
    CASE WHEN v.[ABS_Escala_Sec_Daily] > 0 THEN (CAST(v.[ABS_Tempo_Sec_Daily] AS FLOAT) / v.[ABS_Escala_Sec_Daily]) ELSE 0 END AS [ABS_Taxa_Daily_Atual],
    
    -- 4. Métricas de Tempo (TMA, TME, Pausas)
    CASE WHEN v.[Vol_Real] > 0 THEN (v.[Tempo_AHT_Real_Total] / v.[Vol_Real]) ELSE 0 END AS [TMA_Real_Agora],
    CASE WHEN v.[Vol_Previsto] > 0 THEN (v.[Tempo_AHT_Previsto_Total] / v.[Vol_Previsto]) ELSE 0 END AS [TMA_Previsto_Erlang],
    CASE WHEN v.[Vol_Atendidas] > 0 THEN (v.[Tempo_Espera_Total] / v.[Vol_Atendidas]) ELSE 0 END AS [TME_Real_Agora],
    v.[Pausa_Tecnica_Sec],
    v.[Pausa_Pessoal_Sec],
    
    -- 5. Métricas Principais (A Batalha: Nível de Serviço Real vs IA)
    CASE WHEN v.[Vol_Real] > 0 THEN CAST(v.[Vol_Atendidas_NS_Real] AS FLOAT) / v.[Vol_Real] ELSE 0 END AS [Nivel_Servico_Real_Ate_Agora],     
    f.[NS_Previsto_SmartCorr] AS [Nivel_Servico_Previsto_IA],
    f.[NS_Lag_1] AS [Nivel_Servico_Meia_Hora_Anterior],
    
    -- 6. Análise Macro: Qual pilar está ajudando ou atrapalhando? (Visão XAI - Cascata)
    f.[Impacto_Pilar_Pessoas],
    f.[Impacto_Pilar_Volumetria],
    f.[Impacto_Pilar_TMA],
    f.[Impacto_Pilar_Contexto],
    
    -- 7. Análise Micro Dores: Causa Raiz para Card Vermelho do Frontend (TOP 3 Ofensores)
    f.[Ofensor_1_Nome] AS [Ofensor_1_Nome],
    f.[Ofensor_1_Impacto] AS [Ofensor_1_Peso_NS],
    f.[Ofensor_1_Pilar] AS [Ofensor_1_Pilar],
    
    f.[Ofensor_2_Nome] AS [Ofensor_2_Nome],
    f.[Ofensor_2_Impacto] AS [Ofensor_2_Peso_NS],
    f.[Ofensor_2_Pilar] AS [Ofensor_2_Pilar],
    
    f.[Ofensor_3_Nome] AS [Ofensor_3_Nome],
    f.[Ofensor_3_Impacto] AS [Ofensor_3_Peso_NS],
    f.[Ofensor_3_Pilar] AS [Ofensor_3_Pilar],
    
    -- 8. Análise Micro Ajudas: Causa Raiz para Card Verde do Frontend (TOP 3 Impulsionadores)
    f.[Impulsionador_1_Nome] AS [Impulsionador_1_Nome],
    f.[Impulsionador_1_Impacto] AS [Impulsionador_1_Peso_NS],
    f.[Impulsionador_1_Pilar] AS [Impulsionador_1_Pilar],
    
    f.[Impulsionador_2_Nome] AS [Impulsionador_2_Nome],
    f.[Impulsionador_2_Impacto] AS [Impulsionador_2_Peso_NS],
    f.[Impulsionador_2_Pilar] AS [Impulsionador_2_Pilar],
    
    f.[Impulsionador_3_Nome] AS [Impulsionador_3_Nome],
    f.[Impulsionador_3_Impacto] AS [Impulsionador_3_Peso_NS],
    f.[Impulsionador_3_Pilar] AS [Impulsionador_3_Pilar]
    
FROM [OdsCorp].[SmartCorr].[vw_SmartCorr_Principal] v WITH (NOLOCK)
LEFT JOIN [OdsCorp].[SmartCorr].[FactSmartCorr_Previsao] f WITH (NOLOCK)
    ON v.[CodPrograma] = f.[CodPrograma]
    AND v.[DataRef] = f.[DataRef]
    AND v.[Intervalo] = f.[Intervalo]
    AND v.[Canal] = f.[Canal]
    
-- Filtro para trazer apenas o retrato do dia atual em diante (Dashboard Vivo)
WHERE v.[DataRef] >= CAST(GETDATE() AS DATE) 

-- Filtro base da Operação Pagbank / Voz
AND v.[CodPrograma] IN (366845, 370587, 370588, 548619, 581345, 
          581346, 589266, 589360, 589361, 591529, 
          347851, 347858, 353059, 355491, 355492) 
AND v.[Canal] = 7

ORDER BY 
    v.[DataRef], 
    v.[Intervalo];
