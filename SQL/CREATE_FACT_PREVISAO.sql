/*
    Tabela Fato: FactSmartCorr_Previsao
    Autor: Danielle M. Ballester
    Data: 2026-02-20
    Descrição: 
        Armazena a previsão do modelo de ML (XGBoost) para o Nível de Serviço.
        Inclui métricas do Erlang no momento da previsão e Explicabilidade Local (SHAP)
        com impactos por Pilar e Ofensores/Impulsionadores.
*/

CREATE TABLE [OdsCorp].[SmartCorr].[FactSmartCorr_Previsao] (
    -- Chaves Dimensionais
    [DataRef] DATE NOT NULL,
    [Intervalo] TIME(7) NOT NULL,
    [CodPrograma] INT NOT NULL,
    [Canal] INT NOT NULL,
    
    -- A Métrica Principal (O que a IA disse que vai acontecer)
    [NS_Previsto_SmartCorr] DECIMAL(5,4) NULL,
    
    -- O Contexto do Erlang (O que a operação acha que vai acontecer)
    [Vol_Previsto] INT NULL,
    [HC_Previsto] INT NULL,
    [TMA_Previsto_Avg] DECIMAL(10,2) NULL,
    [NS_Lag_1] DECIMAL(5,4) NULL, -- Sinal de Fumaça Imediato
    
    -- O Relato Agrupado (SHAP Values) - Impactos na Previsão
    [Impacto_Pilar_Volumetria] DECIMAL(5,4) NULL,
    [Impacto_Pilar_Pessoas] DECIMAL(5,4) NULL,
    [Impacto_Pilar_TMA] DECIMAL(5,4) NULL,
    [Impacto_Pilar_Contexto] DECIMAL(5,4) NULL, -- Lags e Temporais
    
    -- Top 3 Ofensores (O que puxou o NS pra baixo)
    [Ofensor_1_Nome] VARCHAR(100) NULL,
    [Ofensor_1_Pilar] VARCHAR(50) NULL,
    [Ofensor_1_Impacto] DECIMAL(5,4) NULL,
    
    [Ofensor_2_Nome] VARCHAR(100) NULL,
    [Ofensor_2_Pilar] VARCHAR(50) NULL,
    [Ofensor_2_Impacto] DECIMAL(5,4) NULL,
    
    [Ofensor_3_Nome] VARCHAR(100) NULL,
    [Ofensor_3_Pilar] VARCHAR(50) NULL,
    [Ofensor_3_Impacto] DECIMAL(5,4) NULL,

    -- Top 3 Impulsionadores (O que puxou/segurou o NS pra cima)
    [Impulsionador_1_Nome] VARCHAR(100) NULL,
    [Impulsionador_1_Pilar] VARCHAR(50) NULL,
    [Impulsionador_1_Impacto] DECIMAL(5,4) NULL,
    
    [Impulsionador_2_Nome] VARCHAR(100) NULL,
    [Impulsionador_2_Pilar] VARCHAR(50) NULL,
    [Impulsionador_2_Impacto] DECIMAL(5,4) NULL,
    
    [Impulsionador_3_Nome] VARCHAR(100) NULL,
    [Impulsionador_3_Pilar] VARCHAR(50) NULL,
    [Impulsionador_3_Impacto] DECIMAL(5,4) NULL,
    
    -- Rastreabilidade
    [DataHora_Atualizacao] DATETIME DEFAULT GETDATE()
);

-- Índice Clustered nas chaves dimensionais
-- Cria ordenação física no disco, vital para DELETES e SELECTS pesados do BI
CREATE CLUSTERED INDEX [IX_FactSmartCorr_Chaves] 
ON [OdsCorp].[SmartCorr].[FactSmartCorr_Previsao] ([DataRef], [CodPrograma], [Canal], [Intervalo]);
