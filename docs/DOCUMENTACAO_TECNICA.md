# SmartCorr - Documentação Técnica

> Ferramenta de Correlação Inteligente para Predição de Nível de Serviço em Call Centers

## Índice

1. [Arquitetura do Pipeline](#arquitetura-do-pipeline)
2. [Módulos](#módulos)
3. [Features](#features)
4. [Tabela de Features](#tabela-de-features)
5. [Persistência no SQL Server](#persistência-no-sql-server)
6. [Parâmetros](#parâmetros)
7. [Configuração](#configuração)

---

## Arquitetura do Pipeline

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  SQL Server │ ──▶ │  load_data  │ ──▶ │ clean_data  │ ──▶ │build_features│ ──▶ │train_model  │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
                                                                                         │
                                                                                         ▼
                    ┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
                    │ SQL Server  │ ◀── │  predict    │ ◀── │build_features│     │evaluate_model│
                    │  (SHAP)     │     └─────────────┘     │(future only)│     └─────────────┘
                    └─────────────┘                           └─────────────┘
```

### Fluxos de Execução

| Modo          | Comando                             | Descrição                 |
| ------------- | ----------------------------------- | --------------------------- |
| `training`  | `dvc repro`                       | Pipeline completo de treino |
| `inference` | `python -m src.inference.predict` | Apenas predição           |

---

## Módulos

### 1. data_loading (Extração)

**Arquivo:** `src/data_loading/load_data.py`

| Aspecto                 | Detalhe                                                |
| ----------------------- | ------------------------------------------------------ |
| **Entrada**       | SQL Server (vw_SmartCorr_Principal, FatoTempoSistemas) |
| **Saída**        | `data/raw/raw_history.csv`                           |
| **Dependências** | `config/queries.ini`                                 |

**Função Principal:**

```python
def fetch_data(janela_dias, queries_file, data_corte_final, mode, future_days) -> pd.DataFrame
```

**Parâmetros do módulo:**

| Parâmetro           | Tipo | Padrão      | Descrição                   |
| -------------------- | ---- | ------------ | ----------------------------- |
| `mode`             | str  | `training` | `training` ou `inference` |
| `janela_dias`      | int  | 30           | Dias históricos (training)   |
| `future_days`      | int  | 7            | Dias futuros (inference)      |
| `data_corte_final` | str  | null         | Data de corte                 |

**Queries utilizadas:**

- `smartcorr`: View principal com volumetria e capacidade
- `perda_log`: FatoTempoSistemas com indicadores diários

---

### 2. data_preprocessing (Limpeza)

**Arquivo:** `src/data_preprocessing/clean_data.py`

| Aspecto                 | Detalhe                           |
| ----------------------- | --------------------------------- |
| **Entrada**       | `data/raw/raw_history.csv`      |
| **Saída**        | `data/interim/clean_data.csv`   |
| **Dependências** | `src/data_loading/load_data.py` |

**Função Principal:**

```python
def clean_data(df) -> pd.DataFrame
```

**Transformações aplicadas:**

1. Preenchimento de valores ausentes
2. Remoção de outliers de ociosidade (HC_Previsto > 0)
3. Cálculo do target (NS_Real)
4. Conversão de tipos

---

### 3. feature_engineering (Engenharia de Features)

**Arquivo:** `src/feature_engineering/build_features.py`

| Aspecto                 | Detalhe                                                                   |
| ----------------------- | ------------------------------------------------------------------------- |
| **Entrada**       | `data/interim/clean_data.csv`                                           |
| **Saída**        | `data/processed/train_data.csv`, `test_data.csv`, `future_data.csv` |
| **Dependências** | `src/data_preprocessing/clean_data.py`                                  |

**Função Principal:**

```python
def build_features(df) -> pd.DataFrame
```

**Pipeline de Features:**

1. `_ensure_datetime()` - Converte DataHora para datetime
2. `_create_delta_features()` - Calcula deltas (Vol_Real - Vol_Previsto)
3. `_create_synthetic_features()` - Features de causa raiz
4. `_create_rate_features()` - Taxas e proporções
5. `_create_perda_log_features()` - Indicadores de perda de log
6. `_create_lag_features()` - Features temporais (lags)

**Split de Dados (modo training):**

```python
_split_train_future()  # Separa real vs futuro
_split_train_test()    # Split temporal 80/20
```

---

### 4. model_training (Treinamento)

**Arquivo:** `src/model_training/train_model.py`

| Aspecto                 | Detalhe                                              |
| ----------------------- | ---------------------------------------------------- |
| **Entrada**       | `data/processed/train_data.csv`                    |
| **Saída**        | `models/model.pkl`, `metrics/train_metrics.json` |
| **Dependências** | `src/feature_engineering/build_features.py`        |

**Função Principal:**

```python
def train(X, y, config_modelo, val_size) -> tuple[modelo, X_train, y_train, X_val, y_val]
```

**Algoritmo:** XGBRegressor com EarlyStopping

**Métricas salvas:**

| Métrica                | Descrição                    |
| ----------------------- | ------------------------------ |
| `r2_train`            | R² no conjunto de treino      |
| `r2_val`              | R² no conjunto de validação |
| `mse_val`             | MSE na validação             |
| `rmse_val`            | RMSE na validação            |
| `mae_val`             | MAE na validação             |
| `feature_importances` | Importância das features      |

---

### 5. model_evaluation (Avaliação)

**Arquivo:** `src/model_evaluation/evaluate_model.py`

| Aspecto                 | Detalhe                                                |
| ----------------------- | ------------------------------------------------------ |
| **Entrada**       | `models/model.pkl`, `data/processed/test_data.csv` |
| **Saída**        | `metrics/evaluation.json`                            |
| **Dependências** | `src/model_training/train_model.py`                  |

**Função Principal:**

```python
def evaluate(modelo, X_test, y_test, features) -> dict
```

**Métricas de avaliação:**

| Métrica                | Descrição                       |
| ----------------------- | --------------------------------- |
| `r2_score`            | Coeficiente de determinação     |
| `rmse`                | Root Mean Square Error            |
| `mse`                 | Mean Square Error                 |
| `mae`                 | Mean Absolute Error               |
| `feature_importances` | Importância no conjunto de teste |

---

### 6. inference (Predição)

**Arquivo:** `src/inference/predict.py`

| Aspecto                 | Detalhe                                                       |
| ----------------------- | ------------------------------------------------------------- |
| **Entrada**       | `data/processed/future_data.csv`, `models/model.pkl`      |
| **Saída**        | SQL Server:`[OdsCorp].[SmartCorr].[FactSmartCorr_Previsao]` |
| **Dependências** | `src/model_training/train_model.py`                         |

**Função Principal:**

```python
def main() -> None
```

**Pipeline:**

1. Carrega modelo treinado
2. Lê dados futuros
3. Faz predição com XGBoost
4. Calcula SHAP values
5. Processa impactos por pilar
6. Grava no SQL Server

---

## Features

### Categorias de Features

#### 1. METAS (Dados Disponíveis Antes do Fato)

| Feature                      | Descrição                         | SQL Server |
| ---------------------------- | ----------------------------------- | ---------- |
| `Vol_Previsto`             | Volume de ligações previsto       | ✅         |
| `HC_Previsto`              | Headcount previsto                  | ✅         |
| `Tempo_AHT_Previsto_Total` | Tempo total de atendimento previsto | ✅         |

#### 2. CONTEXTO TEMPORAL (Padrões Sazonais)

| Feature       | Descrição         | SQL Server |
| ------------- | ------------------- | ---------- |
| `Hora`      | Hora do dia (0-23)  | ❌         |
| `DiaSemana` | Dia da semana (0-6) | ❌         |

#### 3. INDICADORES DE RH / QUALIDADE

| Feature                 | Descrição                | SQL Server |
| ----------------------- | -------------------------- | ---------- |
| `ABS_Taxa_Daily`      | Taxa de ABS (Absenteísmo) | ✅         |
| `Turnover_Taxa_Daily` | Taxa de turnover           | ✅         |
| `Ferias_Qtd_Daily`    | Quantidade de férias      | ✅         |
| `Faltas_Qtd_Daily`    | Quantidade de faltas       | ✅         |
| `WAHA_Qtd_Daily`      | Quantidade de WAHA         | ✅         |

#### 4. SINAIS DE FUMAÇA (Lags - Imediato Passado)

| Feature                 | Descrição               | SQL Server |
| ----------------------- | ------------------------- | ---------- |
| `Taxa_Abandono_Lag_1` | Taxa de abandono no Lag 1 | ✅         |

#### 5. EFICIÊNCIA E DESVIOS (Lags)

| Feature                      | Descrição                  | SQL Server |
| ---------------------------- | ---------------------------- | ---------- |
| `TME_Real_Avg_Lag_1`       | Tempo médio de espera Lag 1 | ✅         |
| `Taxa_Ocupacao_Lag_1`      | Taxa de ocupação Lag 1     | ✅         |
| `Taxa_Pausa_Tecnica_Lag_1` | Pausa técnica Lag 1         | ✅         |
| `Taxa_Pausa_Pessoal_Lag_1` | Pausa pessoal Lag 1          | ✅         |
| `Taxa_Pausa_Gestao_Lag_1`  | Pausa gestão Lag 1          | ✅         |
| `Desvio_HC_Pct_Lag_1`      | Desvio HC % Lag 1            | ✅         |
| `Desvio_Volume_Pct_Lag_1`  | Desvio volume % Lag 1        | ✅         |
| `Delta_TMA_Lag_1`          | Variação TMA Lag 1         | ✅         |

#### 6. FEATURES SINTÉTICAS (Causas Raiz)

| Feature                     | Descrição         | Fórmula                                  | SQL Server |
| --------------------------- | ------------------- | ----------------------------------------- | ---------- |
| `Pressao_Prevista_Vol_HC` | Pressão Volume/HC  | `Vol_Previsto / HC_Previsto`            | ❌         |
| `Indicador_Sufoco`        | Indicador de sufoco | `TMA_Previsto / (HC_Previsto * 1800)`   | ❌         |
| `Vol_Por_Agente`          | Volume por agente   | `Vol_Previsto / HC_Previsto`            | ❌         |
| `Margem_Capacidade`       | Folga capacidade    | `(Cap_Teorica - Vol) / Cap_Teorica`     | ❌         |
| `Desvio_Escala_Pct`       | Desvio escala %     | `(HC_Real - HC_Previsto) / HC_Previsto` | ❌         |
| `Razao_Escala`            | Razão escala       | `HC_Real / HC_Previsto`                 | ❌         |
| `Taxa_Sobrecarga`         | Taxa de sobrecarga  | `Vol_Real / (HC_Real * 1800)`           | ❌         |

#### 7. INDICADORES DE PERDA DE LOG (Diários)

| Feature                    | Descrição                 | SQL Server |
| -------------------------- | --------------------------- | ---------- |
| `PerdaLog_Taxa_Daily`    | Taxa de perda de log        | ✅         |
| `TechIssues_Taxa_Daily`  | Taxa de problemas técnicos | ✅         |
| `NewHire_Pct_Daily`      | % de novatos                | ✅         |
| `AgentIssues_Taxa_Daily` | Taxa de problemas do agente | ✅         |

---

## Tabela de Features

| #     | Feature                  | Categoria  | Importância | SQL Server |
| ----- | ------------------------ | ---------- | ------------ | ---------- |
| 1     | TME_Real_Avg_Lag_1       | Lag        | 36.2%        | ✅         |
| 2     | Pressao_Prevista_Vol_HC  | Saúde Operacional | 24.6%        | ❌         |
| 3     | Desvio_Volume_Pct_Lag_1  | Lag        | 14.0%        | ✅         |
| 4     | Vol_Previsto             | Meta       | 7.9%         | ✅         |
| 5     | NewHire_Pct_Daily        | Perda Log  | 3.3%         | ✅         |
| 6     | Delta_TMA_Lag_1          | Lag        | 2.7%         | ✅         |
| 7     | Indicador_Sufoco         | Saúde Operacional | 1.8%         | ❌         |
| 8     | PerdaLog_Taxa_Daily      | Perda Log  | 1.4%         | ✅         |
| 9     | Ferias_Qtd_Daily         | RH         | 1.3%         | ✅         |
| 10    | Taxa_Abandono_Lag_1      | Lag        | 1.1%         | ✅         |
| 11    | Tempo_AHT_Previsto_Total | Meta       | 0.9%         | ✅         |
| 12    | HC_Previsto              | Meta       | 0.8%         | ✅         |
| 13    | DiaSemana                | Contexto   | 0.6%         | ❌         |
| 14    | Faltas_Qtd_Daily         | RH         | 0.6%         | ✅         |
| 15    | Vol_Por_Agente           | Saúde Operacional | 0.5%         | ❌         |
| 16    | ABS_Taxa_Daily           | RH         | 0.5%         | ✅         |
| 17    | Margem_Capacidade        | Saúde Operacional | 0.5%         | ❌         |
| 18    | AgentIssues_Taxa_Daily   | Perda Log  | 0.4%         | ✅         |
| 19    | Hora                     | Contexto   | 0.3%         | ❌         |
| 20    | Turnover_Taxa_Daily      | RH         | 0.3%         | ✅         |
| 21-30 | *Demais features*      | -          | 0%           | -          |

---

## Persistência no SQL Server

### Tabela: `[OdsCorp].[SmartCorr].[FactSmartCorr_Previsao]`

| Coluna                   | Tipo          | Descrição                 | Feature Origem               |
| ------------------------ | ------------- | --------------------------- | ---------------------------- |
| DataRef                  | date          | Data de referência         | -                            |
| Intervalo                | time          | Intervalo do dia            | -                            |
| CodPrograma              | int           | Código do programa         | -                            |
| Canal                    | int           | Código do canal            | -                            |
| NS_Previsto_SmartCorr    | decimal(5,4)  | Nível de Serviço previsto | Predição                   |
| Vol_Previsto             | int           | Volume previsto             | `Vol_Previsto`             |
| HC_Previsto              | int           | Headcount previsto          | `HC_Previsto`              |
| TMA_Previsto_Avg         | decimal(10,2) | TMA médio previsto         | `Tempo_AHT_Previsto_Total` |
| NS_Lag_1                 | decimal(5,4)  | NS do Lag 1                 | Calculado                    |
| TME_Real_Lag_1           | decimal(10,4) | TME real Lag 1              | `TME_Real_Avg_Lag_1`       |
| Desvio_Volume_Pct_Lag_1  | decimal(10,4) | Desvio volume %             | `Desvio_Volume_Pct_Lag_1`  |
| Impacto_Pilar_Volumetria | decimal(5,4)  | Impacto SHAP pilar          | SHAP                         |
| Impacto_Pilar_Pessoas    | decimal(5,4)  | Impacto SHAP pilar          | SHAP                         |
| Impacto_Pilar_TMA        | decimal(5,4)  | Impacto SHAP pilar          | SHAP                         |
| Impacto_Pilar_Contexto   | decimal(5,4)  | Impacto SHAP pilar          | SHAP                         |
| Ofensor_1_Nome           | varchar(100)  | Nome do ofensor 1           | SHAP                         |
| Ofensor_1_Pilar          | varchar(50)   | Pilar do ofensor 1          | SHAP                         |
| Ofensor_1_Impacto        | decimal(5,4)  | Impacto do ofensor 1        | SHAP                         |
| Ofensor_2_Nome           | varchar(100)  | Nome do ofensor 2           | SHAP                         |
| Ofensor_2_Pilar          | varchar(50)   | Pilar do ofensor 2          | SHAP                         |
| Ofensor_2_Impacto        | decimal(5,4)  | Impacto do ofensor 2        | SHAP                         |
| Ofensor_3_Nome           | varchar(100)  | Nome do ofensor 3           | SHAP                         |
| Ofensor_3_Pilar          | varchar(50)   | Pilar do ofensor 3          | SHAP                         |
| Ofensor_3_Impacto        | decimal(5,4)  | Impacto do ofensor 3        | SHAP                         |
| Impulsionador_1_Nome     | varchar(100)  | Nome do impulsionador 1     | SHAP                         |
| Impulsionador_1_Pilar    | varchar(50)   | Pilar do impulsionador 1    | SHAP                         |
| Impulsionador_1_Impacto  | decimal(5,4)  | Impacto do impulsionador 1  | SHAP                         |
| Impulsionador_2_Nome     | varchar(100)  | Nome do impulsionador 2     | SHAP                         |
| Impulsionador_2_Pilar    | varchar(50)   | Pilar do impulsionador 2    | SHAP                         |
| Impulsionador_2_Impacto  | decimal(5,4)  | Impacto do impulsionador 2  | SHAP                         |
| Impulsionador_3_Nome     | varchar(100)  | Nome do impulsionador 3     | SHAP                         |
| Impulsionador_3_Pilar    | varchar(50)   | Pilar do impulsionador 3    | SHAP                         |
| Impulsionador_3_Impacto  | decimal(5,4)  | Impacto do impulsionador 3  | SHAP                         |
| DataHora_Atualizacao     | datetime      | Data/hora da atualização  | DEFAULT GETDATE()            |

---

## Parâmetros

### params.yaml

```yaml
data:
  mode: inference              # 'training' ou 'inference'
  queries_file: config/queries.ini
  raw_path: data/raw/raw_history.csv
  clean_path: data/interim/clean_data.csv
  processed_train_path: data/processed/train_data.csv
  processed_test_path: data/processed/test_data.csv
  processed_future_path: data/processed/future_data.csv
  test_size: 0.2              # Proporção para teste
  janela_dias: 30             # Janela histórica (training)
  future_days: 7              # Dias futuros (inference)
  data_corte_final: null     # Data de corte opcional
  target: NS_Real             # Variável alvo
  features: [30 features]    # Lista de features

model:
  path: models/model.pkl
  metrics_path: metrics/train_metrics.json
  type: XGBRegressor
  params:
    n_estimators: 100
    max_depth: 4
    learning_rate: 0.1
    alpha: 1
    reg_lambda: 1
    colsample_bytree: 0.6
    subsample: 0.6
    random_state: 42
    n_jobs: -1
    early_stopping_rounds: 15
```

---

## Configuração

### Estrutura de Diretórios

```
SmartCorr/
├── config/
│   └── queries.ini           # Queries SQL
├── src/
│   ├── data_loading/
│   ├── data_preprocessing/
│   ├── feature_engineering/
│   ├── model_training/
│   ├── model_evaluation/
│   └── inference/
├── data/
│   ├── raw/                  # Dados brutos
│   ├── interim/              # Dados intermediários
│   └── processed/            # Dados processados
├── models/                   # Modelos treinados
├── metrics/                  # Métricas
├── docs/                     # Documentação
├── params.yaml               # Parâmetros
└── dvc.yaml                  # Pipeline DVC
```

### Variáveis de Ambiente

| Variável                | Descrição                         |
| ------------------------ | ----------------------------------- |
| `MLFLOW_EXPERIMENT_ID` | ID do experimento MLflow (opcional) |
| `DVC_EXP_NAME`         | Nome do experimento DVC (opcional)  |

---

## DVC Pipeline

### Stages

```bash
# Executar pipeline completo (training)
dvc repro

# Executar estágio específico
dvc repro load_data
dvc repro preprocess_data
dvc repro engineer_features
dvc repro train
dvc repro evaluate

# Listar estágios
dvc stage list
```

---

## Uso

### Modo Training (Treino do Modelo)

1. Configure `params.yaml` com `mode: training`
2. Execute:

```bash
dvc repro
```

### Modo Inference (Predição)

1. Configure `params.yaml` com `mode: inference`
2. Execute pipeline de inferência:

```bash
python -m src.data_loading.load_data
python -m src.data_preprocessing.clean_data
python -m src.feature_engineering.build_features
python -m src.inference.predict
```

---

## Métricas do Modelo

### Resultados Atuais

| Métrica         | Valor  | Avaliação   |
| ---------------- | ------ | ------------- |
| R² Treino       | 0.9304 | ✅ Excelente  |
| R² Validação  | 0.8899 | ✅ Bom        |
| R² Teste        | 0.8747 | ✅ Bom        |
| Gap Treino-Teste | 0.05   | ✅ Adequado   |
| RMSE             | 0.1622 | ✅ Aceitável |
| MAE              | 0.0768 | ✅ Bom        |

---

## Pilares Analíticos (SHAP)

| Pilar                 | Features                                                       | Impacto |
| --------------------- | -------------------------------------------------------------- | ------- |
| `Volumetria`        | Vol_Previsto, Taxa_Abandono_Lag_1, Desvio_Volume_Pct_Lag_1     | Alto    |
| `Pessoas`           | HC_Previsto, ABS_Taxa, Turnover, Ferias, Faltas, WAHA, NewHire | Médio  |
| `TMA`               | Tempo_AHT_Previsto_Total, TME_Real_Avg_Lag_1, Delta_TMA_Lag_1  | Alto    |
| `Saude_Operacional`       | Pressao_Prevista_Vol_HC, Indicador_Sufoco, Margem_Capacidade   | Alto    |
| `Contexto_Temporal` | Hora, DiaSemana                                                | Baixo   |

---

## DDL - Tabela SQL Server

```sql
CREATE TABLE [SmartCorr].[FactSmartCorr_Previsao](
    [DataRef] [date] NOT NULL,
    [Intervalo] [time](7) NOT NULL,
    [CodPrograma] [int] NOT NULL,
    [Canal] [int] NOT NULL,
    [NS_Previsto_SmartCorr] [decimal](5, 4) NULL,
    [Vol_Previsto] [int] NULL,
    [HC_Previsto] [int] NULL,
    [TMA_Previsto_Avg] [decimal](10, 2) NULL,
    [NS_Lag_1] [decimal](5, 4) NULL,
    [TME_Real_Lag_1] [decimal](10, 4) NULL,
    [Desvio_Volume_Pct_Lag_1] [decimal](10, 4) NULL,
    [Impacto_Pilar_Volumetria] [decimal](5, 4) NULL,
    [Impacto_Pilar_Pessoas] [decimal](5, 4) NULL,
    [Impacto_Pilar_TMA] [decimal](5, 4) NULL,
    [Impacto_Pilar_Contexto] [decimal](5, 4) NULL,
    [Ofensor_1_Nome] [varchar](100) NULL,
    [Ofensor_1_Pilar] [varchar](50) NULL,
    [Ofensor_1_Impacto] [decimal](5, 4) NULL,
    [Ofensor_2_Nome] [varchar](100) NULL,
    [Ofensor_2_Pilar] [varchar](50) NULL,
    [Ofensor_2_Impacto] [decimal](5, 4) NULL,
    [Ofensor_3_Nome] [varchar](100) NULL,
    [Ofensor_3_Pilar] [varchar](50) NULL,
    [Ofensor_3_Impacto] [decimal](5, 4) NULL,
    [Impulsionador_1_Nome] [varchar](100) NULL,
    [Impulsionador_1_Pilar] [varchar](50) NULL,
    [Impulsionador_1_Impacto] [decimal](5, 4) NULL,
    [Impulsionador_2_Nome] [varchar](100) NULL,
    [Impulsionador_2_Pilar] [varchar](50) NULL,
    [Impulsionador_2_Impacto] [decimal](5, 4) NULL,
    [Impulsionador_3_Nome] [varchar](100) NULL,
    [Impulsionador_3_Pilar] [varchar](50) NULL,
    [Impulsionador_3_Impacto] [decimal](5, 4) NULL,
    [DataHora_Atualizacao] [datetime] NULL DEFAULT (getdate())
)
```

---

## Requisitos

```
pandas>=2.0.0
numpy>=1.24.0
scikit-learn>=1.0.0
xgboost>=2.0.0
shap>=0.40.0
joblib>=1.0.0
pyyaml>=6.0
pyodbc>=5.0.0
dvc>=3.0.0
```

---

*Documentação gerada em: 12/04/2026*
