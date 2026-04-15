# Feature Engineering Module

> Engenharia de features para o modelo de predição de Nível de Serviço.

## Quick Start

```bash
# Executar standalone
python -m src.feature_engineering.build_features

# Pipeline completo
python -m src.data_loading.load_data
python -m src.data_preprocessing.clean_data
python -m src.feature_engineering.build_features
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         main()                               │
│                   (Orquestração do Pipeline)                 │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                     build_features()                         │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────┐  │
│  │ _ensure_     │→ │ _create_     │→ │ _create_        │  │
│  │ datetime()   │  │ delta_       │  │ synthetic_      │  │
│  │              │  │ features()   │  │ features()      │  │
│  └──────────────┘  └──────────────┘  └─────────────────┘  │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────┐  │
│  │ _create_     │→ │ _create_      │→ │ _create_        │  │
│  │ rate_       │  │ perda_log_    │  │ lag_            │  │
│  │ features()  │  │ features()   │  │ features()      │  │
│  └──────────────┘  └──────────────┘  └─────────────────┘  │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                   _split_train_future()                      │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                       save_data()                           │
│     (train_data.csv + future_data.csv)                      │
└─────────────────────────────────────────────────────────────┘
```

## Pipeline Flow

| Step | Function                         | Description                                    |
| ---- | -------------------------------- | ---------------------------------------------- |
| 1    | `main()`                       | Carrega config, orquestra pipeline             |
| 2    | `build_features()`             | Executa todas as etapas de feature engineering |
| 3    | `_ensure_datetime()`           | Converte DataHora para datetime                |
| 4    | `_create_delta_features()`     | Cria deltas (real - previsto)                  |
| 5    | `_create_synthetic_features()` | Cria features combinadas                       |
| 6    | `_create_rate_features()`      | Cria taxas e proporções                      |
| 7    | `_create_perda_log_features()` | Cria features de perda de log                  |
| 8    | `_create_lag_features()`       | Cria lags (memória histórica)                |
| 9    | `_split_train_future()`        | Separa treino e futuro                         |
| 10   | `save_data()`                  | Salva CSVs                                     |

## Configuration

### params.yaml

```yaml
data:
  clean_path: data/interim/clean_data.csv        # Entrada
  processed_train_path: data/processed/train_data.csv   # Saída treino
  processed_test_path: data/processed/test_data.csv     # Saída teste
  processed_future_path: data/processed/future_data.csv # Saída futuro
```

## API Reference

### Public Functions

#### `load_config() -> dict`

Carrega configurações do `params.yaml`.

---

#### `build_features(df: pd.DataFrame) -> pd.DataFrame`

Executa pipeline completo de engenharia de features.

**Parameters:**

| Name | Type         | Required | Description                |
| ---- | ------------ | -------- | -------------------------- |
| df   | pd.DataFrame | Yes      | Dados limpos do clean_data |

**Returns:**

- `pd.DataFrame`: DataFrame com 70 features

---

#### `save_data(df_train, df_future, train_path, future_path) -> tuple`

Salva dados de treino e futuro em CSV.

---

#### `main() -> None`

Orquestra pipeline completo.

### Private Functions

| Function                         | Purpose                                              |
| -------------------------------- | ---------------------------------------------------- |
| `_ensure_datetime()`           | Converte DataHora para datetime                      |
| `_create_delta_features()`     | Deltas de volume, HC e TMA                           |
| `_create_synthetic_features()` | Pressão prevista, Indicador de sufoco               |
| `_create_rate_features()`      | Taxas de ABS, Turnover, Abandono, Ocupação, Pausas |
| `_create_perda_log_features()` | Taxas de perda de log                                |
| `_create_lag_features()`       | Lags de NS e indicadores                             |
| `_split_train_future()`        | Separa dados históricos de futuros                  |

## Features Geradas

### 1. Delta Features (Erro de Previsão)

| Feature              | Fórmula                          | Descrição         |
| -------------------- | --------------------------------- | ------------------- |
| `Delta_Volume`     | Vol_Real - Vol_Previsto           | Desvio de volume    |
| `Delta_HC`         | HC_Real_Equiv - HC_Previsto       | Desvio de HC        |
| `TMA_Real_Avg`     | Tempo_AHT_Real / Vol_Atendidas    | TMA real médio     |
| `TMA_Previsto_Avg` | Tempo_AHT_Previsto / Vol_Previsto | TMA previsto médio |
| `Delta_TMA`        | TMA_Real - TMA_Previsto           | Desvio de TMA       |

### 2. Synthetic Features (Causas Raiz)

#### Features de PRESSÃO DE DEMANDA

| Feature                     | Fórmula                                   | Descrição            | Importância    |
| --------------------------- | ------------------------------------------ | ---------------------- | --------------- |
| `Pressao_Prevista_Vol_HC` | Vol_Previsto / HC_Previsto                 | Volume por HC previsto | **24.6%** |
| `Vol_Por_Agente`          | Vol_Previsto / HC_Previsto                 | Volume por agente      | 0.5%            |
| `Indicador_Sufoco`        | Tempo_AHT_Previsto / (HC_Previsto × 1800) | Sufoco previsto        | 1.8%            |

#### Features de ESCALA

| Feature               | Fórmula                                                     | Descrição               | Importância |
| --------------------- | ------------------------------------------------------------ | ------------------------- | ------------ |
| `Desvio_Escala_Pct` | (HC_Real - HC_Previsto) / HC_Previsto                        | Desvio de escala          | 0%           |
| `Razao_Escala`      | HC_Real / HC_Previsto                                        | Proporção real/prevista | 0%           |
| `Margem_Capacidade` | (HC_Previsto × 1800 - Vol_Previsto) / (HC_Previsto × 1800) | Folga operacional         | 0.5%         |

#### Features de CAPACIDADE

| Feature             | Fórmula                     | Descrição   | Importância |
| ------------------- | ---------------------------- | ------------- | ------------ |
| `Taxa_Sobrecarga` | Vol_Real / (HC_Real × 1800) | Overload real | 0%           |

### Interpretação de Causas vs Sintomas

```
SINTOMA (efeito):
└── TME_Real_Avg_Lag_1 = 36.2%  ← resultado do NS ruim

CAUSA (origem):
├── Pressao_Prevista_Vol_HC = 24.6%  ← pressão de demanda
├── Desvio_Volume_Pct_Lag_1 = 14.0% ← desvio de volume
└── Vol_Previsto = 7.9%              ← volume absoluto
```

**Benefício:** o modelo pode adverter:

- "HC insuficiente para demanda prevista" → causa
- "Escala desviou do planejado" → causa
- "TME alto foi sintoma" → consequência

### 3. Rate Features

| Feature                 | Fórmula                     | Descrição        |
| ----------------------- | ---------------------------- | ------------------ |
| `ABS_Taxa_Daily`      | ABS_Tempo / ABS_Escala       | Taxa de ABS        |
| `Turnover_Taxa_Daily` | Desligados / Ativos          | Taxa de turnover   |
| `Taxa_Abandono`       | Vol_Abandono / Vol_Real      | Taxa de abandono   |
| `TME_Real_Avg`        | Tempo_Espera / Vol_Real      | TME médio         |
| `Taxa_Ocupacao`       | Tempo_AHT / (HC × 1800)     | Ocupação do time |
| `Taxa_Pausa_Tecnica`  | Pausa_Tecnica / (HC × 1800) | Pausa técnica     |
| `Taxa_Pausa_Pessoal`  | Pausa_Pessoal / (HC × 1800) | Pausa pessoal      |
| `Taxa_Pausa_Gestao`   | Pausa_Gestao / (HC × 1800)  | Pausa gestão      |
| `Desvio_HC_Pct`       | Delta_HC / HC_Previsto       | % desvio HC        |
| `Desvio_Volume_Pct`   | Delta_Volume / Vol_Previsto  | % desvio volume    |

### 4. Perda Log Features (Daily Broadcast)

| Feature                    | Fórmula           | Descrição                 |
| -------------------------- | ------------------ | --------------------------- |
| `PerdaLog_Taxa_Daily`    | PerdaLog / PPH     | Taxa de perda de log        |
| `TechIssues_Taxa_Daily`  | TechIssues / PPH   | Taxa de indisponibilidade   |
| `NewHire_Pct_Daily`      | NewHire / HC_Total | % novatos                   |
| `AgentIssues_Taxa_Daily` | AgentIssues / PPH  | Taxa de problemas do agente |

### 5. Lag Features (Histórico)

| Feature                      | Descrição             | Uso                    |
| ---------------------------- | ----------------------- | ---------------------- |
| `NS_Lag_1`                 | NS Real do intervalo -1 | Padrão imediato       |
| `NS_Lag_2`                 | NS Real do intervalo -2 | Padrão médio         |
| `NS_Lag_3`                 | NS Real do intervalo -3 | Padrão distante       |
| `Taxa_Abandono_Lag_1`      | Taxa abandono -1        | Sinais de fuga         |
| `TME_Real_Avg_Lag_1`       | TME -1                  | Gargalo imediato       |
| `Taxa_Ocupacao_Lag_1`      | Ocupação -1           | Utilização anterior  |
| `Taxa_Pausa_Tecnica_Lag_1` | Pausa técnica -1       | Ineficiência técnica |
| `Taxa_Pausa_Pessoal_Lag_1` | Pausa pessoal -1        | Ineficiência pessoal  |
| `Taxa_Pausa_Gestao_Lag_1`  | Pausa gestão -1        | Ineficiência gestão  |
| `Desvio_HC_Pct_Lag_1`      | Desvio HC % -1          | Desvio anterior        |
| `Desvio_Volume_Pct_Lag_1`  | Desvio Volume % -1      | Desvio anterior        |
| `Delta_TMA_Lag_1`          | Delta TMA -1            | Desvio tempo anterior  |

## Split Strategy

```
┌────────────────────────────────────────────────────────────┐
│                     DADOS ORIGINAIS                          │
│                      (20,383 linhas)                        │
└─────────────────────────┬──────────────────────────────────┘
                          │
                          ▼
          ┌────────────────────────────────────┐
          │  Vol_Real > 0 = "Histórico"       │
          │  Último registro com Vol_Real      │
          └──────────────┬─────────────────────┘
                         │
           ┌─────────────┴─────────────┐
           │                           │
           ▼                           ▼
    ┌─────────────────────┐   ┌──────────────┐
    │   TRAIN + TEST      │   │   FUTURO     │
    │  (12,481 linhas)    │   │ (7,902 linhas)│
    └──────────┬──────────┘   └──────────────┘
               │
               ▼
    ┌────────────────────────────────────┐
    │     SPLIT POR DATA (80/20)         │
    │                                      │
    │  TRAIN: Datas mais ANTIGAS        │
    │  TEST:  Datas mais RECENTES         │
    │                                      │
    │  Exemplo:                            │
    │  Train: 2026-03-13 a 2026-04-05    │
    │  Test:  2026-04-06 a 2026-04-11    │
    └────────────────────────────────────┘
```

**Nota:** Split por data garante que teste usa dados de períodos completamente diferentes do treino, simulando o cenário real de produção.

## Para Que Serve Cada Dataset?

### train_data.csv (Dados Históricos)

- **Conteúdo:** Dados do passado até hoje
- **Tem:** `Vol_Real`, `Vol_Previsto`, `NS_Real` (resposta real)
- **Uso:** Treinar o modelo aprender padrões

### test_data.csv (Dados de Validação)

- **Conteúdo:** 20% das datas mais recentes (separadas por data)
- **Tem:** `Vol_Real`, `Vol_Previsto`, `NS_Real`
- **Datas:** 2026-04-06 a 2026-04-11 (diferentes do treino)
- **Uso:** Avaliar modelo de forma consistente entre execuções

**Por que separar por data?**
```
TREINO: 2026-03-13 a 2026-04-05  (datas antigas)
TESTE:  2026-04-06 a 2026-04-11  (datas recentes)

Garante que modelo é testado em PERIODOS DIFERENTES,
simulando o cenário real de produção.
```

### future_data.csv (Dados Futuros)

- **Conteúdo:** Previsões do sistema SmartCorr (datas futuras)
- **Tem:** Apenas `Vol_Previsto` (ainda não aconteceu)
- **Datas:** 2026-04-12 a 2026-04-30
- **Uso:** Gerar predições ANTES de acontecer

## Fluxo Completo

```
┌─────────────────────────────────────────────────────────────────┐
│                         TREINAMENTO                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  train_data.csv ──→ Treinar modelo (com EarlyStopping)         │
│  test_data.csv  ──→ Avaliar modelo (métricas finais)           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        INFERÊNCIA                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  future_data.csv ──→ Gerar predições ANTES de acontecer        │
│                      (NS_Previsto para 12-30/04)               │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      COMPARAÇÃO POST-HOC                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Quando chegar 2026-04-15:                                     │
│    - Comparar NS_Previsto (do modelo) vs NS_Real (do banco)    │
│    - Verificar acurácia do modelo                              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

| Objetivo                                | Dataset             | Quando               |
| --------------------------------------- | ------------------- | -------------------- |
| Treinar modelo                          | `train_data.csv`  | Agora                |
| Avaliar modelo                          | `test_data.csv`   | Agora                |
| **Gerar predições antecipadas** | `future_data.csv` | Agora                |
| Testar/acertividade real                | Comparar depois     | Quando chegar a data |

## Input/Output

| Etapa | Input                        | Output                    |
| ----- | ---------------------------- | ------------------------- |
| 1     | `clean_data.csv` (37 cols) | -                         |
| 2     | -                            | `train_data.csv` (~80%) |
| 3     | -                            | `test_data.csv` (~20%)  |
| 4     | -                            | `future_data.csv`       |

## Logging

```python
logger = logging.getLogger(__name__)
```

**Eventos:**

| Level   | Message                                 |
| ------- | --------------------------------------- |
| INFO    | Colunas antes do feature engineering: N |
| INFO    | Colunas após feature engineering: N    |
| INFO    | Dados de treino salvos em: caminho      |
| INFO    | Dados futuros salvos em: caminho        |
| WARNING | DataFrame vazio                         |
| WARNING | Nenhum dado de treino encontrado        |

## Requirements

```txt
pandas>=2.0.0
numpy>=1.24.0
pyyaml>=6.0
```

## Related Documentation

- [Data Preprocessing](../data_preprocessing/README.md)
- [Model Training](../model_training/README.md)
- [Configuration](../params.yaml)
