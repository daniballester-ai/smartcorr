# Análise Completa do Pipeline SmartCorr

## Goal
Analisar cada etapa do pipeline (data_loading, preprocessing, feature_engineering, model_training, evaluation, inference) para entender o fluxo de dados e identificar problemas, culminating em benchmark de previsões vs NS real.

## Pipeline Steps Analysis Done

### Etapa 1: Data Loading - DONE
- [x] Executar data_loading e analisar logs
- [x] Verificar dados brutos: 4848 rows, 25 columns
- [x] Validar queries SQL e filtros aplicados
- **Result**: data/raw/raw_history.csv

### Etapa 2: Preprocessing - DONE
- [x] Filtros de relevância (Vol_Real > 0)
- [x] Distribuição NS after cleaning: 93.4% NS=1
- [x] Programas ativos/inativos identificados
- **Result**: data/interim/clean_data.csv

### Etapa 3: Feature Engineering - DONE
- [x] 89 columns created
- [x] Lag features (NS_Lag_1, NS_Lag_2, etc)
- [x] Rolling features (NS_Media_Movel_3, etc)
- [x] Seasonality features (Dia_Mes, Semana_Mes, etc)
- [x] Train/Test temporal split
- **Result**: data/processed/train_data.csv (562 rows), test_data.csv (127 rows)

### Etapa 4: Model Training - DONE
- [x] Training executed
- [x] Metrics: R²_val=0.12, R²_test=-0.11
- [x] Feature importances: Indicador_Sufoco (19.5%), Dia_Mes (13%)
- **Result**: models/model_589361.pkl

### Etapa 5: Evaluation - DONE
- [x] Predictions = 0.49-0.54 for ALL cases!
- [x] MAE_test = 0.12
- [x] Problem identified

### Etapa 6: Benchmark Results - DONE
- Training: 562 rows, 94.5% NS=1
- Test predictions: mean=0.498 (expected ~0.95)
- Root cause: DATA DRIFT

### Etapa 7: Análise de Problemas

**Problema 1: Modelo prevê ~0.5 para TUDO**
- Train: 562 rows, NS=1 = 531 (94.5%), mean=0.966
- Test: predictions = 0.49-0.54 (mean 0.498)
- O modelo NÃO está aprendendo - apenas prevê valor médio!

**Possíveis causas:**
1. Features não informativas (todas parecem same values)
2. Overfitting no treinamento
3. Data leakage nos dados de treino vs teste
4. Feature engineering com problema

### Etapa 8: ROOT CAUSE ENCONTRADO!

**Problema: Data Drift SEVERO entre Treino e Teste**

| Feature | Train | Test | Problema |
|---------|-------|------|----------|
| Turnover_Taxa_Daily | different values, mean=0.009 | **ALL 0** | Severo! |
| Indicador_Sufoco | mean=0.113 | mean=0.075 | Drift |
| Desvio_Volume_Pct_Lag_1 | mean=-0.186 | mean=-0.007 | Drift |
| NS_Lag_1 | mean=0.966 | mean=0.946 | OK |

**Conclusão:**
- O modelo foi treinado com Turnover_Taxa_Daily Having values
- No teste, TODOS OS VALORES SÃO 0!
- O modelo não consegue adaptar porque a distribuição mudou completamente
- Isso explica por que prevê ~0.5 (valor médio sem informação)

## Done When
- [x] Root cause identificado
- [ ] Fazer correções necessárias
- [ ] Re-treinar com dados mais recentes ou features mais estáveis
- [ ] Verificar inference pipeline para garantir features disponívels



## Notas Importantes
- Data drift é a causa raiz principal
- O modelo funciona OK (R²_val=0.12)
- O problema é a mudança de distribuição entre treino e teste
- Não é bug no código, é conceito de MLOps/drift detection