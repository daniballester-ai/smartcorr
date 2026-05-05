-- ==========================================================
-- Comparação de Nível de Serviço (NS): Erlang vs SmartCorr
-- Finalidade: Analisar o ganho de precisão do modelo ML em relação ao Erlang
-- ==========================================================

SELECT 
    P.[DataRef],
    P.[Intervalo],
    P.[CodPrograma],
    
    -- NS Baseline (Erlang Puro)
    B.[NS_Previsto_Erlang] AS [NS_Erlang_Teorico],
    
    -- NS SmartCorr (Predição direta de NS_Real pelo modelo)
    P.[NS_Previsto_SmartCorr] AS [NS_SmartCorr_Final],

    -- NS Real (regra WFM: Vol_Real == 0 => NS_Real == 0)
    CASE
        WHEN B.[Vol_Real] > 0 THEN
            CASE
                WHEN (CAST(B.[Vol_Atendidas_NS_Real] AS FLOAT) / NULLIF(B.[Vol_Real], 0)) > 1.0 THEN 1.0
                ELSE (CAST(B.[Vol_Atendidas_NS_Real] AS FLOAT) / NULLIF(B.[Vol_Real], 0))
            END
        ELSE 0.0
    END AS [NS_Real],
    
    -- Erros absolutos vs real (pp)
    ABS(
        (
            CASE
                WHEN B.[Vol_Real] > 0 THEN
                    CASE
                        WHEN (CAST(B.[Vol_Atendidas_NS_Real] AS FLOAT) / NULLIF(B.[Vol_Real], 0)) > 1.0 THEN 1.0
                        ELSE (CAST(B.[Vol_Atendidas_NS_Real] AS FLOAT) / NULLIF(B.[Vol_Real], 0))
                    END
                ELSE 0.0
            END
        ) - B.[NS_Previsto_Erlang]
    ) AS [ErroAbs_Erlang],
    ABS(
        (
            CASE
                WHEN B.[Vol_Real] > 0 THEN
                    CASE
                        WHEN (CAST(B.[Vol_Atendidas_NS_Real] AS FLOAT) / NULLIF(B.[Vol_Real], 0)) > 1.0 THEN 1.0
                        ELSE (CAST(B.[Vol_Atendidas_NS_Real] AS FLOAT) / NULLIF(B.[Vol_Real], 0))
                    END
                ELSE 0.0
            END
        ) - P.[NS_Previsto_SmartCorr]
    ) AS [ErroAbs_SmartCorr],
    
    -- Principais Alavancas de Ajuste (Explicabilidade SHAP)
    P.[Impacto_Pilar_Pessoas] AS [Impacto_Pessoas],
    P.[Impacto_Pilar_Volumetria] AS [Impacto_Volume],
    P.[Impacto_Pilar_TMA] AS [Impacto_TMA],
    
    -- Ofensores Detectados
    P.[Ofensor_1_Nome] AS [Principal_Ofensor],
    P.[Ofensor_1_Impacto],
    
    -- Impulsionadores Detectados
    P.[Impulsionador_1_Nome] AS [Principal_Impulsionador],
    P.[Impulsionador_1_Impacto]

FROM [OdsCorp].[SmartCorr].[FactSmartCorr_Previsao] P WITH (NOLOCK)
INNER JOIN [OdsCorp].[SmartCorr].[vw_SmartCorr_Principal] B WITH (NOLOCK)
    ON P.[DataRef] = B.[DataRef]
    AND P.[Intervalo] = B.[Intervalo]
    AND P.[CodPrograma] = B.[CodPrograma]
    AND P.[Canal] = B.[Canal]

WHERE P.[DataRef] >= CAST(GETDATE() AS DATE)
ORDER BY P.[DataRef], P.[Intervalo], P.[CodPrograma];
