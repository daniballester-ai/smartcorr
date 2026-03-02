# Design Técnico: ETL e Engenharia de Features (SmartCorr)

Este documento define a arquitetura de dados para alimentar o modelo de Machine Learning, baseada no Brainstorming e no Mapeamento de Variáveis aprovados.

---

## 1. Estratégia de Dados (The "Hybrid" Approach)

O modelo será treinado com uma visão **Híbrida**: não tentaremos prever o Nível de Serviço do zero, mas sim **corrigir o erro do Erlang**.

* **Input (X):** O planejamento teórico (Erlang) + O comportamento real recente (Ineficiências).
* **Output (Y):** O desvio real do Nível de Serviço.

### A Lógica do Benchmark

O modelo aprende onde o Erlang "mentiu" ou falhou.

> *Exemplo:* "O Erlang previu NS 90%. O sistema detectou uma falha sistêmica de 10 min (Pausa Técnica). O modelo corrige a previsão para 82% baseado no impacto histórico dessa falha."

### A Decisão do Join: `FULL OUTER JOIN`

Não podemos usar apenas `INNER JOIN` entre Real e Meta.

* **Cenário A (Hora Extra):** Temos chamadas reais, mas zero forecast. O modelo precisa alertar.
* **Cenário B (Queda de Link):** Temos forecast, mas zero chamadas. O modelo precisa aprender esse padrão de "Sinal de Vida Zero".

---

## 2. Schema da Tabela de Treino (`dataset_train`)

A query SQL resultante deverá entregar a seguinte estrutura plana para o Python:

### Chaves (Identificadores)

* `DataRef` (Date): Dia da operação.
* `Intervalo` (Time): Início do slot de 30min (ex: 10:00:00).
* `CodPrograma` (Int): ID da Operação (`program_ccmsid`).
* `Canal` (Int): ID do Meio (`Channel`).

### Features de Volumetria (Input)

* `Vol_Previsto` (Int): `chamrece` da tabela Metas.
* `Vol_Real` (Int): `OFERECIDAS` da tabela Intraday.
* `Vol_Delta_Abs` (Int): `Vol_Real - Vol_Previsto`.
* `Vol_Delta_Perc` (Float): `(Vol_Real / Vol_Previsto) - 1`.

### Features de Capacidade (Input)

* `HC_Previsto` (Float): `hcdime` (Headcount dimensionado).
* `HC_Real_Equiv` (Float): **Cálculo de Proxy**.
  * *Lógica:* Como não temos contagem direta de logins, dividimos os segundos totais de disponibilidade pela duração do slot (1800s).
  * *Exemplo:* 3600s logados num intervalo de 30min = **2.0 Agentes Full-Time**.
* `TMA_Previsto` (Sec): `TMA_Pond` (Meta de tempo falado).
* `TMA_Real` (Sec): `(TMP_FALADO + TMP_HOLD + TMP_POS_AT) / ATENDIDAS`.

### Features de Ineficiência (O "Pulo do Gato")

Para evitar que o modelo se perca em 10 colunas de pausa esparsas (ruído), agrupamos em 3 "Super-Features" comportamentais:

* **`Pausa_Tecnica_Sec`** (Crítico): `TMP_PAUSA0` (Sistema) + `TMP_PAUSA7` (Falha).
  * *Impacto:* O modelo aprende que isso derruba o NS drasticamente.
* **`Pausa_Pessoal_Sec`** (Aderência): `TMP_PAUSA1` (Lanche) + `TMP_PAUSA2` (Particular) + `TMP_PAUSA4` (Descanso).
  * *Impacto:* Aprende a curva natural de pausas (almoço, bio).
* **`Pausa_Gestao_Sec`** (Planejado): `TMP_PAUSA3` (Treinamento) + `TMP_PAUSA5` (BackOffice).
  * *Impacto:* Aprende o efeito da retirada planejada de staff para desenvolvimento.

### Target (O que queremos prever)

* `NS_Real` (Float): `ATENDIDAS_NS / OFERECIDAS`.
* `NS_Previsto_Erlang` (Float): `NS_Pond / ChamRece` (apenas para benchmark).

---

## 3. Estratégia de Evolução Incremental (Novas Variáveis)

Dada a dependência do mapeamento de outros projetos de BI (ex: People Analytics para Absenteísmo/Turnover), o ETL adotará uma **estratégia incremental**:

1. **Fase 1 (Core):** Implementação imediata das features listadas acima (Volumetria + Capacidade + Pausas), cujos dados já residem no Intraday/Metas.
2. **Fase 2 (Enrichment):** Conforme os projetos de BI paralelos liberarem suas views/tabelas, faremos *Left Joins* adicionais nesta view principal.
3. **Resiliência:** O pipeline Python deverá ser configurado para ignorar colunas de Fase 2 caso elas ainda não existam no schema, permitindo que o modelo "Core" rode sem bloqueios.

---

## 4. Lógica de Substituição de Nulos (Imputation)

Como usaremos `FULL OUTER JOIN`, teremos nulos. Regra de negócio para o ETL:

1. **Se Forecast for Nulo:** Assumir **0** (Operação não planejada).
2. **Se Real for Nulo:** Assumir **0** (Dados ainda não chegaram ou operação fechada).
3. **Se Divisão por Zero:** (ex: TMA Real sem atendidas): Retornar **0** ou manter Nulo para tratamento no Python (XGBoost lida bem com isso).

---

## 5. Pipeline Sugerido

1. **SQL Server**: View `[SmartCorr].[Vw_SmartCorr_Principal]` fazendo o `FULL JOIN` e agregando os tempos. (Fase 1 - Core).
2. **Python (`load_data.py`)**:
   * Lê a View.
   * Verifica dinamicamente quais colunas "extras" (Fase 2) estão presentes.
   * Cria Features de Janela (Lag): "Como foi o NS nos últimos 3 intervalos?".
   * Separa Treino/Teste (Time Series Split).
