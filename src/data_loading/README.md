# Data Loading Module

> Extração e carga de dados da View SmartCorr e FatoTempoSistemas para o pipeline de correlação inteligente.

## Quick Start

```bash
# Executar com credenciais Windows (runas)
runas /netonly /user:tpb\ballester.19 "python -m src.data_loading.load_data"

# Ou via Task Scheduler (recomendado para automação)
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
│                       fetch_data()                           │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │ smartcorr    │  │ perda_log    │  │ _merge_daily_data │  │
│  │ (intervalos) │  │ (diário)     │  │ (broadcast join)   │  │
│  └──────┬───────┘  └──────┬───────┘  └─────────┬─────────┘  │
└─────────┼────────────────┼───────────────────┼─────────────┘
          ▼                ▼                   ▼
    ┌─────────────────────────────────────────────────┐
    │              SQL Server (OdsCorp)                 │
    │  • vw_SmartCorr_Principal                        │
    │  • FatoTempoSistemas                             │
    │  • factMicroGestao                               │
    └─────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                      save_data()                            │
│                  (CSV → data/raw/)                          │
└─────────────────────────────────────────────────────────────┘
```

## Pipeline Flow

| Step | Function | Description |
|------|----------|-------------|
| 1 | `main()` | Carrega config, orquestra pipeline |
| 2 | `fetch_data()` | Busca dados do SQL Server |
| 3 | `_fetch_smartcorr_data()` | Query View SmartCorr (intervalos) |
| 4 | `_fetch_perda_log_data()` | Query FatoTempoSistemas (diário) |
| 5 | `_merge_daily_data()` | Broadcast join diário → intervalos |
| 6 | `save_data()` | Persiste CSV em `data/raw/` |

## Configuration

### params.yaml

```yaml
data:
  queries_file: config/queries.ini    # Caminho das queries SQL
  raw_path: data/raw/raw_history.csv # Destino dos dados brutos
  janela_dias: 120                   # Janela de dias para consulta
  data_corte_final: null            # Data fixa (DD/MM/YYYY) ou null (atual)
```

### config/queries.ini

```ini
[smartcorr]
query = SELECT [DataRef], [Intervalo], ... FROM [OdsCorp].[SmartCorr].[vw_SmartCorr_Principal]

[perda_log]
query = SELECT F.[Date], ... FROM [OdsCorp].[DataMart].[FatoTempoSistemas]
```

## API Reference

### Public Functions

#### `load_config() -> dict`

Carrega configurações do `params.yaml`.

**Returns:**
- `dict`: Configurações completas do arquivo

---

#### `load_queries(queries_file: str) -> dict`

Carrega queries SQL do arquivo `.ini`.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| queries_file | str | Yes | Caminho para `config/queries.ini` |

**Returns:**
```json
{
  "smartcorr": "SELECT ... FROM vw_SmartCorr_Principal ...",
  "perda_log": "SELECT ... FROM FatoTempoSistemas ..."
}
```

---

#### `fetch_data(janela_dias: int, queries_file: str, data_corte_final: str | None) -> pd.DataFrame`

Busca e consolida dados do SQL Server.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| janela_dias | int | Yes | Janela de dias para consulta |
| queries_file | str | Yes | Caminho do arquivo de queries |
| data_corte_final | str \| None | No | Data de corte (DD/MM/YYYY) |

**Returns:**
- `pd.DataFrame`: Dados consolidados com colunas:

| Column | Type | Source |
|--------|------|--------|
| DataRef | datetime | smartcorr |
| Intervalo | str | smartcorr |
| CodPrograma | int | smartcorr |
| Canal | int | smartcorr |
| Vol_Previsto | float | smartcorr |
| ... | ... | ... |
| PerdaLog_Total_Sec | float | perda_log |
| SysFailure_Sec_Daily | float | perda_log |
| TechIssues_Total_Sec_Daily | float | perda_log |
| ... | ... | perda_log |

---

#### `save_data(data: pd.DataFrame, output_path: str) -> str`

Salva DataFrame em arquivo CSV.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| data | pd.DataFrame | Yes | Dados a salvar |
| output_path | str | Yes | Caminho do CSV |

**Returns:**
- `str`: Caminho do arquivo salvo

---

#### `main() -> None`

Orquestra pipeline completo de extração e salvamento.

**Execution:**
```python
config = load_config()
df = fetch_data(janela_dias, queries_file, data_corte_final)
save_data(df, raw_path)
```

### Private Functions

| Function | Purpose |
|----------|---------|
| `_build_data_expressions()` | Constrói expressões SQL de data |
| `_fetch_smartcorr_data()` | Executa query SmartCorr |
| `_fetch_perda_log_data()` | Executa query Perda de Log |
| `_merge_daily_data()` | Realiza broadcast join |

## Data Sources

### SmartCorr Principal (vw_SmartCorr_Principal)

**Filtros aplicados:**
- `CodPrograma IN (...)` - Operações Pagbank
- `Canal = 7` - Canal de Voz
- `DataRef` - Janela configurável

**Colunas retornadas:**
- Volumetria: Vol_Previsto, Vol_Real, Vol_Atendidas, Vol_Abandono
- Capacidade: HC_Previsto, HC_Real_Equiv
- TMA: Tempo_AHT_Previsto_Total, Tempo_AHT_Real_Total, Tempo_Espera_Total
- Pausas: Pausa_Tecnica_Sec, Pausa_Pessoal_Sec, Pausa_Gestao_Sec
- KPIs Diários: ABS_Tempo_Sec_Daily, Turnover_Ativos_Daily, etc.

### FatoTempoSistemas (Perda de Log)

**Agregação:** Por `Date` e `CellCode`

**Colunas retornadas:**
- PerdaLog_Total_Sec, PPH_Total_Sec
- SysFailure_Sec_Daily, ClientSysFailure_Sec_Daily, SeatUnavail_Sec_Daily
- TechIssues_Total_Sec_Daily
- NewHire_Qtd_Daily, HC_Total_PerdaLog_Daily
- AgentIssues_Sec_Daily

## Broadcasting Strategy

Dados diários são replicados para todos os intervalos do dia:

```
Antes do Merge:
┌─────────────┬───────┐
│ DataRef     │ HC    │  ← Diária (1 registro/dia)
├─────────────┼───────┤
│ 2026-01-01  │ 50    │
│ 2026-01-02  │ 48    │
└─────────────┴───────┘

┌─────────────┬────────┬───────┐
│ DataRef     │ Intervalo│ Vol  │  ← Intraday (múltiplos/dia)
├─────────────┼────────┼───────┤
│ 2026-01-01  │ 08:00  │ 120   │
│ 2026-01-01  │ 09:00  │ 150   │
│ 2026-01-01  │ 10:00  │ 180   │
│ 2026-01-02  │ 08:00  │ 100   │
└─────────────┴────────┴───────┘

Depois do Merge:
┌─────────────┬────────┬───────┬──────┐
│ DataRef     │ Intervalo│ Vol  │ HC   │  ← Broadcast (mesmo HC p/ todos intervalos)
├─────────────┼────────┼───────┼──────┤
│ 2026-01-01  │ 08:00  │ 120   │ 50   │
│ 2026-01-01  │ 09:00  │ 150   │ 50   │
│ 2026-01-01  │ 10:00  │ 180   │ 50   │
│ 2026-01-02  │ 08:00  │ 100   │ 48   │
└─────────────┴────────┴───────┴──────┘
```

## Logging

```python
logger = logging.getLogger("src.data_loading.load_data")
```

**Eventos logados:**

| Level | Message |
|-------|---------|
| INFO | Iniciando carga de dados (Janela: X dias ...) |
| INFO | Dados SmartCorr carregados: N linhas |
| INFO | Dados Perda de Log carregados: N linhas |
| INFO | Merge concluído. Colunas totais: N |
| INFO | Dados brutos salvos em: caminho |
| WARNING | Nenhum dado retornado! |
| WARNING | Perda de Log vazio |

## Requirements

```txt
pandas>=2.0.0
pyyaml>=6.0
pyodbc>=4.0
```

## Related Documentation

- [Architecture Overview](../docs/architecture.md)
- [Database Connection](../src/database/README.md)
- [Data Preprocessing](../src/data_preprocessing/README.md)
