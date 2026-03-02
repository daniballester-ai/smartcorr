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
    -- 1. Chaves da Operação perfeitamente alinhadas com a View
    v.[DataRef], 
    v.[Intervalo], 
    v.[CodPrograma], 
    v.[Canal],
    
    -- 2. Métricas Reais e de Forecast (Erlang)
    v.[Vol_Real], 
    v.[Vol_Atendidas_NS_Real], 
    v.[Vol_Previsto],
    
    -- TMA calculado de forma segura (Prevenindo Divisão por Zero no Frontend)
    CASE WHEN v.[Vol_Real] > 0 THEN (v.[Tempo_AHT_Real_Total] / v.[Vol_Real]) ELSE 0 END AS [TMA_Real_Agora],
    CASE WHEN v.[Vol_Previsto] > 0 THEN (v.[Tempo_AHT_Previsto_Total] / v.[Vol_Previsto]) ELSE 0 END AS [TMA_Previsto_Erlang],
    
    v.[HC_Real_Equiv],
    v.[HC_Previsto],
    
    -- 3. Métricas Principais (A Batalha: Previsto IA vs Final Real)
    CASE WHEN v.[Vol_Real] > 0 THEN CAST(v.[Vol_Atendidas_NS_Real] AS FLOAT) / v.[Vol_Real] ELSE 0 END AS [Nivel_Servico_Ate_Agora],     
    v.[NS_Previsto_Erlang] AS [Nivel_Servico_Previsto_Erlang],
    f.[NS_Previsto_SmartCorr] AS [Nivel_Servico_Previsto_SmartCorr],
    
    -- 4. Análise Macro: Qual pilar está ajudando ou atrapalhando? (Visão XAI - Cascata)
    f.[Impacto_Pilar_Pessoas],
    f.[Impacto_Pilar_Volumetria],
    f.[Impacto_Pilar_TMA],
    
    -- 5. Análise Micro: Causa Raiz para o Card Vermelho/Verde do Frontend
    f.[Ofensor_1_Nome] AS Pior_Problema_Nome,
    f.[Ofensor_1_Impacto] AS Pior_Problema_Peso_NS,
    
    f.[Ofensor_2_Nome] AS Segundo_Pior_Problema_Nome,
    
    f.[Impulsionador_1_Nome] AS Maior_Ajuda_Nome,
    f.[Impulsionador_1_Impacto] AS Maior_Ajuda_Peso_NS
    
FROM [OdsCorp].[SmartCorr].[vw_SmartCorr_Principal] v
LEFT JOIN [OdsCorp].[SmartCorr].[FactSmartCorr_Previsao] f
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
