-- Parâmetros de Recorte
DECLARE @DataInicio DATE = '2026-04-04';
DECLARE @DataFim DATE   = '2026-04-11';
DECLARE @Threshold FLOAT      = 0.6;

-- 1. Tabela Temporária para consolidar Predição vs Realidade
 DROP TABLE IF EXISTS #ComparativoAbs;

SELECT 
    p.[FpwIdHierarchyLevel1],
    p.[Data],
    CASE WHEN p.[Probabilidade_de_Ausencia] >= @Threshold THEN 1 ELSE 0 END AS Predicao,
    CASE WHEN f.[LackOfWorkday] > 0 THEN 1 ELSE 0 END AS Realidade
INTO #ComparativoAbs
FROM [dbAbs].[dbo].[ProcessoAbsenteismoPredicao] p
INNER JOIN [dbAbs].[dbo].[factMicroGestao2] f 
    ON p.[FpwIdHierarchyLevel1] = f.[FpwIdHierarchyLevel1] 
    AND p.[Data] = f.[date]
WHERE p.[Data] BETWEEN @DataInicio AND @DataFim
  AND f.[ScheduledWorktime] > 0; -- Garante que avaliamos apenas dias de escala real

-- 2. Tabela Temporária para Cálculo das Matrizes de Confusão
  DROP TABLE  IF EXISTS  #MetricasBase;

SELECT 
    CAST(COUNT(*) AS FLOAT) AS Total,
    SUM(CASE WHEN Predicao = 1 AND Realidade = 1 THEN 1.0 ELSE 0 END) AS TP, -- Verdadeiro Positivo
    SUM(CASE WHEN Predicao = 0 AND Realidade = 0 THEN 1.0 ELSE 0 END) AS TN, -- Verdadeiro Negativo
    SUM(CASE WHEN Predicao = 1 AND Realidade = 0 THEN 1.0 ELSE 0 END) AS FP, -- Falso Positivo
    SUM(CASE WHEN Predicao = 0 AND Realidade = 1 THEN 1.0 ELSE 0 END) AS FN  -- Falso Negativo
INTO #MetricasBase
FROM #ComparativoAbs;

-- 3. Inserção do Resultado Final (Log de Performance)
-- Substitua [dbo].[Resultados_Validacao_Modelos] pelo nome da sua tabela de log
--INSERT INTO [dbAbs].[dbo].[LogPerformanceModelos] 
--    (DataProcessamento, InicioPeriodo, FimPeriodo, Acuracia, Precisao, Recall, F1_Score)
SELECT 
    GETDATE() AS DataProcessamento,
    @DataInicio AS InicioPeriodo,
    @DataFim AS FimPeriodo,
    (TP + TN) / Total AS Acuracia,
    CASE WHEN (TP + FP) = 0 THEN 0 ELSE TP / (TP + FP) END AS Precisao,
    CASE WHEN (TP + FN) = 0 THEN 0 ELSE TP / (TP + FN) END AS Recall,
    TP,
    TN,
    FP,
    FN,
    -- Cálculo do F1-Score: 2 * (P * R) / (P + R)
    CASE 
        WHEN (TP + FP) = 0 OR (TP + FN) = 0 THEN 0 
        ELSE (2.0 * (TP / (TP + FP)) * (TP / (TP + FN))) / ((TP / (TP + FP)) + (TP / (TP + FN))) 
    END AS F1_Score
FROM #MetricasBase;
 