-- Script SQL para criar a tabela de destino das predições de absenteísmo
-- Tabela: [dbo].[stageProcessoAbsenteismoPredicao]

CREATE TABLE [dbo].[stageProcessoAbsenteismoPredicao] (
    [Data] DATE NOT NULL,             -- Data da escala
    [CodeLevelServiceStructure3] INT NOT NULL,  -- Código da operação
    [FpwIdHierarchyLevel1] INT NOT NULL,  -- Matrícula do especialista
    [Probabilidade_de_Ausencia] FLOAT NOT NULL  -- Probabilidade de ausência (0.0 a 1.0)
);

CREATE TABLE [dbo].[ProcessoAbsenteismoPredicao] (
    [Data] DATE NOT NULL,             -- Data da escala
    [CodeLevelServiceStructure3] INT NOT NULL,  -- Código da operação
    [FpwIdHierarchyLevel1] INT NOT NULL,  -- Matrícula do especialista
    [Probabilidade_de_Ausencia] FLOAT NOT NULL, -- Probabilidade de ausência (0.0 a 1.0)
    [insertDateCtrl] DATETIME NOT NULL DEFAULT GETDATE(), -- Data de inserção do registro
    [processKey] int NULL, -- Chave do processo para rastreabilidade
    PRIMARY KEY CLUSTERED ([Data], [CodeLevelServiceStructure3], [FpwIdHierarchyLevel1])
);

-- Adicionar índices se necessário para performance
CREATE INDEX IX_ProcessoAbsenteismoPredicao_Data ON [dbo].[ProcessoAbsenteismoPredicao] ([Data]);
CREATE INDEX IX_ProcessoAbsenteismoPredicao_Matricula ON [dbo].[ProcessoAbsenteismoPredicao] ([FpwIdHierarchyLevel1]);
