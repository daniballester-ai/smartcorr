# SmartCorr Benchmark de Avaliação Retroativa

Gera predições para N dias passados (onde `NS_Real` já existe) e compara automaticamente com o real observado.

## Quick Start

```bash
python run_benchmark.py              # Últimos 7 dias
python run_benchmark.py --dias 14    # Últimos 14 dias
python run_benchmark.py --dias 7 --salvar
```

## O que o script faz

1. **Extrai** dados retroativos do banco (últimos N dias + margem de 15 dias para lags)
2. **Processa** o pipeline de limpeza (`clean`) e features (`build_features`) em modo `inference`
3. **Filtra** apenas a janela de avaliação (descarta os registros extras de lags)
4. **Gera predições** carregando o modelo `.pkl` de cada programa
5. **Calcula métricas** comparando `NS_Previsto_SmartCorr` vs `NS_Real`, com baseline WFM
6. **Exporta** CSV, JSON de métricas e gráficos PNG para `reports/benchmark/`

## Parâmetros

| Argumento | Tipo | Padrão | Descrição |
|-----------|------|--------|-----------|
| `--dias` | int | 7 | Dias retroativos para avaliar |
| `--salvar` | flag | False | Salva resultados no banco (tabela separada) |

## Fluxo de execução (`main`)

```
Etapa 1/5 → extrair_dados_retroativos()
Etapa 2/5 → processar_pipeline()  [clean → build_features]
Etapa 3/5 → filtrar_janela_avaliacao()
Etapa 4/5 → gerar_predicoes()
Etapa 5/5 → calcular_metricas() → gerar_graficos() → imprimir_relatorio()
```

## Funções principais

### `extrair_dados_retroativos(config, dias_retroativos)`
Consulta o banco com janela `dias_retroativos + 15` (margem para lags). Aplica filtro `DataRef < GETDATE()` para garantir dados reais completos. Usa as mesmas funções de `src.data_loading.load_data` da produção.

### `processar_pipeline(df_bruto, config)`
Força `mode = "inference"` para evitar filtros de treino. Executa `clean()` e `build_features()`, carregando o target encoding de `models/target_encoding.json`.

### `filtrar_janela_avaliacao(df, dias_retroativos)`
Corta o DataFrame na data `(hoje - dias_retroativos)`, mantendo só os registros que serão de fato avaliados.

### `gerar_predicoes(df, config)`
Para cada `CodPrograma`:
- Carrega `model_{programa}.pkl`
- Carrega encoding por programa de `models/encodings/target_encoding_{programa}.json`
- Usa `feature_registry` se disponível
- Aplica transformação reversa se `target_transformation` estiver ativa
- Força `NS = 0` quando `Vol_Previsto == 0`
- Trunca predições em `[0, 1]`

### `calcular_metricas(df)`
Métricas calculadas (apenas intervalos com `Vol_Real > 0`):

| Métrica | SmartCorr | WFM (baseline) |
|---------|-----------|-------------------|
| MAE | :heavy_check_mark: | :heavy_check_mark: |
| RMSE | :heavy_check_mark: | :heavy_check_mark: |
| R² | :heavy_check_mark: | :heavy_check_mark: |
| Uplift % | `(MAE_WFM - MAE_SC) / MAE_WFM * 100` | — |

Inclui também detalhamento **por programa** com as mesmas métricas.

### `gerar_graficos(df, diretorio_saida)`
Gera um PNG por programa com séries temporais de NS_Real, NS_WFM e NS_SmartCorr. Salva em `reports/benchmark/benchmark_{programa}.png`.

### `imprimir_relatorio(metricas, dias)`
Exibe tabela formatada no console com métricas globais e por programa.

## Arquivos de saída

Todos salvos em `reports/benchmark/`:

| Arquivo | Conteúdo |
|---------|----------|
| `benchmark_{dias}d.csv` | Predições por intervalo |
| `metricas_{dias}d.json` | Métricas globais + por programa |
| `benchmark_{programa}.png` | Gráfico comparativo por programa |

## Regras importantes

- **Não altera** a tabela de produção `FactSmartCorr_Previsao`
- Usa `DataRef < GETDATE()` para garantir que só dados completos entrem na avaliação
- Modo `inference` no pipeline desativa filtros de treino (ex.: remoção de outliers)
- Se `--salvar` for passado, salva em tabela separada (não implementado no corpo atual)

## Dependências internas

```
src.data_loading.load_data   → Extração
src.data_preprocessing.clean → Limpeza
src.feature_engineering      → Features
src.config.feature_registry  → (opcional) Features por programa
src.database                 → Conexão
```
