/*
    View: Vw_SmartCorr_Principal
    Author: Danielle M. Ballester
    Date: 2026-02-19
    Description: 
        Core (Fase 1 e 2) do Dataset unificado para o projeto SmartCorr.
        Realiza o cruzamento (FULL JOIN) entre Realizado e Planejado.
        Enriquecida com dados de Pessoas/Turnover (Fase 2) baseados no report GO.
*/

-- Cria o Schema se não existir
IF NOT EXISTS (SELECT * FROM sys.schemas WHERE name = 'SmartCorr')
BEGIN
    EXEC('CREATE SCHEMA [SmartCorr]')
END
GO

CREATE OR ALTER VIEW [SmartCorr].[vw_SmartCorr_Principal]
AS

WITH RealData AS (
    SELECT 
        [program_ccmsid],
        [RowDate],
        -- Agrupamento matemático limpo e hiper-rápido para blocos de 30 min (ex: 07:10 -> 07:00, 07:40 -> 07:30)
        TIMEFROMPARTS(DATEPART(HOUR, CAST([Intervalo] AS TIME)), CASE WHEN DATEPART(MINUTE, CAST([Intervalo] AS TIME)) >= 30 THEN 30 ELSE 0 END, 0, 0, 0) AS [Intervalo],
        [Channel],
        
        -- Volumetria
        SUM([OFERECIDAS]) AS [Vol_Real],
        SUM([ATENDIDAS]) AS [Vol_Atendidas],
        SUM([ATENDIDAS_NS]) AS [Vol_Atendidas_NS],
        SUM([ABAND]) AS [Vol_Abandono],
        
        -- Tempos Operacionais
        SUM([TMP_SERVICO]) AS [TMP_SERVICO],   -- Logado
        SUM([TMP_FALADO]) AS [TMP_FALADO],     -- Talk Time
        SUM([TMP_POS_AT]) AS [TMP_POS_AT],     -- ACW
        SUM([TMP_HOLD]) AS [TMP_HOLD],         -- Hold
        SUM([TMP_ESPERA]) AS [TMP_ESPERA],     -- Queue Time
        SUM([TMP_DISPONIVEL]) AS [TMP_DISPONIVEL], -- Idle/Avail (Sec)

        -- Pausas (Raw Columns)
        SUM([TMP_PAUSA0]) AS [Pausa_0], -- Sistema
        SUM([TMP_PAUSA1]) AS [Pausa_1], -- Lanche
        SUM([TMP_PAUSA2]) AS [Pausa_2], -- Particular
        SUM([TMP_PAUSA3]) AS [Pausa_3], -- Treinamento
        SUM([TMP_PAUSA4]) AS [Pausa_4], -- Descanso
        SUM([TMP_PAUSA5]) AS [Pausa_5], -- BackOffice
        SUM([TMP_PAUSA6]) AS [Pausa_6], -- Feedback
        SUM([TMP_PAUSA7]) AS [Pausa_7], -- Falha Sistêmica
        SUM([TMP_PAUSA8]) AS [Pausa_8], -- Ambulatório
        SUM([TMP_PAUSA9]) AS [Pausa_9]  -- Ginástica

    FROM [OdsCorp].[DataMart].[factIntradayDelivery] WITH (NOLOCK)
    WHERE [RowDate] >= DATEADD(day, -90, CAST(GETDATE() AS DATE))
    GROUP BY 
        [program_ccmsid], 
        [RowDate], 
        TIMEFROMPARTS(DATEPART(HOUR, CAST([Intervalo] AS TIME)), CASE WHEN DATEPART(MINUTE, CAST([Intervalo] AS TIME)) >= 30 THEN 30 ELSE 0 END, 0, 0, 0), 
        [Channel]
),

ForecastData AS (
    SELECT 
        [program_ccmsid],
        [date] AS [RowDate],
        -- Agrupamento do Erlang para mesma proporção de 30 min
        TIMEFROMPARTS(DATEPART(HOUR, CAST([interval] AS TIME)), CASE WHEN DATEPART(MINUTE, CAST([interval] AS TIME)) >= 30 THEN 30 ELSE 0 END, 0, 0, 0) AS [Intervalo],
        [Channel],
        
        -- Metas (Benchmark)
        SUM([chamrece]) AS [Vol_Previsto],
        SUM([hcdime]) AS [HC_Previsto],
        SUM([SLA] * [chamrece]) AS [NS_Pond_Previsto],   -- SLA * Vol (Calculado)
        SUM([TMA] * [chamrece]) AS [TMA_Pond_Previsto]  -- TMA * Vol (Calculado)

    FROM [OdsCorp].[DataMart].[MetasIntradiariasForecastDelivery] WITH (NOLOCK)
    WHERE [date] >= DATEADD(day, -90, CAST(GETDATE() AS DATE))
    GROUP BY 
        [program_ccmsid], 
        [date], 
        TIMEFROMPARTS(DATEPART(HOUR, CAST([interval] AS TIME)), CASE WHEN DATEPART(MINUTE, CAST([interval] AS TIME)) >= 30 THEN 30 ELSE 0 END, 0, 0, 0), 
        [Channel]
),

PessoasData_PorAgente AS (
    SELECT 
        [CodeLevelServiceStructure1] AS [program_ccmsid],
        [Date] AS [RowDate],
        [FpwIdHierarchyLevel1],
        
        -- Soma dos Tempos Operacionais (Sem distinct, um agente pode ter multiplos trechos no dia)
        SUM(CAST([AbsenteeismTime] AS FLOAT)) AS [ABS_Tempo_Sec_Agente],
        SUM(CAST([ScheduledWorktime] AS FLOAT)) AS [ABS_Escala_Sec_Agente],
        SUM(CAST([LackOfWorkday] AS INT)) AS [Faltas_Qtd_Agente],
        
        -- Flags para transformar contagem distinta num MAX diário super rápido
        MAX(CASE WHEN [GeneralStatusCode] = 1 THEN 1 ELSE 0 END) AS [IsAtivo],
        MAX(CASE WHEN [TypeTurnOver] > 0 THEN 1 ELSE 0 END) AS [IsDesligado],
        MAX(CASE WHEN [GeneralStatusCode] = 2 THEN 1 ELSE 0 END) AS [IsFerias],
        MAX(CASE WHEN [FlagWaha] = 1 THEN 1 ELSE 0 END) AS [IsWaha]
        
    FROM [OdsCorp].[DataMart].[vw_factMicroGestao] WITH (NOLOCK)
    -- Remover "CAST(GETDATE() AS DATE)" do corpo de avaliação otimiza índices (SARGable)
    WHERE [Date] >= CAST(DATEADD(day, -90, GETDATE()) AS DATE)
    GROUP BY 
        [CodeLevelServiceStructure1],
        [Date],
        [FpwIdHierarchyLevel1]
),

PessoasData AS (
    SELECT 
        [program_ccmsid],
        [RowDate],
        
        SUM([ABS_Tempo_Sec_Agente]) AS [ABS_Tempo_Sec],
        SUM([ABS_Escala_Sec_Agente]) AS [ABS_Escala_Sec],
        SUM([Faltas_Qtd_Agente]) AS [Faltas_Qtd],
        
        -- Emulação ultra-rápida do COUNT(DISTINCT)
        SUM([IsAtivo]) AS [Turnover_Ativos],
        SUM([IsDesligado]) AS [Turnover_Desligados],
        SUM([IsFerias]) AS [Ferias_Qtd],
        SUM([IsWaha]) AS [WAHA_Qtd]
        
    FROM PessoasData_PorAgente
    GROUP BY 
        [program_ccmsid],
        [RowDate]
)

SELECT 
    -- Chaves de Cruzamento (Coalesce para garantir não-nulos no Full Join)
    COALESCE(R.RowDate, F.RowDate) AS [DataRef],
    COALESCE(R.Intervalo, F.Intervalo) AS [Intervalo],
    COALESCE(R.program_ccmsid, F.program_ccmsid) AS [CodPrograma],
    COALESCE(R.Channel, F.Channel) AS [Canal],

    -- Volumetria (Features + Target Components)
    ISNULL(F.Vol_Previsto, 0) AS [Vol_Previsto],
    ISNULL(R.Vol_Real, 0) AS [Vol_Real],
    ISNULL(R.Vol_Atendidas, 0) AS [Vol_Atendidas],
    ISNULL(R.Vol_Atendidas_NS, 0) AS [Vol_Atendidas_NS_Real], -- Numerador do Target
    ISNULL(R.Vol_Abandono, 0) AS [Vol_Abandono],

    -- Capacidade (HC)
    ISNULL(F.HC_Previsto, 0) AS [HC_Previsto],
    
    -- HC Real Equivalente: (Segundos Disponíveis / 1800s do slot)
    -- Ex: 3600s logados = 2 Agentes Full Time no slot de 30min
    CAST(ISNULL(R.TMP_DISPONIVEL, 0) / 1800.0 AS DECIMAL(10,2)) AS [HC_Real_Equiv],

    -- Nível de Serviço Previsto Oficial (Erlang Capacity)
    CASE WHEN ISNULL(F.Vol_Previsto, 0) > 0 THEN (F.NS_Pond_Previsto / F.Vol_Previsto) ELSE 0 END AS [NS_Previsto_Erlang],

    -- TMA (Tempos Totais em Segundos)
    -- O modelo usará (Tempo_Total / Vol) no Python para achar a média, evitando div/0 aqui
    ISNULL(F.TMA_Pond_Previsto, 0) AS [Tempo_AHT_Previsto_Total],
    (ISNULL(R.TMP_FALADO,0) + ISNULL(R.TMP_HOLD,0) + ISNULL(R.TMP_POS_AT,0)) AS [Tempo_AHT_Real_Total],
    ISNULL(R.TMP_ESPERA, 0) AS [Tempo_Espera_Total],

    -- Pausas Agrupadas (Ineficiência / Aderência)
    -- Grupo 1: Perda Técnica (Sistema + Falha) -> CRÍTICO
    (ISNULL(R.Pausa_0,0) + ISNULL(R.Pausa_7,0)) AS [Pausa_Tecnica_Sec],

    -- Grupo 2: Pessoal (Lanche + Particular + Descanso + Saúde) -> ADERÊNCIA
    (ISNULL(R.Pausa_1,0) + ISNULL(R.Pausa_2,0) + ISNULL(R.Pausa_4,0) + ISNULL(R.Pausa_8,0) + ISNULL(R.Pausa_9,0)) AS [Pausa_Pessoal_Sec],

    -- Grupo 3: Gestão (Treino + BackOffice + Feedback) -> PLANEJADO
    (ISNULL(R.Pausa_3,0) + ISNULL(R.Pausa_5,0) + ISNULL(R.Pausa_6,0)) AS [Pausa_Gestao_Sec],

    -- KPIs de Pessoas (Diário - Broadcast para os Intervalos)
    ISNULL(P.ABS_Tempo_Sec, 0) AS [ABS_Tempo_Sec_Daily],
    ISNULL(P.ABS_Escala_Sec, 0) AS [ABS_Escala_Sec_Daily],
    ISNULL(P.Turnover_Ativos, 0) AS [Turnover_Ativos_Daily],
    ISNULL(P.Turnover_Desligados, 0) AS [Turnover_Desligados_Daily],
    ISNULL(P.Ferias_Qtd, 0) AS [Ferias_Qtd_Daily],
    ISNULL(P.Faltas_Qtd, 0) AS [Faltas_Qtd_Daily],
    ISNULL(P.WAHA_Qtd, 0) AS [WAHA_Qtd_Daily]

FROM RealData R
FULL OUTER JOIN ForecastData F 
    ON R.RowDate = F.RowDate 
    AND R.Intervalo = F.Intervalo 
    AND R.program_ccmsid = F.program_ccmsid
    AND R.Channel = F.Channel
LEFT JOIN PessoasData P
    ON COALESCE(R.RowDate, F.RowDate) = P.RowDate
    AND COALESCE(R.program_ccmsid, F.program_ccmsid) = P.program_ccmsid;
