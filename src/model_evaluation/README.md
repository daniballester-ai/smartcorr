# Model Evaluation Module

> Avaliação de modelo treinado em dados holdout.

## Quick Start

```bash
# Executar standalone
python -m src.model_evaluation.evaluate_model

# Pipeline completo
python -m src.data_loading.load_data
python -m src.data_preprocessing.clean_data
python -m src.feature_engineering.build_features
python -m src.model_training.train_model
python -m src.model_evaluation.evaluate_model
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
│                      load_model()                             │
│                 (Carrega .pkl do disco)                     │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                      load_data()                             │
│                   (Carrega CSV e valida)                   │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                   prepare_holdout()                           │
│              (Split temporal 80/20, sem shuffle)             │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                       evaluate()                             │
│               (Calcula métricas no holdout)                 │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                     save_metrics()                           │
│                     (Salva .json)                          │
└─────────────────────────────────────────────────────────────┘
```

## Pipeline Flow

| Step | Function | Description |
|------|----------|-------------|
| 1 | `main()` | Orquestra pipeline |
| 2 | `load_model()` | Carrega modelo .pkl |
| 3 | `load_data()` | Carrega CSV e valida |
| 4 | `prepare_holdout()` | Split temporal 80/20 |
| 5 | `evaluate()` | Métricas no holdout |
| 6 | `save_metrics()` | Salva evaluation.json |

## Configuration

### params.yaml

```yaml
model:
  path: models/model.pkl
  metrics_path: metrics/train_metrics.json
```

## API Reference

### Public Functions

#### `load_config() -> dict`

Carrega configurações do `params.yaml`.

---

#### `load_model(model_path: str) -> Any`

Carrega modelo treinado do disco.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| model_path | str | Yes | Caminho para .pkl |

**Returns:**
- Modelo carregado (joblib)

---

#### `load_data(train_path: str, features: list, target: str) -> tuple`

Carrega dados e valida colunas.

---

#### `prepare_holdout(X, y, test_size=0.2) -> tuple`

Split temporal para holdout (sem shuffle).

---

#### `evaluate(modelo, X_holdout, y_holdout) -> dict`

Avalia modelo e retorna métricas.

**Returns:**
```json
{
  "r2_score": 0.7924,
  "rmse": 0.2127,
  "mse": 0.0453,
  "mae": 0.1160,
  "n_amostras_holdout": 2497
}
```

---

#### `save_metrics(metricas, metrics_path) -> str`

Salva métricas em JSON.

---

#### `main() -> None`

Orquestra pipeline completo.

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

## Diferença entre evaluation e train_metrics

| Aspecto | train_metrics.json | evaluation.json |
|---------|-------------------|-----------------|
| Quando | Durante treinamento | Após carregar modelo |
| Dataset | Split interno do train | Holdout separado |
| Uso | Referência rápida | Validação independente |

## Output

### metrics/evaluation.json

```json
{
  "r2_score": 0.5096,
  "rmse": 0.3270,
  "mse": 0.107,
  "mae": 0.240,
  "n_amostras_teste": 2497
}
```

**Nota:** O teste agora usa `test_data.csv` fixo (separado no feature_engineering), garantindo consistência entre execuções.

## Logging

```python
logger = logging.getLogger(__name__)
```

**Eventos:**

| Level | Message |
|-------|---------|
| INFO | Carregando modelo |
| INFO | Carregando dados |
| INFO | Holdout: N amostras |
| INFO | Métricas: R², RMSE, MAE |
| INFO | Métricas salvas |
| ERROR | Modelo não encontrado |

## Requirements

```txt
pandas>=2.0.0
scikit-learn>=1.0.0
joblib>=1.0.0
pyyaml>=6.0
```

## Related Documentation

- [Model Training](../model_training/README.md)
- [Inference](../inference/README.md)
