/*
    SCRIPT: Extração de Dados Reais para Benchmark (SmartCorr)
    Objetivo: Consolidar o Realizado (NS_Real) e o Baseline (NS_Erlang)
    para comparar com as predições de Machine Learning geradas via Backtesting.
*/

-- Defina aqui os CodPrograma que deseja conferir (ex: 366845, 370587, 370588)
DECLARE @Programas TABLE (ID INT);
INSERT INTO @Programas VALUES (366845), (370587), (370588);

-- Intervalo de Datas para o Benchmark (Semana Passada)
DECLARE @DataInicio DATE = DATEADD(DAY, -7, CAST(GETDATE() AS DATE));
DECLARE @DataFim DATE = DATEADD(DAY, -1, CAST(GETDATE() AS DATE));

SELECT
    [DataRef],
    [Intervalo],
    [CodPrograma],
    
    -- Realizado (Numerador e Denominador)
    [Vol_Atendidas_NS_Real],
    [Vol_Real] AS Vol_Recebidas_Real,
    
    -- NS Real (%) - Calculado
    CASE 
        WHEN [Vol_Real] > 0 
        THEN CAST([Vol_Atendidas_NS_Real] AS FLOAT) / [Vol_Real] 
        ELSE 0 
    END AS NS_Real_Percent,

    -- Baseline Teórico (Erlang Forecast)
    [NS_Previsto_Erlang] AS NS_Erlang_Percent

FROM [OdsCorp].[SmartCorr].[vw_SmartCorr_Principal] WITH (NOLOCK)
WHERE [CodPrograma] IN (SELECT ID FROM @Programas)
  AND [DataRef] BETWEEN @DataInicio AND @DataFim
  AND [Canal] = 7 -- Filtro Voz (Padrão)
ORDER BY [DataRef], [Intervalo], [CodPrograma];
