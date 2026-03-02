DECLARE @DataCorte DATE = DATEADD(MONTH, -1, GETDATE());

WITH Unificado AS (
    -- Parte 1: Dados Reais (Aplicamos ISNULL aqui para garantir 0 em vez de nulo)
    SELECT 
        program_ccmsid, 
        Channel, 
        RowDate AS Data, 
        Intervalo,
        ISNULL(OFERECIDAS, 0) AS Volume_Real,           -- CORREÇÃO AQUI
        ISNULL(ATENDIDAS_NS, 0) AS Atendidas_NS_Real,   -- CORREÇÃO AQUI
        ISNULL(ATENDIDAS, 0) AS Atendidas_Real,         -- CORREÇÃO AQUI
        ISNULL(TMP_SERVICO, 0) AS Tempo_Servico_Real,   -- CORREÇÃO AQUI
        0 AS Volume_Previsto,
        0 AS NS_Meta_Pct,
        0 AS TMA_Meta
    FROM [OdsCorp].[DataMart].[factIntradayDelivery] WITH (NOLOCK)
    WHERE RowDate >= @DataCorte

    UNION ALL

    -- Parte 2: Dados de Meta/Forecast (Mantemos os 0 fixos nas colunas reais)
    SELECT 
        program_ccmsid, 
        Channel, 
        [date] AS Data, 
        [interval] AS Intervalo,
        0 AS Volume_Real,
        0 AS Atendidas_NS_Real,
        0 AS Atendidas_Real,
        0 AS Tempo_Servico_Real,
        ISNULL(ChamRece, 0) AS Volume_Previsto, -- Apliquei ISNULL aqui também por segurança
        ISNULL(SLA, 0) AS NS_Meta_Pct,
        ISNULL(TMA, 0) AS TMA_Meta
    FROM [OdsCorp].[DataMart].[MetasIntradiariasForecastDelivery] WITH (NOLOCK)
    WHERE [date] >= @DataCorte
)
SELECT 
    program_ccmsid,
    Channel,
    Data,
    Intervalo,
    -- Agora a soma será segura (0 + 0 = 0)
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
    Intervalo;