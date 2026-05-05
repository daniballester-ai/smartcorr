# PLANO: Auditoria de Pipeline e Benchmark Competitivo (SmartCorr)

Este plano descreve as etapas para avaliar a integridade dos dados em cada estágio do pipeline e realizar um benchmark histórico (Backtesting) para validar a precisão das predições de ML contra o real e o baseline teórico (Erlang).

## 📋 Visão Geral
Atualmente, o sistema gera predições apenas para o futuro. Para validar a eficácia sem esperar o tempo passar, utilizaremos a técnica de **Backtesting**, simulando uma data de corte no passado e comparando o que o modelo "preveria" com o que de fato aconteceu no banco de dados.

---

## 🛠️ Tech Stack & Agentes
- **Agentes**: `@[backend-specialist]`, `@[database-architect]`
- **Skills**: `clean-code`, `database-design`, `python-patterns`
- **Ambiente**: PowerShell (Windows) + SQL Server

---

## 🎯 Critérios de Sucesso
- [ ] Auditoria completa de logs e dados em `data/interim` e `data/processed`.
- [ ] Execução bem-sucedida de inferência retroativa (Backtesting).
- [ ] Script SQL capaz de confrontar predições com dados reais de D-1 a D-7.
- [ ] Relatório de ganhos (ML vs Erlang) gerado.

---

## 🛤️ Divisão de Tarefas

### Fase 1: Auditoria de Pipeline (Logs e Estágios)
Nesta fase, verificaremos se os dados estão sendo transformados corretamente em cada etapa "etapa a etapa".

| ID | Tarefa | Agente | Instruções | INPUT → OUTPUT → VERIFY |
|:---|:---|:---|:---|:---|
| 1.1 | **Análise de Data Loading** | `backend-specialist` | Executar `src/data_loading/load_data.py` e verificar o volume de linhas extraídas. | SQL → `raw_data.csv` | Conferir log: "Total de registros carregados". |
| 1.2 | **Análise de Preprocessing** | `backend-specialist` | Inspecionar `data/interim/clean_data.csv`. Verificar tratamento de nulos e tipos de dados. | `raw_data.csv` → `clean_data.csv` | Logs de nulos removidos/preenchidos. |
| 1.3 | **Auditoria de Features** | `backend-specialist` | Avaliar `data/processed/train_data.csv`. Verificar se Lags e Médias Móveis estão corretas (não vazias). | `clean_data.csv` → `train_data.csv` | Presença de colunas `lag_1`, `v_hora_sen`, etc. |

### Fase 2: Estratégia de Backtesting (Validação do Passado)
Para não esperar o futuro, vamos "voltar no tempo" nas configurações.

| ID | Tarefa | Agente | Instruções | INPUT → OUTPUT → VERIFY |
|:---|:---|:---|:---|:---|
| 2.1 | **Configuração de Retroação** | `backend-specialist` | Alterar `params.yaml`: definir `data_corte_final` para **7 dias atrás**. | `params.yaml` | `data_corte_final` visível nos logs. |
| 2.2 | **Execução de Inferência Histórica** | `backend-specialist` | Rodar `run_inference.py`. Isso gerará predições para a semana passada (que já tem Real). | Modelo + Dados Históricos → `data/predictions/` | Arquivo CSV com datas passadas. |

### Fase 3: Benchmark & SQL Verification
Criação das ferramentas de comparação de performance.

| ID | Tarefa | Agente | Instruções | INPUT → OUTPUT → VERIFY |
|:---|:---|:---|:---|:---|
| 3.1 | **Script SQL de Extração Real** | `database-architect` | Criar script SQL que extrai `ID_PROGRAMA`, `DATA`, `HORA`, `NS_REAL` e `NS_BASELINE_ERLANG`. | Banco SQL Server → `benchmark_real.csv` | Resultado do SELECT batendo com OdsCorp. |
| 3.2 | **Script de Confronto (Python)** | `backend-specialist` | Criar script `scripts/benchmark_performance.py` para cruzar Previsão ML vs Real SQL. | `predictions.csv` + `benchmark_real.csv` → Tabela de Métricas | Cálculo de MAE/RMSE (ML vs Erlang). |

---

## 🏁 Fase X: Verificação Final
- [ ] Comparar `MAE(ML)` com `MAE(Erlang)`. O erro do ML deve ser menor.
- [ ] Verificar se há "Edge Cases" onde o Erlang ainda é melhor (ex: feriados).
- [ ] Validar se as métricas de treino (`metrics/*.json`) batem com o benchmark de inferência.

---
