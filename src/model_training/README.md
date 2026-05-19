# Model Training Module

> Treinamento do modelo XGBoost para predição de Nível de Serviço.

## Quick Start

```bash
# Executar standalone
python -m src.model_training.train_model

# Pipeline completo
python -m src.data_loading.load_data
python -m src.data_preprocessing.clean_data
python -m src.feature_engineering.build_features
python -m src.model_training.train_model
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
│                      load_data()                             │
│                  (Carrega e valida)                         │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    prepare_data()                            │
│              (Split temporal 80/20)                         │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                        train()                              │
│                    (XGBoost / RF)                          │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                      evaluate()                             │
│                  (Métricas R², RMSE)                       │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                     save_model()                           │
│              (model.pkl + metrics.json)                    │
└─────────────────────────────────────────────────────────────┘
```

## Pipeline Flow

| Step | Function | Description |
|------|----------|-------------|
| 1 | `main()` | Orquestra pipeline |
| 2 | `load_data()` | Carrega CSV e valida colunas |
| 3 | `prepare_data()` | Split temporal 80/20 |
| 4 | `train()` | Treina XGBoost ou RF |
| 5 | `evaluate()` | Calcula métricas |
| 6 | `save_model()` | Persiste modelo e métricas |

## Configuration

### params.yaml

```yaml
data:
  processed_train_path: data/processed/train_data.csv
  features:
    - Vol_Previsto
    - HC_Previsto
    # ... (25 features)
  target: NS_Real

model:
  path: models/model.pkl
  metrics_path: metrics/train_metrics.json
  type: XGBRegressor
  params:
    n_estimators: 100
    max_depth: 3
    learning_rate: 0.1
    alpha: 5
    reg_lambda: 5
    colsample_bytree: 0.8
    subsample: 0.8
    random_state: 42
    n_jobs: -1
    early_stopping_rounds: 10
```

### EarlyStopping

O XGBoost usa EarlyStopping para evitar overfitting:
- **Validação interna:** 10% do train_data
- **Patience:** 10 rounds sem melhoria
- **Benefício:** Para treino automaticamente quando modelo para de melhorar

## API Reference

### Public Functions

#### `load_config() -> dict`

Carrega configurações do `params.yaml`.

---

#### `load_data(train_path: str, features: list, target: str) -> tuple[pd.DataFrame, pd.DataFrame]`

Carrega dados e valida colunas.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| train_path | str | Yes | Caminho do CSV |
| features | list | Yes | Lista de features |
| target | str | Yes | Nome do target |

**Returns:**
- `tuple`: (X, y) DataFrames

---

#### `prepare_data(X, y, test_size=0.2) -> tuple`

Split temporal sem shuffle (preserva ordem cronológica).

**Parameters:**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| X | pd.DataFrame | Yes | Features |
| y | pd.Series | Yes | Target |
| test_size | float | 0.2 | Proporção de teste |

---

#### `train(X_train, y_train, config_modelo) -> model`

Treina modelo XGBoost ou RandomForest.

---

#### `evaluate(modelo, X_train, X_test, y_train, y_test, features) -> dict`

Calcula métricas de avaliação.

**Returns:**
```json
{
  "r2_train": 0.9037,
  "r2_test": 0.8816,
  "rmse_test": 0.1634,
  "mae_test": 0.0794,
  "feature_importances": {...}
}
```

---

#### `save_model(...) -> tuple`

Salva modelo (.pkl) e métricas (.json).

---

#### `main() -> None`

Orquestra pipeline completo.

### Private Functions

| Function | Purpose |
|----------|---------|
| (todas são públicas) | - |

## Métricas de Avaliação

### R² (Coeficiente de Determinação)

| Valor | Interpretação |
|-------|---------------|
| 1.0 | Predição perfeita |
| > 0.9 | Excelente |
| 0.7 - 0.9 | Bom |
| 0.5 - 0.7 | Razoável |
| < 0.5 | Ruim |

### RMSE (Root Mean Square Error)

Erro médio quadrático. Quanto menor, melhor.

### MAE (Mean Absolute Error)

Erro médio absoluto em pontos percentuais de NS.

## Output Files

### models/model.pkl

Modelo treinado (joblib). Usado pelo módulo de inference.

### metrics/train_metrics.json

```json
{
  "algoritmo": "XGBRegressor",
  "duracao_treino_segundos": 0.5,
  "linhas_treino": 9984,
  "linhas_teste": 2497,
  "r2_train": 0.9037,
  "r2_test": 0.8816,
  "rmse_test": 0.1634,
  "mae_test": 0.0794,
  "feature_importances": {
    "Vol_Previsto": 0.15,
    "HC_Previsto": 0.12,
    ...
  }
}
```

## Feature Importance

O modelo XGBoost calcula importância de cada feature:

```
Top Features:
  1. Vol_Previsto
  2. HC_Previsto
  3. Hora
  4. NS_Lag_1
  5. ...
```

## Split Strategy

```
┌────────────────────────────────────────────────────────────┐
│               feature_engineering                           │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  clean_data.csv → Split 80/20 POR DATA                    │
│                                                            │
│  TRAIN (80% das datas mais antigas):                      │
│    2026-03-13 a 2026-04-05                               │
│                                                            │
│  TEST (20% das datas mais recentes):                      │
│    2026-04-06 a 2026-04-11                               │
│                                                            │
│  Garante: datas do teste sao 100% diferentes do treino    │
└────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌────────────────────────────────────────────────────────────┐
│                    model_training                            │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  train_data.csv → Split interno 90/10 (para EarlyStopping) │
│                                                            │
│  Sem shuffle → Preserva ordem temporal                      │
└────────────────────────────────────────────────────────────┘
```

**Nota:** Split por data simula o cenário real de produção: "treinar com passado, prever futuro".

## Logging

```python
logger = logging.getLogger(__name__)
```

**Eventos:**

| Level | Message |
|-------|---------|
| INFO | Carregando dados de treino |
| INFO | Dados carregados: N registros |
| INFO | Treino: N linhas. Teste: N linhas |
| INFO | Iniciando treinamento com algoritmo |
| INFO | R² (Treino/Teste) |
| INFO | RMSE, MAE |
| INFO | Modelo salvo em |
| INFO | Métricas salvas em |
| WARNING | XGBoost não instalado |

## Requirements

```txt
pandas>=2.0.0
numpy>=1.24.0
pyyaml>=6.0
scikit-learn>=1.0.0
xgboost>=2.0.0
joblib>=1.0.0
```

## Related Documentation

- [Feature Engineering](../feature_engineering/README.md)
- [Inference](../inference/README.md)
- [Configuration](../params.yaml)
