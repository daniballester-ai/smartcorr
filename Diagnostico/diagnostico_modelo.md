# 🔍 Diagnóstico: Por que NS Previsto ≠ NS Real

## Resumo Executivo

A análise revelou **5 problemas críticos** que explicam a divergência entre NS real e NS previsto. O mais grave é a **distribuição extremamente bimodal do target** — 59% dos registros são `0.0` e 30% são `1.0`, com apenas 10% no meio.

---

## 🚨 Problema #1: Target Bimodal (CRÍTICO)

A distribuição do `NS_Real` está completamente concentrada nos extremos:

| Faixa NS_Real | Treino | % |
|---|---|---|
| **== 0.0** | 5.979 | **59.4%** |
| 0.01 - 0.49 | 87 | 0.9% |
| 0.50 - 0.69 | 129 | 1.3% |
| 0.70 - 0.89 | 270 | 2.7% |
| 0.90 - 0.99 | 589 | 5.9% |
| **== 1.0** | 3.011 | **29.9%** |

> [!CAUTION]
> **O modelo de regressão está tentando prever um valor contínuo entre 0 e 1, mas 89% dos dados são exatamente 0 ou 1.** Isso é essencialmente um **problema de classificação disfarçado de regressão**.

### Causa Raiz

Olhando os registros com `NS_Real == 0`:
- `Vol_Real` médio = **0.0** → Não houve chamadas reais
- `Vol_Previsto` médio = **3.3** → Havia previsão de volume
- `HC_Previsto` médio = **38.4** → Havia equipe prevista

**Conclusão**: Quando `Vol_Real == 0`, a fórmula `Vol_Atendidas_NS_Real / Vol_Real` retorna 0 (proteção contra divisão por zero), mas **na realidade esses intervalos não tiveram operação**. O modelo está sendo treinado com milhares de registros "mortos" que distorcem as predições.

---

## 🚨 Problema #2: 10 Features com Zero Variância (CRÍTICO)

| Feature | Zeros | Observação |
|---|---|---|
| `WAHA_Qtd_Daily` | 100% | Dados não disponíveis |
| `Taxa_Ocupacao_Lag_1` | 100% | Lag de feature 100% zero |
| `Taxa_Pausa_Tecnica_Lag_1` | 100% | Lag de feature 100% zero |
| `Taxa_Pausa_Pessoal_Lag_1` | 100% | Lag de feature 100% zero |
| `Taxa_Pausa_Gestao_Lag_1` | 100% | Lag de feature 100% zero |
| `Razao_Escala` | 100% | `HC_Real_Equiv` sempre zero |
| `Taxa_Sobrecarga` | 100% | `HC_Real_Equiv` sempre zero |
| `TechIssues_Taxa_Daily` | 99.4% | Quase nenhum dado |
| `Desvio_Escala_Pct` | mean = -0.999 | Quase constante |
| `Taxa_Abandono_Lag_1` | 97% | Pouquíssima variação |

> [!WARNING]
> **10 das 30 features (33%) não contribuem com NADA.** O modelo carrega ruído sem informação, e isso atrapalha a capacidade de generalização.

### Causa Raiz

`HC_Real_Equiv == 0` para quase todos os registros, o que significa que a View SQL **não está retornando dados de HC Real**. As taxas de pausa, ocupação e escala dependem de `HC_Real_Equiv` e todas ficam zeradas.

---

## 🚨 Problema #3: Data Leakage nas Features (ALTO)

Três features usam dados **reais** (que só existem DEPOIS do fato):

| Feature | Depende de | Disponível na Inferência? |
|---|---|---|
| `Desvio_Escala_Pct` | `HC_Real_Equiv` | ❌ NÃO (100% dos dados são -0.999) |
| `Razao_Escala` | `HC_Real_Equiv` | ❌ NÃO (100% zero) |
| `Taxa_Sobrecarga` | `HC_Real_Equiv` + `Vol_Real` | ❌ NÃO (100% zero) |

Outras features como `Desvio_Volume_Pct_Lag_1` e `Delta_TMA_Lag_1` usam `shift(1)` sobre dados reais, o que **é correto do ponto de vista temporal**, mas como `HC_Real_Equiv` está sempre zerado, os deltas ficam distorcidos:

- `Desvio_HC_Pct_Lag_1`: mean = **-0.998** (quase constante!)
- Isso significa que o lag está dizendo "HC real foi 99.8% menor que previsto" em praticamente TODOS os intervalos

---

## ⚠️ Problema #4: Janela de Treino Muito Curta

- **Treino**: 16/Mar a 08/Abr (23 dias efetivos)
- **Teste**: 09/Abr a 14/Abr (5 dias)
- **`janela_dias` = 30** no params.yaml

Com apenas 23 dias, o modelo:
- Não captura **sazonalidade mensal** (início/fim de mês tem comportamento diferente)
- Não captura **variações de feriados, campanhas, eventos**
- Tem apenas ~10k registros, dos quais 59% são inúteis (NS=0)

---

## ⚠️ Problema #5: Modelo Tenta Prever Valor Contínuo em Dados Binários

Com R² = 0.87 na avaliação, mas MAE = 0.079 (≈8 p.p.), o erro parece pequeno **em média**, mas:

- Para intervalos com NS=1.0, o modelo pode prever 0.85 → erro de 15 p.p.
- Para intervalos com NS=0.0, o modelo pode prever 0.15 → erro de 15 p.p.
- A métrica R² é enganosa em distribuições bimodais

O Top 3 de importância do modelo confirma o viés:
1. **TME_Real_Avg_Lag_1** (36%) → Tempo médio de espera do intervalo anterior
2. **Pressao_Prevista_Vol_HC** (25%) → Razão Vol/HC previsto
3. **Desvio_Volume_Pct_Lag_1** (14%) → Quanto volume desviou do previsto

---

## 💡 Plano de Ação (Priorizado)

### 🔴 P0 — Imediato (maior impacto)

#### 1. Filtrar intervalos sem operação no treino
```
Remover registros onde Vol_Real == 0 E Vol_Previsto < threshold
```
Esses intervalos "mortos" estão fazendo o modelo aprender que "NS=0 quando não há chamadas", mas na inferência ele não sabe se haverá chamadas ou não.

**Alternativa**: Criar feature binária `tem_operacao` e usar classificação em dois estágios.

#### 2. Remover as 10 features mortas
Reduzir de 30 para ~20 features, mantendo apenas as que têm variância real. Menos ruído = melhor generalização.

#### 3. Investigar HC_Real_Equiv na View SQL
O `HC_Real_Equiv` está vindo zerado da view `vw_SmartCorr_Principal`. Se esse dado for corrigido, **várias features voltam à vida**: Taxa_Ocupacao, Pausas, Desvio_Escala, etc.

### 🟡 P1 — Curto Prazo

#### 4. Aumentar janela de treino para 90-120 dias
Captura sazonalidade mensal e dá mais robustez ao modelo.

#### 5. Considerar abordagem Two-Stage
```
Estágio 1: Classificador → {sem operação, com operação}
Estágio 2: Regressor   → NS_Real (apenas para intervalos com operação)
```

#### 6. Segmentar por CodPrograma ou grupo
Diferentes programas podem ter dinâmicas completamente diferentes. Um modelo com `CodPrograma` como feature (encoding) pode ajudar.

### 🟢 P2 — Médio Prazo

#### 7. Rolling features mais ricas
- Média móvel de NS dos últimos 3/6/12 intervalos
- Desvio padrão de NS dos últimos 6 intervalos
- Tendência (slope) de NS nos últimos 12 intervalos

#### 8. Quantile Regression ou modelo probabilístico
Em vez de prever um ponto, prever intervalos de confiança (Q10, Q50, Q90).

#### 9. Cross-validation temporal
Ao invés de um split fixo 80/20, usar TimeSeriesSplit com 5 folds para avaliação mais robusta.

---

## Impacto Estimado

| Ação | Impacto Esperado | Esforço |
|---|---|---|
| Filtrar NS=0 sem operação | ⭐⭐⭐⭐⭐ | Baixo |
| Remover features mortas | ⭐⭐⭐ | Baixo |
| Corrigir HC_Real_Equiv | ⭐⭐⭐⭐ | Médio (SQL) |
| Aumentar janela de dados | ⭐⭐⭐ | Baixo |
| Two-Stage model | ⭐⭐⭐⭐ | Médio |
| Rolling features | ⭐⭐⭐ | Médio |

> [!IMPORTANT]
> **As ações P0 (#1 a #3) sozinhas devem reduzir o erro significativamente.** O modelo atual está aprendendo um padrão distorcido porque 59% dos dados são "não-eventos" (NS=0 por falta de operação, não por mal desempenho).
