# Mapeamento de Variáveis: Visão de Negócio vs. Disponibilidade Técnica

Este documento consolida a análise de viabilidade técnica das variáveis idealizadas no esboço do projeto (`KPIs_Correlacao.png`) confrontadas com os dados reais disponíveis no Banco de Dados (`Intraday`) e fontes externas mapeadas.

---

## 🟢 1. Pilar Volumetria

| Variável Idealizada (Negócio)    | Variável Técnica<br />(SQL/DAX) | Status | Observação                                                                    |
| :--------------------------------- | :-------------------------------- | :----: | :------------------------------------------------------------------------------ |
| **Volume Recebido**          | `OFERECIDAS`                    |   ✅   | Dado bruto disponível na `f_Intraday`.                                       |
| **Volume Atendido**          | `ATENDIDAS`                     |   ✅   | Disponível. Base para cálculo de NS.                                          |
| **Abandono (Qtd/%)**         | `Taxa_Abandono` *(Calculado)* |   ✅   | Calculada via script (`build_features.py`).<br />Relevância preditiva altíssima. |
| **Forecast de Volume**       | `chamrece` (Meta)               |   ✅   | Disponível na tabela<br />`f_MetasIntradiariasForecast`.                     |
| **Desvio de Volume (Delta)** | `Desvio_Volume_Pct` *(Calc.)*   |   ✅   | Transformado via script (`build_features.py`)<br />para Percentual em vez de bruto. |
| **Sazonalidade (Dia/Hora)**  | `Dimension_Date`                |   ✅   | Derivável das colunas de data/hora.                                            |
| **Transferências**          | `Transf` (ODS)                  |   🟡   | Ausente no Intraday. Buscar no**OdsClient**.                              |
| **Indisp. Sistêmica**       | *Diário de Bordo*              |   ❌   | Fonte "Diário de Bordo" ainda não está pronta.                               |
| **Eventos Externos**         | *Diário de Bordo*              |   ❌   | (Clima, Propaganda). Fonte não pronta.                                         |

---

## 🟡 2. Pilar TMA (Tempo Médio de Atendimento)

| Variável Idealizada (Negócio)     | Variável Técnica<br />(SQL/DAX) | Status | Observação                                                                                                                                                          |
| :---------------------------------- | :-------------------------------- | :----: | :-------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **TMA Geral**                 | *(Calculado)*                   |   ✅   | Soma de<br />`TMP_FALADO` + `TMP_HOLD` + `TMP_POS_AT` / `ATENDIDAS`.                                                                                          |
| **Tempo Falado (Talk Time)**  | `TMP_FALADO`                    |   ✅   | Disponível.                                                                                                                                                          |
| **Tempo em Espera (Hold)**    | `TMP_HOLD`                      |   ✅   | Disponível.                                                                                                                                                          |
| **ACW (Pós-Atendimento)**    | `TMP_POS_AT`                    |   ✅   | Disponível.                                                                                                                                                          |
| **TME (Tempo Médio Espera)** | `TME_Real_Avg` *(Calc)*        |   ✅   | Transformado de Segundos Totais<br />para Média Absoluta via script.                                                                                |
| **Forecast de TMA**           | `TMA_Pond_Previsto`             |   ✅   | Requer normalização para evitar div. por zero ou<br /> "média de médias". Realizado no SQL multiplicando `TMA` pelo volume (`chamrece`), virando Tempo Total. |
| **Novatos (Curva)**           | `Tenure` (RH)                   |   🟡   | Cruzar Log (`program_ccmsid`) <br />com Data Admissão (RH/OdsFpw).                                                                                                 |
| **Lentidão Sistêmica**      | *Diário de Bordo*              |   ❌   | Fonte não pronta.                                                                                                                                                    |
| **Tabulação (Motivo)**      | *Tabulacao*                     |   ❌   | Esquema pronto,<br />dados não populados pelos analistas.                                                                                                            |
| **Processos**                 | *Diário de Bordo*              |   ❌   | Fonte não pronta.                                                                                                                                                    |

---

## 🔴 3. Pilar Pessoas (Aderência & Eficiência)

Este é o pilar mais crítico e com maior necessidade de integração de novas fontes.

| Variável Idealizada (Negócio)  | Variável Técnica<br />(SQL/DAX) | Status | Observação                                                                                                                                                                |
| :------------------------------- | :-------------------------------- | :----: | :-------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Headcount Logado (Qtd)** | `HC_Real_Equiv` (Parcial)       |   ✅   | O SQL divide o Total de Segundos Disponíveis do intervalo por 1800s (30 minutos).<br /> Isso dá a fração exata de FTEs (Full-Time Equivalent)equivalentes àquele slot. |
| **Headcount Planejado**    | `hcdime`                        |   ✅   | Disponível na tabela de metas.                                                                                                                                             |
| **Pausas Improdutivas**    | `Taxa_Pausa_Tecnica` *(Calc)* |   ✅   | Mapeado e convertido<br />em Métrica % via script.                                                                                                                        |
| **Pausas Pessoais (NR17)** | `Taxa_Pausa_Pessoal` *(Calc)* |   ✅   | Mapeado e convertido<br />em Métrica % via script.                                                                                                                        |
| **Pausas Gestão**         | `Taxa_Pausa_Gestao` *(Calc)*  |   ✅   | Mapeado e convertido<br />em Métrica % via script.                                                                                                                        |
| **Ocupação Operacional**  | `Taxa_Ocupacao` *(Calc)*      |   ✅   | Transforma Tempo_Alocado e HC<br />em Percentual de Fila.                                                                                                                |
| **Absenteísmo (ABS)**     | `ABS_Tempo_Sec`                 |   ✅   | Adicionado via `vw_factMicroGestao` (Relatório GO!).                                                                                                                     |
| **Gap de Log (Atraso)**    | `Escala` vs `Log`             |   🟡   | Disponível no**CRM (OdsClient)**.                                                                                                                                    |
| **Turnover**               | `Turnover_Desligados`           |   ✅   | Adicionado via `vw_factMicroGestao` (Relatório GO!).                                                                                                                     |
| **Férias**                | `Ferias_Qtd_Daily`              |   ✅   | Adicionado via `vw_factMicroGestao` (Relatório GO!).                                                                                                                     |
| **Faltas Totais**          | `Faltas_Qtd_Daily`              |   ✅   | Adicionado via `vw_factMicroGestao` (Relatório GO!).                                                                                                                     |
| **Alocação WAHA**        | `WAHA_Qtd_Daily`                |   ✅   | Adicionado via `vw_factMicroGestao` (Relatório GO!).                                                                                                                     |

---

## 4. Plano de Ação: Integração de Novas Fontes

Para cobrir os Gaps identificados (🟡), precisamos expandir o pipeline de dados para além do Intraday atual.

### Prioridade 1: OdsClient (CRM)

> *Essencial para refinar o pilar Pessoas e Volumetria.*

* **Variáveis:** `Transferências`, `Gap de Log`.
* **Ação:** Criar query no Schema `OdsClient` cruzando pelo `program_ccmsid`.

### Prioridade 2: OdsFpw (RH)

> *Essencial para qualificar o Staff (Novatos vs Experientes).*

* **Variáveis:** `Data de Admissão` (para cálculo de Novatos).
* **Ação:** Importar base de ativos D-1 e cruzar com os logins do dia.

### Prioridade 3: Diário de Bordo (Futuro)

> *Dependência Externa.*

* **Variáveis:** `Indisponibilidade Sistêmica`, `Eventos Externos`, `Processos`.
* **Status:** Aguardar desenvolvimento da ferramenta pela equipe responsável. Por enquanto, o modelo tratará esses ofensores como "Outliers explicados pelo Resíduo".

---

## Legenda de Status

* ✅ **Pronto:** Já disponível na `f_Intraday` ou `f_Metas`.
* ⚠️ **Cálculo:** Requer engenharia de features no Python.
* 🟡 **Integração:** Disponível em outro banco (ODS), requer nova Query.
* ❌ **Bloqueado:** Fonte de dados ainda não existe ou não está populada.
