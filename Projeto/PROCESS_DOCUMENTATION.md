# Documentação do Processo de Absenteísmo Preditivo

## 1. Visão geral do processo atual

O projeto atual implementa um pipeline de previsão de absenteísmo que:

1. Carrega dados do banco de dados via query SQL.
2. Filtra os dados por intervalo de datas dinâmico usando parâmetros de controle.
3. Faz preprocessamento e engenharia de features.
4. Treina um modelo por operação (`CodeLevelServiceStructure3`).
5. Gera previsões de probabilidade para escalas futuras.
6. Insere o resultado em uma tabela stage no banco de dados.
7. Executa a procedure `dbo.AtualizaAbsenteismoPredicao` após o insert.

Ainda faltam implementar em produção:
- criação das tabelas finais no banco de produção;
- criação do nó de processo que dispara o script automaticamente.

---

## 2. Arquitetura do processo

### 2.1 Entrada

O script principal é `Projeto/main.py`.
Ele lê argumentos via `argparse`, incluindo:

- `--connectionString`: conexão ODBC com o SQL Server.
- `--ProcessTable`: tabela stage de destino.
- `--ProcessKey`: chave de processo usada pela procedure.
- `--dias_atras`: janela para trás no filtro da query.
- `--dias_frente`: janela para frente no filtro da query.
- `--FinalDateCtrl`: data de referência para o treinamento e previsões.
- `--dias_filtro_previsao`: quantidade de dias para trás da `FinalDateCtrl` para filtrar as previsões a inserir (padrão: 2).

### 2.2 Carregamento de dados

A classe `AbsenteeismPredictor` em `Projeto/AbsenteeismPredictor/main.py` faz:

- leitura da query em `Projeto/sql/Base_treinamento_dev.sql`;
- substituição de `{{data_inicial}}` e `{{data_final}}` com base em `FinalDateCtrl`, `dias_atras` e `dias_frente`;
- execução da query no banco, retornando o DataFrame inicial.

### 2.3 Preprocessamento

O método `preprocess_data()` faz:

- normalização de nomes de colunas mínimos (`date`, `LackOfWorkday`, `JustifiedEventFlag`);
- conversão de `DATA` para datetime;
- criação de `TARGET` a partir de `LackOfWorkday`;
- conversão de coordenadas para numérico;
- cálculo da distância Haversine entre `latExp/longExp` e `latSite/longSite`;
- preenchimento de distâncias faltantes com mediana;
- criação de categorias de distância.

### 2.4 Engenharia de features

O método `feature_engineering()` faz:

- criação de `DIA_DA_SEMANA` e `FIM_DE_SEMANA`;
- cálculo de estatísticas por especialista/operação via `_calculate_expert_stats()`;
- definição das features finais usadas pelo modelo.

O cálculo de estatísticas históricas usa `FinalDateCtrl` como data de referência.

### 2.5 Treinamento por operação

O método `train_model_por_operacao()`:

- itera sobre cada `CodeLevelServiceStructure3` disponível;
- filtra o dataset por operação;
- chama `prepare_data()` para montar os conjuntos de treino e teste;
- treina um `RandomForestClassifier` com parâmetros fixos;
- gera previsões usando `predict_absenteeism()`;
- concatena os resultados para todas as operações.

Se não houver dados de teste suficientes, o processo continua com treino sem avaliação.

### 2.5.1 Avaliação do modelo (opcional)

Quando o parâmetro `--evaluate_model` é passado, o método `evaluate_overall_model()` é executado:

- Coleta dados de teste de todas as operações que possuem dados suficientes;
- Treina modelos individuais por operação usando os dados de treino;
- Faz previsões no conjunto de teste de cada operação;
- Calcula métricas globais agregadas: acurácia, precisão, recall, F1-score e AUC-ROC;
- Gera relatório de classificação detalhado;
- Plota e salva matriz de confusão como `confusion_matrix.png` (se matplotlib e seaborn estiverem disponíveis).

Esta avaliação permite medir o desempenho geral do modelo antes da inserção em produção.

### 2.6 Geração de previsões finais

`predict_absenteeism()` obtém os registros futuros a partir de `FinalDateCtrl - dias_filtro_previsao` dias (padrão 5) e calcula:

- `PROBABILIDADE` de ausência para cada escala futura.

O resultado final contém as colunas:

- `FpwIdHierarchyLevel1`
- `CodeLevelServiceStructure3`
- `DATA_PREVISAO`
- `PROBABILIDADE`

### 2.7 Preparação para inserção

`_prepare_df_pred_insert()` faz:

- rename para o esquema de colunas de destino da tabela stage;
- validação das colunas obrigatórias;
- filtro de registros recentes a partir de `FinalDateCtrl - dias_filtro_previsao` dias (padrão 2, configurável via parâmetro);
- formatação da data e truncamento de strings.

### 2.8 Inserção no banco e procedure

`insert_data()` executa:

1. `TRUNCATE TABLE {ProcessTable}`;
2. `INSERT INTO {ProcessTable} (...) VALUES (...)` com colunas dinâmicas baseadas no DataFrame final;
3. `EXEC dbo.AtualizaAbsenteismoPredicao @processKey = ?`.

O insert é construído dinamicamente a partir de `self.df_pred_insert.columns`, portanto qualquer mudança no output é automaticamente refletida no SQL.

---

## 3. Diferenças em relação ao projeto original `MLPreditivoAbs.py`

### 3.1 Configuração e dependências

- O projeto atual usa `ConnectionString` diretamente via argumento de linha de comando.
- O `MLPreditivoAbs.py` original usava credenciais fixas vindo de `credencial.py` e uma conexão criada dentro da classe.

### 3.2 Carregamento de dados

- O projeto atual usa um SQL externo com placeholders `{{data_inicial}}` / `{{data_final}}` e aceita controle explícito de datas via `FinalDateCtrl`, `dias_atras` e `dias_frente`.
- O original tinha query integrada com intervalos calculados internamente e usava `GETDATE()` para derivar as datas.

### 3.3 Nomes de colunas e padrão

- O projeto atual preserva as colunas originais do banco (`CodeLevelServiceStructure3`, `ScheduledWorktime`, `FpwIdHierarchyLevel1`) e aplica apenas renomeios mínimos de alias.
- O projeto original havia renomeado várias colunas para português, como `MATRICULA EXPERT`, `TEMPO ESCALA`, `FALTOU`.

### 3.4 Saída de previsão

- O projeto atual produz apenas `probabilidade` de ausência, sem converter isso em um flag binário `PREVISAO_ABS`.
- O original possuía lógica de predição binária com threshold e construção de features ligeiramente diferente.

### 3.5 Inserção dinâmica e fase de stage

- O projeto atual insere diretamente na tabela stage especificada por `ProcessTable`, truncando antes e chamando procedure depois.
- O original tinha um método `insert_data(df, table_name, schema='AbsGuard')` genérico, mas não fazia o fluxo stage + procedure automatizado.

### 3.6 Controle de processo

- O projeto atual já integra `ProcessKey` e a execução de `dbo.AtualizaAbsenteismoPredicao`.
- O original não continha essa camada de orquestração de processo baseado em chave de processo.

### 3.7 Modularidade e produção

- O projeto atual está organizado em `Projeto/AbsenteeismPredictor/main.py` e `Projeto/main.py`, com separação clara entre pipeline e entrypoint.
- O original era uma classe mais isolada, sem uma descrição de nó de processo ou automação de execução.

### 3.8 Dependências adicionais

- O projeto atual adicionou `matplotlib` e `seaborn` para plotar matriz de confusão durante avaliação.
- Estas bibliotecas são opcionais - se não estiverem disponíveis, a avaliação continua mas sem plot visual.

---

## 4. Próximos passos para produção

### 4.1 Criar tabelas no banco de produção

As tabelas necessárias são:

- `dbo.stageProcessoAbsenteismoPredicao`
- `dbo.ProcessoAbsenteismoPredicao` (caso desejado)

A definição deve corresponder às colunas geradas por `df_pred_insert` depois do rename final.

### 4.2 Criar nó de processo automático

O processo deve disparar `Projeto/main.py` periodicamente, passando:

- `--connectionString`
- `--ProcessTable`
- `--ProcessKey`
- `--FinalDateCtrl`
- `--dias_atras`
- `--dias_frente`
- `--dias_filtro_previsao` (opcional, padrão: 2)
- `--evaluate_model` (opcional, para executar avaliação completa do modelo)

Esse nó pode ser um job do SQL Server Agent, um pipeline de orquestração ou um container agendado.

#### Exemplo de uso com avaliação:

```bash
python main.py --connectionString "DRIVER={SQL Server};SERVER=servidor;DATABASE=banco;UID=usuario;PWD=senha;" \
               --ProcessTable "dbo.stageProcessoAbsenteismoPredicao" \
               --ProcessKey "12345" \
               --FinalDateCtrl "2024-10-12" \
               --dias_atras 90 \
               --dias_frente 15 \
               --dias_filtro_previsao 5 \
               --evaluate_model
```

Este comando executará o pipeline completo incluindo avaliação do modelo, gerando métricas e matriz de confusão.

### 4.3 Validar e monitorar

- verificar se `dbo.AtualizaAbsenteismoPredicao` é executada com sucesso;
- checar se a tabela stage recebe registros corretamente;
- garantir que o dataset não contenha duplicatas indesejadas após `TRUNCATE`.

---

## 5. Resumo do estado atual

O processo já está funcional em código e preparado para produção, incluindo funcionalidade completa de avaliação do modelo com métricas e matriz de confusão. As principais pendências são:

- criação física das tabelas no ambiente de produção;
- criação do nó de processo que executa o script automaticamente;
- validação final com os dados reais de produção.
