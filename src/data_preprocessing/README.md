# Data Preprocessing Module

> Limpeza, formatação e preparação dos dados brutos para o pipeline de correlação inteligente.

## Quick Start

```bash
# Executar standalone
python -m src.data_preprocessing.clean_data

# Ou via runas
runas /netonly /user:tpb\ballester.19 "python -m src.data_preprocessing.clean_data"
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
│                        clean()                               │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────┐  │
│  │ _parse_      │→ │ _create_     │→ │ _filter_         │  │
│  │ datetime()   │  │ temporal_    │  │ relevant_       │  │
│  │              │  │ features()   │  │ intervals()     │  │
│  └──────────────┘  └──────────────┘  └─────────────────┘  │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐                        │
│  │ _calculate_   │→ │ _fill_       │                        │
│  │ target()      │  │ missing_     │                        │
│  │              │  │ values()     │                        │
│  └──────────────┘  └──────────────┘                        │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                      save_data()                            │
│                  (CSV → data/interim/)                      │
└─────────────────────────────────────────────────────────────┘
```

## Pipeline Flow

| Step | Function | Description |
|------|----------|-------------|
| 1 | `main()` | Carrega config, orquestra pipeline |
| 2 | `clean()` | Executa todas as etapas de limpeza |
| 3 | `_parse_datetime()` | Constrói DataHora a partir de DataRef + Intervalo |
| 4 | `_create_temporal_features()` | Extrai Hora e DiaSemana |
| 5 | `_filter_relevant_intervals()` | Remove slots vazios |
| 6 | `_calculate_target()` | Calcula NS_Real |
| 7 | `_fill_missing_values()` | Preenche NaNs com 0 |
| 8 | `save_data()` | Persiste CSV em `data/interim/` |

## Configuration

### params.yaml

```yaml
data:
  raw_path: data/raw/raw_history.csv   # Entrada (bruto)
  clean_path: data/interim/clean_data.csv  # Saída (limpo)
```

## API Reference

### Public Functions

#### `load_config() -> dict`

Carrega configurações do `params.yaml`.

**Returns:**
- `dict`: Configurações completas do arquivo

---

#### `clean(df: pd.DataFrame) -> pd.DataFrame`

Executa pipeline completo de limpeza.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| df | pd.DataFrame | Yes | Dados brutos do load_data |

**Returns:**
- `pd.DataFrame`: Dados limpos e preparados

**Transformations:**
1. Constrói `DataHora` a partir de `DataRef` + `Intervalo`
2. Extrai `Hora` (0-23) e `DiaSemana` (0=Seg, 6=Dom)
3. Remove intervalos sem previsão E sem atendimento
4. Calcula `NS_Real` = Vol_Atendidas_NS_Real / Vol_Real
5. Preenche NaNs numéricos com 0

---

#### `save_data(df: pd.DataFrame, output_path: str) -> str`

Salva DataFrame em arquivo CSV.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| df | pd.DataFrame | Yes | Dados limpos |
| output_path | str | Yes | Caminho do CSV |

**Returns:**
- `str`: Caminho do arquivo salvo

---

#### `main() -> None`

Orquestra pipeline completo.

```python
df_raw = pd.read_csv(raw_path)
df_clean = clean(df_raw)
save_data(df_clean, clean_path)
```

### Private Functions

| Function | Purpose |
|----------|---------|
| `_parse_datetime()` | Constrói DataHora a partir de DataRef + Intervalo |
| `_create_temporal_features()` | Extrai Hora e DiaSemana de DataHora |
| `_filter_relevant_intervals()` | Remove intervalos sem operação |
| `_calculate_target()` | Calcula Nível de Serviço Real |
| `_fill_missing_values()` | Preenche NaNs com valor configurável |

## Data Transformations

### 1. Datetime Parsing

```python
# Entrada:
# DataRef: "2026-01-15"
# Intervalo: "10:30:00.0000000"

# Saída:
# DataHora: 2026-01-15 10:30:00
```

### 2. Temporal Features

| Column | Description | Range |
|--------|-------------|-------|
| `Hora` | Hora do intervalo | 0-23 |
| `DiaSemana` | Dia da semana | 0 (Seg) - 6 (Dom) |

### 3. Interval Filtering

Remove apenas turnos fechados. Mantém:
- Registros operacionais (com volume)
- Registros ociosos (com equipe, sem volume)

```python
# Mantidos:
(Vol_Previsto > 0) OR (Vol_Real > 0) OR (HC_Previsto > 0)

# Removidos (turno fechado):
Vol_Previsto == 0 AND Vol_Real == 0 AND HC_Previsto == 0
```

**Categorias preservadas:**

| Tipo | Condição | Descrição |
|------|----------|-----------|
| Operacional | Vol > 0 | Com ligações |
| Ocioso | HC_Previsto > 0, Vol = 0 | Equipe disponível sem ligações |

### 4. Target Calculation

```python
NS_Real = Vol_Atendidas_NS_Real / Vol_Real  # se Vol_Real > 0
NS_Real = 0                                   # se Vol_Real == 0
NS_Real = clip(NS_Real, 0, 1)                  # Limita entre 0 e 1
```

### 5. Missing Value Handling

Todas as colunas numéricas são preenchidas com `0.0`.

## Logging

```python
logger = logging.getLogger(__name__)
```

**Eventos logados:**

| Level | Message |
|-------|---------|
| INFO | Linhas antes da limpeza: N |
| INFO | Linhas após remover slots vazios: N |
| INFO | Linhas após limpeza: N |
| INFO | Dados limpos salvos em: caminho |
| WARNING | Colunas DataRef/Intervalo não encontradas |
| ERROR | Erro na limpeza de dados |

## Input Schema

```python
{
    "DataRef": str,          # Data de referência
    "Intervalo": str,        # Hora do intervalo
    "CodPrograma": int,      # Código do programa
    "Canal": int,            # Código do canal
    "Vol_Previsto": float,   # Volume previsto
    "Vol_Real": float,       # Volume real
    "Vol_Atendidas": float,  # Atendidas total
    "Vol_Atendidas_NS_Real": float,  # Atendidas NS
    "Vol_Abandono": float,   # Abandonos
    "HC_Previsto": float,    # HC previsto
    "HC_Real_Equiv": float,  # HC real
    # ... outras colunas do SmartCorr
}
```

## Output Schema

```python
{
    # Colunas originais ...

    # Novas colunas:
    "DataHora": datetime,     # Timestamp completo
    "Hora": int,              # 0-23
    "DiaSemana": int,         # 0-6
    "NS_Real": float,        # 0.0-1.0 (Target)
}

## Data Retention

| Categoria | Registros | % |
|-----------|----------|---|
| Total original | 35,280 | 100% |
| Operacionais | ~10,094 | 29% |
| Ociosos | ~10,289 | 29% |
| Removidos (turno fechado) | ~14,897 | 42% |
| **Total limpo** | **20,383** | **58%** |

### Categorias de Dados

| Tipo | Condição | Utilidade |
|------|----------|-----------|
| **Operacional** | Vol_Real > 0 | Treino de predição NS |
| **Ocioso** | HC_Previsto > 0, Vol = 0 | Treino de underutilization (equipe desperdiçada) |
| **Removido** | Tudo = 0 | Turnos fechados/madrugada |

## Requirements

```txt
pandas>=2.0.0
numpy>=1.24.0
pyyaml>=6.0
```

## Related Documentation

- [Data Loading](../data_loading/README.md)
- [Feature Engineering](../feature_engineering/README.md)
- [Configuration](../params.yaml)
