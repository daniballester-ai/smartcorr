-- CONFIGURAÇÂO DOS FILTROS
DECLARE @DataInicio DATE    = '2026-02-19';      -- Data Inicial
DECLARE @DataFim    DATE    = GETDATE();         -- Data Final (hoje)
DECLARE @HoraInicio TIME(0) = '17:30:00';        -- Horário Inicial (Intervalo)
DECLARE @HoraFim    TIME(0) = '17:30:00';        -- Horário Final (Intervalo)

-- CTE com UNION ALL (Filtros aplicados direto na origem)
WITH Unificado AS (
    -- Parte 1: Dados Reais
    SELECT 
        program_ccmsid, 
        Channel, 
        RowDate AS Data, 
        Intervalo,
        ISNULL(OFERECIDAS, 0) AS Volume_Real,
        ISNULL(ATENDIDAS_NS, 0) AS Atendidas_NS_Real,
        ISNULL(ATENDIDAS, 0) AS Atendidas_Real,
        ISNULL(TMP_SERVICO, 0) AS Tempo_Servico_Real,
        0 AS Volume_Previsto,
        0 AS NS_Meta_Pct,
        0 AS TMA_Meta
    FROM [OdsCorp].[DataMart].[factIntradayDelivery] WITH (NOLOCK)
    WHERE RowDate BETWEEN @DataInicio AND @DataFim
      AND Intervalo BETWEEN @HoraInicio AND @HoraFim
      AND program_ccmsid IN (
          366845, 370587, 370588, 548619, 581345, 
          581346, 589266, 589360, 589361, 591529, 
          347851, 347858, 353059, 355491, 355492
      )

    UNION ALL

    -- Parte 2: Dados de Meta/Forecast
    SELECT 
        program_ccmsid, 
        Channel, 
        [date] AS Data, 
        [interval] AS Intervalo,
        0 AS Volume_Real,
        0 AS Atendidas_NS_Real,
        0 AS Atendidas_Real,
        0 AS Tempo_Servico_Real,
        ISNULL(ChamRece, 0) AS Volume_Previsto,
        ISNULL(SLA, 0) AS NS_Meta_Pct,
        ISNULL(TMA, 0) AS TMA_Meta
    FROM [OdsCorp].[DataMart].[MetasIntradiariasForecastDelivery] WITH (NOLOCK)
    WHERE [date] BETWEEN @DataInicio AND @DataFim
      AND [interval] BETWEEN @HoraInicio AND @HoraFim
      AND program_ccmsid IN (
          366845, 370587, 370588, 548619, 581345, 
          581346, 589266, 589360, 589361, 591529, 
          347851, 347858, 353059, 355491, 355492
      )
)
SELECT 
    program_ccmsid,
    Channel,
    Data,
    Intervalo,
    -- Agregação final
    SUM(Volume_Real) AS Volume_Real,
    SUM(Atendidas_NS_Real) AS Atendidas_NS_Real,
    SUM(Atendidas_Real) AS Atendidas_Real,
    SUM(Tempo_Servico_Real) AS Tempo_Servico_Real,
    SUM(Volume_Previsto) AS Volume_Previsto,
    SUM(NS_Meta_Pct) AS NS_Meta_Pct,
    SUM(TMA_Meta) AS TMA_Meta
FROM Unificado
GROUP BY 
    program_ccmsid,
    Channel,
    Data,
    Intervalo
ORDER BY
    program_ccmsid, Data, Intervalo;