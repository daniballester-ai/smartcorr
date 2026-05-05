# 🔍 Diagnóstico SmartCorr — Por que o NS_Previsto está tão diferente do NS_Real?

## Resumo Executivo

| Métrica | Valor |
|---|---|
| **MAE (Erro Absoluto Médio)** | **0.74** (em escala 0-1) |
| **NS_Real médio (operacional)** | 0.975 (~97.5%) |
| **NS_Previsto_IA médio** | 0.154 (~15.4%) |
| **Razão Real/Previsto** | **6.7x** — o modelo subestima sistematicamente |
| **Registros com predição** | 185 de 240 (55 sem predição = NaN) |

> [!CAUTION]
> O modelo está prevendo NS em torno de 15%, quando o NS real é ~97%. Isso não é um erro marginal — é uma falha estrutural no pipeline de treino.

---

## 🎯 5 Causas Raiz Identificadas

### 🔴 Causa 1: 59% dos dados de treino têm NS_Real = 0 (CRÍTICA)

**O problema mais grave.** De 15 programas configurados no `params.yaml`, **8 programas têm 100% dos registros com NS_Real = 0**:

| Programa | Registros | NS_Real = 0 | NS_Real médio | Vol_Real médio |
|---|---|---|---|---|
| 347858 | 744 | **100.0%** | 0.000 | 0.0 |
| 353059 | 408 | **100.0%** | 0.000 | 0.0 |
| 355491 | 720 | **100.0%** | 0.000 | 0.0 |
| 355492 | 756 | **100.0%** | 0.000 | 0.0 |
| 366845 | 546 | **100.0%** | 0.000 | 0.0 |
| 370587 | 546 | **100.0%** | 0.000 | 0.0 |
| 548619 | 624 | **100.0%** | 0.000 | 0.0 |
| 589266 | 624 | **100.0%** | 0.000 | 0.0 |
| **347851** | 889 | 6.5% | **0.915** | 33.1 |
| 370588 | 891 | 13.0% | 0.823 | 24.1 |
| 581345 | 888 | 4.3% | 0.936 | 30.1 |
| 581346 | 888 | 4.6% | 0.882 | 28.6 |
| 589360 | 329 | 7.6% | 0.877 | 8.6 |
| 589361 | 324 | 38.6% | 0.603 | 1.3 |
| 591529 | 888 | 68.5% | 0.285 | 6.9 |

**Resultado:** 5.979 registros (59.4%) têm NS_Real = 0, e apenas 4.086 (40.6%) têm NS > 0.

> [!WARNING]
> O filtro operacional (`filtro_operacional.ativo: true`) está configurado mas **não está funcionando** para estes 8 programas. Eles passam pelo filtro porque `Vol_Previsto > 0` ou `HC_Previsto > 0` (filtro de relevância na [clean_data.py:78-82](file:///c:/TP_ML/BI_Ferramenta_Correlacao_Inteligente/SmartCorr/src/data_preprocessing/clean_data.py#L78-L82)), mas têm `Vol_Real = 0` em todos os registros.
> 
> Estes programas parecem estar **configurados no WFM/Erlang mas sem operação real de voz no período**. Podem ser: digitais, inativos, ou operações que ainda não entraram em produção.

### 🔴 Causa 2: Target Encoding não está sendo salvo (CRÍTICA)

O arquivo `models/target_encoding.json` **não existe**. Isso significa:

- No treino, o `build_features.py` calcula o encoding corretamente
- Na inferência, como o arquivo não existe, **todos os programas recebem encoding = 0.5** ([build_features.py:401-402](file:///c:/TP_ML/BI_Ferramenta_Correlacao_Inteligente/SmartCorr/src/feature_engineering/build_features.py#L401-L402))
- **O modelo treinado espera valores de encoding que refletem a média de NS por programa**, mas na inferência recebe 0.5 para todos

O encoding correto para o programa 347851 seria ~0.72 (média de NS com suavização bayesiana), mas na inferência recebe 0.5.

### 🟠 Causa 3: Distribuição extremamente desbalanceada do target

A distribuição do NS_Real no treino é **trimodal**:

```
NS_Real == 0:  5.979 (59.4%)  ← Programas fantasma
NS_Real == 1:  3.011 (29.9%)  ← NS perfeito
0 < NS < 1:    1.075 (10.7%)  ← Faixa útil
```

O modelo XGBoost aprende que o "mais provável" é NS entre 0 e 0.3 (a média ponderada fica em ~0.39), porque a maioria dos registros é 0. **Mesmo com o clamp `min(max(pred, 0), 1)`**, a predição gravita para a média do treino.

### 🟠 Causa 4: Inconsistência de escala nos dados do resultado CSV

No CSV de resultados (`resultado_20260419.csv`), observei valores como:

```
Vol_Previsto: "4.186.068", "8.747.493"  (format BR com pontos de milhar)
HC_Previsto:  "6.300.000", "13.800.000"
```

Enquanto nos dados de treino:
```
Vol_Previsto: 84.79, 67.89  (float com 2 decimais)
HC_Previsto:  141, 108      (inteiros)
```

> [!IMPORTANT]
> Há uma inconsistência de formatação numérica entre o que a View SQL retorna para o BI (formato BR) vs. o que o modelo treinou (formato float). Se o CSV está sendo gerado pela query do BI, os valores de Vol/HC estão em **escala completamente diferente** do que o modelo espera.

### 🟡 Causa 5: Somente 1 programa nos resultados vs. 15 no treino

Os resultados só contêm o programa **347851**, mas o modelo foi treinado com 15 programas (dos quais 8 são "fantasma"). O modelo precisa se especializar nos programas que realmente operam.

---

## 📋 Plano de Ação — Priorizado por Impacto

### 🔴 Prioridade 1 — Remover programas sem operação real

**Estimativa de impacto: +70% melhoria**

Remover dos `params.yaml` os 8 programas que têm `Vol_Real = 0` em 100% dos registros:

```yaml
# REMOVER estes programas (sem operação real de voz):
# - 347858, 353059, 355491, 355492
# - 366845, 370587, 548619, 589266

# MANTER apenas programas com operação real:
programas:
  - 347851    # NS médio: 0.915
  - 370588    # NS médio: 0.823
  - 581345    # NS médio: 0.936
  - 581346    # NS médio: 0.882
  - 589360    # NS médio: 0.877
  - 589361    # NS médio: 0.603 (baixo volume - avaliar)
  - 591529    # NS médio: 0.285 (68.5% zeros - avaliar)
```

Considerar também remover `591529` (68.5% de NS=0) e `589361` (vol médio = 1.3 por intervalo).

### 🔴 Prioridade 2 — Corrigir o salvamento do Target Encoding

O `build_features.py` calcula o encoding no treino, mas o arquivo não está sendo persistido. Verificar se:

1. O `encoding_path` em `params.yaml` está correto → Está como `models/target_encoding.json`
2. O `main()` do `build_features.py` passa esse path → **Sim, passa** ([linha 627](file:///c:/TP_ML/BI_Ferramenta_Correlacao_Inteligente/SmartCorr/src/feature_engineering/build_features.py#L627))
3. O `dvc.yaml` lista `models/target_encoding.json` como output → **Não lista!**

**Ação**: Adicionar `models/target_encoding.json` como output do stage `engineer_features` no `dvc.yaml`.

### 🟠 Prioridade 3 — Fortalecer o filtro operacional no clean_data

O filtro atual ([clean_data.py:78-85](file:///c:/TP_ML/BI_Ferramenta_Correlacao_Inteligente/SmartCorr/src/data_preprocessing/clean_data.py#L78-L85)) permite registros que tenham `Vol_Previsto > 0` OU `HC_Previsto > 0` mas **sem Vol_Real**. O filtro operacional posterior remove `Vol_Real < 1`, mas NÃO remove registros onde `Vol_Real = 0` E `Vol_Previsto > 0` (programas planejados mas sem operação real).

**Ação**: Se o programa não tem Vol_Real em **nenhum** registro da janela, remover **todos os registros** desse programa da base de treino.

### 🟠 Prioridade 4 — Retreinar com janela mais recente e dados limpos

Após as correções acima:
1. Ajustar `janela_dias: 90` ou mais, para capturar padrões semanais
2. Retreinar o modelo: `dvc repro`
3. Avaliar métricas no test set

### 🟡 Prioridade 5 — Considerar modelo por programa (futuro)

Se os programas têm comportamentos muito distintos (NS médio entre 0.28 e 0.94), considerar:
- Treinar um modelo separado por programa, ou
- Usar o programa como uma interação explícita (`CodPrograma * features`)

---

## 🔧 Mudanças Concretas de Código

### 1. `params.yaml` — Limpar programas

```diff
  programas:
-   - 366845
-   - 370587
-   - 370588
-   - 548619
+   - 370588
    - 581345
    - 581346
-   - 589266
-   - 589360
-   - 589361
-   - 591529
+   - 589360
    - 347851
-   - 347858
-   - 353059
-   - 355491
-   - 355492
```

### 2. `dvc.yaml` — Adicionar output do target encoding

```diff
  engineer_features:
    always_changed: true
    cmd: python -m src.feature_engineering.build_features
    deps:
      - src/feature_engineering/build_features.py
      - data/interim/clean_data.csv
    outs:
      - data/processed/train_data.csv
      - data/processed/test_data.csv
      - data/processed/future_data.csv
+     - models/target_encoding.json
    params:
      - data.mode
      - data.test_size
      - data.features
      - data.target
```

### 3. `clean_data.py` — Adicionar filtro de programa inativo

Adicionar validação no `clean()` que remove programas sem nenhum `Vol_Real > 0` na janela inteira:

```python
def _filter_programas_inativos(df: pd.DataFrame) -> pd.DataFrame:
    """Remove programas que não têm nenhuma operação real na janela."""
    vol_por_programa = df.groupby("CodPrograma")["Vol_Real"].sum()
    programas_ativos = vol_por_programa[vol_por_programa > 0].index
    programas_inativos = vol_por_programa[vol_por_programa == 0].index
    
    if len(programas_inativos) > 0:
        logger.warning(
            f"REMOVENDO {len(programas_inativos)} programas sem operação real: "
            f"{list(programas_inativos)}"
        )
    
    return df[df["CodPrograma"].isin(programas_ativos)].copy()
```

---

## 📊 Estimativa de Impacto

| Ação | Impacto Esperado no MAE | Esforço |
|---|---|---|
| Remover programas fantasma | **0.74 → ~0.15** | 5 min |
| Corrigir target encoding | **~0.15 → ~0.10** | 5 min |
| Retreinar modelo limpo | **~0.10 → ~0.06** | 20 min |
| Modelo por programa (futuro) | **~0.06 → ~0.04** | 2h+ |

> [!TIP]
> As duas primeiras ações (remover programas e corrigir encoding) devem resolver **80-90% do problema** com menos de 10 minutos de trabalho.
