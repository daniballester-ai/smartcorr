# Relatório de Análise — MLPreditivoAbs.py

**Data:** 07/04/2026  
**Arquivo:** `MLPreditivoAbs.py`  
**Linhas:** 624  
**Propósito:** Previsão de absenteísmo usando Random Forest com dados de SQL Server

---

## 1. Visão Geral do Sistema

O script implementa um pipeline de machine learning para prever faltas de colaboradores com base em:

- **Dados de escala** (tempo de trabalho agendado)
- **Distância até o local de trabalho**
- **Histórico de ausências** por expert e operação
- **Features temporais** (dia da semana, fim de semana)

### Pipeline Atual

```
Carregar dados do SQL Server
    → Pré-processamento
        → Engenharia de features
            → Treinamento por operação (com SMOTE + Tuning opcional)
                → Geração de previsões
                    → Inserção no banco de dados
                        → Execução de procedures
```

### Stack Tecnológica

| Componente | Tecnologia |
|------------|------------|
| Linguagem | Python |
| ML | scikit-learn (Random Forest) |
| Balanceamento | imbalanced-learn (SMOTE) |
| Banco | SQL Server (pyodbc) |
| Dados | pandas, numpy |

---

## 2. Problemas Críticos (P0 — Bloqueantes)

### 2.1 `class_weight='recall'` — Valor Inválido

**Local:** Linha 450

```python
self.model = RandomForestClassifier(
    ...
    class_weight='recall',  # ERRO: este valor não existe
    ...
)
```

**Problema:** O scikit-learn aceita apenas `None`, `'balanced'`, `'balanced_subsample'` ou um `dict`. O valor `'recall'` causará `ValueError` em runtime.

**Impacto:** O método `train_model()` **quebra sempre** que chamado sem `tune_hyperparams=True`.

**Sugestão:**
```python
class_weight='balanced'
# ou, para penalizar mais a classe minoritária:
class_weight={0: 1, 1: 5}
```

---

### 2.2 Ativação de VENV via `exec()`

**Local:** Linhas 1-3

```python
enable_venv = os.path.join(os.path.dirname(os.path.abspath(__file__)), r'venv\Scripts\activate_this.py')
exec(open(enable_venv).read(), {'__file__': enable_venv})
```

**Problema:**
- `exec()` executa código arbitrário — risco de segurança
- Caminho hardcoded para Windows — quebra em Linux/macOS
- `activate_this.py` foi descontinuado em versões recentes do venv

**Impacto:** Falha ao ativar ambiente virtual; vulnerabilidade potencial.

**Sugestão:**
```python
# Opção 1: Remover e ativar o venv externamente (recomendado)
# python -m venv venv && venv\Scripts\activate && python MLPreditivoAbs.py

# Opção 2: Verificar ambiente com aviso
import sys
if not hasattr(sys, 'real_prefix') and not (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
    print("AVISO: Ambiente virtual não ativado.")
```

---

## 3. Problemas de Alta Prioridade (P1 — Impacto Direto)

### 3.1 Data Leakage Temporal

**Local:** Linhas 191, 210, 227

```python
df_hist = self.df[self.df['DATA'] <= pd.to_datetime(datetime.now().date()) - timedelta(days=1)]
last_date = pd.to_datetime(datetime.now().date() - timedelta(days=1))
date_threshold_3 = pd.to_datetime(datetime.now().date()) - timedelta(days=3)
```

**Problema:** Usa `datetime.now()` como referência temporal em vez da data máxima dos dados carregados. Se os dados têm delay (ex: último registro é de 3 dias atrás), o modelo usa informações que ainda não estariam disponíveis em produção.

**Impacto:** Métricas de avaliação infladas; performance real inferior ao esperado.

**Sugestão:**
```python
# Usar a data máxima dos dados como referência
max_data_date = self.df['DATA'].max()
df_hist = self.df[self.df['DATA'] <= max_data_date - timedelta(days=1)]
```

### 3.2 `LOKY_MAX_CPU_COUNT` Conflitando com `n_jobs=-1`

**Local:** Linha 4

```python
os.environ["LOKY_MAX_CPU_COUNT"] = "1"
```

**Problema:** Limita o joblib a 1 CPU, mas `n_jobs=-1` é usado no Random Forest (linhas 299, 406). O modelo tenta usar todos os cores, mas é limitado a 1.

**Impacto:** Performance de treino degradada sem benefício real. Se a intenção era limitar CPU, usar `n_jobs=1` explicitamente é mais claro.

**Sugestão:**
```python
# Se quer limitar:
N_JOBS = int(os.environ.get("ML_N_JOBS", "1"))
# ...
self.model.fit(X_train, y_train)  # remover n_jobs=-1 ou usar N_JOBS

# Se quer performance máxima:
os.environ["LOKY_MAX_CPU_COUNT"] = str(os.cpu_count())
```

---

## 4. Problemas de Média Prioridade (P2 — Manutenibilidade)

### 4.1 Merge Criando Colunas Duplicadas (`_x` / `_y`)

**Locais:** Linhas 184-187, 486-501

```python
if 'DISTANCE_MEAN_x' in self.df.columns:
    self.df.rename(columns={'DISTANCE_MEAN_x': 'DISTANCE_MEAN'}, inplace=True)
if 'DISTANCIA_DA_EMPRESA_x' in self.df.columns:
    self.df.rename(columns={'DISTANCIA_DA_EMPRESA_x': 'DISTANCIA_DA_EMPRESA'}, inplace=True)
# ... mais 8 renames similares em predict_absenteeism()
```

**Problema:** O merge na linha 244-248 e linha 477 cria colunas duplicadas porque `self.expert_stats` e `self.df` compartilham nomes de coluna (`DISTANCIA_DA_EMPRESA`, `DISTANCE_MEAN`). Os renames defensivos são um paliativo.

**Causa raiz:** `agg_stats` na linha 193-199 inclui `DISTANCIA_DA_EMPRESA` e `DISTANCE_MEAN`, que já existem no DataFrame principal.

**Sugestão:**
```python
# Remover colunas conflitantes do merge
cols_to_drop = ['DISTANCIA_DA_EMPRESA', 'DISTANCE_MEAN']
self.df = self.df.drop(columns=[c for c in cols_to_drop if c in self.df.columns])

self.df = self.df.merge(
    self.expert_stats,
    on=['MATRICULA EXPERT', 'CodeLevelServiceStructure3'],
    how='left'
)
```

### 4.2 Thresholds Hardcoded por Cliente

**Local:** Linhas 509-520

```python
if codigo_cliente_str == '3230':
    custom_threshold = 0.88
elif codigo_cliente_str == '2721':
    custom_threshold = 0.75
elif codigo_cliente_str == '2379':
    custom_threshold = 0.71
```

**Problema:** Valores embutidos no código exigem redeploy para cada ajuste. Não há documentação do critério de escolha.

**Sugestão:** Externalizar para configuração ou tabela no banco:

```python
# Opção 1: Dicionário de configuração
THRESHOLDS_BY_CLIENT = {
    '3230': 0.88,
    '2721': 0.75,
    '2379': 0.71,
}
custom_threshold = THRESHOLDS_BY_CLIENT.get(codigo_cliente_str, 0.80)

# Opção 2: Buscar do banco (recomendado para ajustes dinâmicos)
# query = "SELECT Threshold FROM AbsGuard.ClientThresholds WHERE ClientCode = ?"
```

### 4.3 Variável Não Utilizada

**Local:** Linha 461

```python
days_ahead=141  # Nunca usada
```

**Sugestão:** Remover ou utilizar no filtro de datas futuras.

### 4.4 Dupla Instanciação do Predictor

**Local:** Linhas 536 e 591

```python
predictor = AbsenteeismPredictor()  # Linha 536
# ...
db_manager = AbsenteeismPredictor()  # Linha 591 — nova conexão ao banco
```

**Problema:** Cria duas conexões separadas ao banco de dados desnecessariamente.

**Sugestão:** Reutilizar a mesma instância:
```python
# Usar `predictor` para tudo, remover `db_manager`
predictor.truncate_table(...)
predictor.insert_data(...)
```

---

## 5. Problemas de Baixa Prioridade (P3 — Boas Práticas)

### 5.1 `truncate_table` Usa DELETE, Não TRUNCATE

**Local:** Linha 91

```python
query = f"DELETE FROM {table_name} WHERE {v_where}"
```

**Observação:** O nome sugere `TRUNCATE`, mas usa `DELETE` com WHERE. `TRUNCATE` não aceita WHERE. O comportamento está correto para o caso de uso, mas o nome é enganoso.

**Sugestão:** Renomear para `delete_from_table` ou `clean_table_by_condition`.

### 5.2 `TARGET_STD` Preenchido com 0

**Local:** Linhas 250-253

```python
for c in ['TARGET_MEAN', 'TARGET_STD', 'TARGET_LAST', ...]:
    self.df[c] = self.df[c].fillna(0)
```

**Problema:** `TARGET_STD = 0` para experts com apenas 1 registro é matematicamente correto, mas pode confundir o modelo ao tratar como "variância zero" vs "nunca faltou".

**Sugestão:** Considerar fill separados:
```python
self.df['TARGET_STD'] = self.df['TARGET_STD'].fillna(self.df['TARGET_STD'].median())
self.df['TARGET_MEAN'] = self.df['TARGET_MEAN'].fillna(0)
```

### 5.3 Falta de Validação de Schema na Inserção

**Local:** Linhas 53-86

O método `insert_data` não valida se as colunas do DataFrame correspondem às colunas da tabela destino antes de inserir.

**Sugestão:** Adicionar validação prévia ou usar `INFORMATION_SCHEMA` para verificar compatibilidade.

### 5.4 SQL Injection Potencial

**Local:** Linhas 70, 91

```python
query = f"INSERT INTO {schema}.{table_name} ({columns}) VALUES ({placeholders})"
query = f"DELETE FROM {table_name} WHERE {v_where}"
```

**Observação:** Os valores são parametrizados (`?`), mas nomes de tabela/schema/colunas vêm de interpolação. Se algum valor vier de input externo, há risco.

**Sugestão:** Validar nomes de tabela/coluna contra allowlist:
```python
import re
def _validate_identifier(name):
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', name):
        raise ValueError(f"Nome de coluna inválido: {name}")
```

### 5.5 Falta de Logging Estruturado

O script usa apenas `print()` para output. Para produção, recomenda-se `logging`:

```python
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logging.info(f"Carregados {len(self.df)} registros do banco de dados.")
```

---

## 6. Boas Práticas Observadas

| Prática | Local | Comentário |
|---------|-------|------------|
| `fast_executemany` | Linha 76 | Insert em lote — boa performance |
| `class_weight='balanced'` | Linha 25 | Lida com desbalanceamento no default |
| Separação temporal treino/teste | Linhas 270-274 | Evita data leakage de shuffle aleatório |
| SMOTE opcional | Linhas 290-295 | Balanceamento sob demanda |
| RandomizedSearchCV | Linhas 316-326 | Tuning sistemático de hiperparâmetros |
| Rollback em transações | Linhas 81, 96, 609 | Garante consistência do banco |
| Backup/restore do `self.df` | Linhas 387, 422 | Protege estado durante treino por operação |
| Validação de classes mínimas | Linhas 287-288 | Evita treino com 1 classe |

---

## 7. Matriz de Priorização

| Prioridade | Item | Esforço | Impacto |
|------------|------|---------|---------|
| **P0** | `class_weight='recall'` inválido | 2 min | Bloqueante |
| **P0** | `exec()` com venv | 10 min | Segurança/estabilidade |
| **P1** | Data leakage temporal | 15 min | Qualidade do modelo |
| **P1** | `LOKY_MAX_CPU_COUNT` conflitando | 5 min | Performance |
| **P2** | Merge com colunas duplicadas | 30 min | Manutenibilidade |
| **P2** | Thresholds hardcoded | 20 min | Flexibilidade |
| **P2** | Variável morta `days_ahead` | 1 min | Limpeza |
| **P2** | Dupla instanciação do Predictor | 5 min | Eficiência |
| **P3** | Renomear `truncate_table` | 5 min | Clareza |
| **P3** | Fill de `TARGET_STD` | 5 min | Qualidade do modelo |
| **P3** | Validação de schema | 20 min | Robustez |
| **P3** | SQL injection em nomes | 10 min | Segurança |
| **P3** | Logging estruturado | 30 min | Operacional |

---

## 8. Sugestões de Melhorias Estruturais

### 8.1 Externalizar Configurações

Criar um arquivo `config.py` ou `.env`:

```python
# config.py
DB_CONFIG = {
    'server': os.getenv('DB_SERVER'),
    'database': os.getenv('DB_DATABASE'),
    'username': os.getenv('DB_USERNAME'),
    'password': os.getenv('DB_PASSWORD'),
}

MODEL_CONFIG = {
    'n_estimators': 200,
    'max_depth': 10,
    'class_weight': 'balanced',
    'threshold_default': 0.80,
    'thresholds_by_client': {
        '3230': 0.88,
        '2721': 0.75,
        '2379': 0.71,
    },
}

TRAINING_CONFIG = {
    'smote': True,
    'tune_hyperparams': True,
    'n_iter': 50,
    'cv': 3,
    'n_jobs': int(os.getenv('ML_N_JOBS', '1')),
}
```

### 8.2 Separar Responsabilidades

O `AbsenteeismPredictor` faz muitas coisas. Sugestão de refatoração:

```
MLPreditivoAbs.py
├── DatabaseManager      # Conexão, queries, inserts
├── DataPreprocessor     # Limpeza, feature engineering
├── ModelTrainer         # Treino, tuning, avaliação
├── PredictionEngine     # Geração de previsões
└── Pipeline             # Orquestração do fluxo
```

### 8.3 Adicionar Testes Unitários

```python
def test_preprocess_data():
    predictor = AbsenteeismPredictor()
    predictor.df = pd.DataFrame({...})
    predictor.preprocess_data()
    assert 'TARGET' in predictor.df.columns
    assert predictor.df['DISTANCIA_DA_EMPRESA'].isna().sum() == 0

def test_prepare_data_validation():
    predictor = AbsenteeismPredictor()
    predictor.df = pd.DataFrame({'TARGET': [0, 0, 0]})  # 1 classe
    with pytest.raises(ValueError, match="apenas 1 classe"):
        predictor.prepare_data()
```

### 8.4 Adicionar Monitoramento de Modelo

```python
# Salvar métricas de cada treino para tracking
metrics_log = {
    'operacao': operacao,
    'data_treino': datetime.now(),
    'auc_roc': auc_score,
    'recall': recall_score,
    'precision': precision_score,
    'n_treino': len(X_train),
    'n_teste': len(X_test),
}
# Inserir em tabela de histórico de modelos
```

### 8.5 Pipeline com Airflow ou Task Scheduler

Para produção, considerar orquestração:

```python
# Exemplo com Apache Airflow
@dag(schedule_interval='0 6 * * *', catchup=False)
def absenteeism_pipeline():
    @task
    def extract():
        predictor.load_data_from_db()
        return predictor.df

    @task
    def transform(df):
        predictor.df = df
        predictor.preprocess_data()
        predictor.feature_engineering()

    @task
    def train_and_predict():
        return predictor.train_model_por_operacao(...)

    df >> transform >> train_and_predict
```

---

## 9. Conclusão

O script é **funcional** mas possui um **bug bloqueante** (`class_weight='recall'`) que impede o uso do método `train_model()`. Além disso, há riscos de **data leakage** que podem inflar artificialmente as métricas do modelo.

As correções de P0 e P1 devem ser tratadas **imediatamente**. As melhorias de P2 e P3 podem ser planejadas em sprints subsequentes.

### Estimativa de Esforço Total

| Categoria | Tempo Estimado |
|-----------|----------------|
| Correções P0 | 15 min |
| Correções P1 | 20 min |
| Melhorias P2 | 1h |
| Melhorias P3 | 1h 15min |
| Refatoração estrutural | 4-8h |
| Testes | 2-4h |
