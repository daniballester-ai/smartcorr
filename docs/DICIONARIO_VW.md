# Dicionário de Dados: View Principal (`VW_SMARTCORR_PRINCIPAL`)

Este documento consolida o dicionário de dados técnico e de negócios da view `[SmartCorr].[vw_SmartCorr_Principal]`, que é o coração analítico do projeto SmartCorr.

A visão atua unindo o **Core Operacional** (Intraday Realizado vs. Forecast de Metas) em blocos cravados de 30 minutos, cruzado com informações comportamentais e táticas do modelo **GO! (Gestão Operacional / RH)**.

---

## 🔑 1. Chaves de Granularidade (Primary Keys)

Campos responsáveis por definir a cardinalidade única de cada linha na tabela (Grão: `Programa + Canal + Data + Intervalo de 30 min`).

| Nome da Coluna  | Tipo SQL | Origem                      | Descrição e Regra de Negócio                                                                                    |
| :-------------- | :------- | :-------------------------- | :----------------------------------------------------------------------------------------------------------------- |
| `DataRef`     | `DATE` | `Intraday` / `Forecast` | Data do acontecimento ou da previsão operacional.                                                                 |
| `Intervalo`   | `TIME` | `Intraday` / `Forecast` | Agrupamento matemático limpo para blocos de 30 min (ex:*07:10* vira `07:00:00`, *07:40* vira `07:30:00`). |
| `CodPrograma` | `INT`  | `Intraday` / `Forecast` | Código CCMSID do Programa/Operação associada.                                                                   |
| `Canal`       | `INT`  | `Intraday` / `Forecast` | Código de identificação do canal de atendimento (Ex: Voice, Chat).                                              |

---

## 📈 2. Pilar Volumetria (Tráfego de Chamadas)

Indicadores que medem o fluxo real e esperado de interações no funil de atendimento.

| Nome da Coluna            | Tipo SQL | Origem                      | Descrição e Regra de Negócio                                                                                           |
| :------------------------ | :------- | :-------------------------- | :------------------------------------------------------------------------------------------------------------------------ |
| `Vol_Previsto`          | `INT`  | `Forecast`                | Demanda esperada calculada via Erlang-C (`chamrece`).                                                                   |
| `Vol_Real`              | `INT`  | `Intraday (Oferencidas)`  | Chamadas brutas recebidas/oferecidas pela rede matriz.                                                                    |
| `Vol_Atendidas`         | `INT`  | `Intraday (Atendidas)`    | Total de interações efetivamente capturadas e resolvidas <br />por agentes.                                             |
| `Vol_Atendidas_NS_Real` | `INT`  | `Intraday (Atendidas_NS)` | Volume de atendimentos finalizados<br />**dentro** da meta de tempo (SLA). É o Numerador <br />do *Target* real. |
| `Vol_Abandono`          | `INT`  | `Intraday (Aband)`        | Número de clientes que desligaram ou abandonaram a<br /> fila antes do transbordo para o operador.                       |

---

## 👥 3. Pilar Capacidade (Headcount) e Eficiência

Métricas brutas do esforço de trabalho e o dimensionamento real dos operadores.

| Nome da Coluna        | Tipo SQL          | Origem       | Descrição e Regra de Negócio                                                                                                                                            |
| :-------------------- | :---------------- | :----------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `HC_Previsto`       | `INT`           | `Forecast` | Quantidade ótima de operadores planejados para o <br />intervalo (`hcdime`).                                                                                            |
| `HC_Real_Equiv`     | `DECIMAL(10,2)` | `Intraday` | Falso proxy dinâmico de contagem. Divide o <br />tempo `TMP_DISPONIVEL` por `1800s`. Determina de forma <br />fracionária os **FTEs Equivalentes** contínuos. |
| `Pausa_Tecnica_Sec` | `INT`           | `Intraday` | Agrupamento crítico de perda sistêmica<br /> (*Sistema + Falha Sistêmica*). <br />Isolador oficial do hardware sobre o ofensor.                                       |
| `Pausa_Pessoal_Sec` | `INT`           | `Intraday` | Tempo em inatividade vitalícia <br />(*Lanche + Particular + Descanso + Saúde*). <br />Medidor de fuga de aderência NR17.                                             |
| `Pausa_Gestao_Sec`  | `INT`           | `Intraday` | Tempo planejado em gestão <br />(*Treinamento + Feedback + BackOffice*).                                                                                                |

---

## ⏱️ 4. Pilar TMA e Tempos Operacionais (Tráfego Base)

Métricas relacionadas à velocidade do processamento (TMA). Para evitar o Paradoxo de Divisão por Zero em DAX, todos os tempos estão em **Segundos Totais**.

| Nome da Coluna               | Tipo SQL    | Origem       | Descrição e Regra de Negócio                                                                                                                 |
| :--------------------------- | :---------- | :----------- | :---------------------------------------------------------------------------------------------------------------------------------------------- |
| `Tempo_AHT_Previsto_Total` | `INT`     | `Forecast` | Cálculo de normalização cruzado ponderado: Meta TMA <br />multiplicada pelo volume (`TMA * chamrece`). <br />Protege a matemática média. |
| `Tempo_AHT_Real_Total`     | `INT`     | `Intraday` | Tempo total agrupando desgaste de <br />Talk Time (`TMP_FALADO`) + Roteiro (`TMP_HOLD`) + <br />Tabulação pós-chamada (`TMP_POS_AT`).  |
| `Tempo_Espera_Total`       | `INT`     | `Intraday` | Tempo somado de latência na fila virtual (`TMP_ESPERA`).                                                                                     |
| `NS_Previsto_Erlang`       | `DECIMAL` | `Forecast` | Normalização para descobrir estatisticamente o <br />percentual oficial esperado: divide meta ponderada pelo `Vol_Previsto`.                |

---

## 🧠 5. Pilar Pessoas e Comportamento (Insights GO! e Machine Learning)

Cruzamento importado da infraestrutura `OdsCorp` diária. Tais colunas agem como modificadores de "onda" em ML, distribuídas ao longo de todos os intervalos daquele dia para justificar variações extremas fora do modelo Erlang.

| Nome da Coluna                | Tipo SQL  | Origem           | Descrição e Valor Analítico (Machine Learning / IA)                                                                                                               |
| :---------------------------- | :-------- | :--------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ABS_Tempo_Sec_Daily`       | `FLOAT` | `OdsFpw` / GO! | Numerador: Tempo total diário esvaído em furos (faltas). Separado do denominador e calculado em ML. <br />Seu aumento drena o NS.                                  |
| `ABS_Escala_Sec_Daily`      | `FLOAT` | `OdsFpw` / GO! | Denominador: O tempo programado formalmente (Escala) do time naquele dia.                                                                                            |
| `Turnover_Ativos_Daily`     | `INT`   | `OdsFpw` / GO! | Base fiel de capital humano ativo naquele dia específico.                                                                                                           |
| `Turnover_Desligados_Daily` | `INT`   | `OdsFpw` / GO! | "Taxa de Atrito". Picos indicam desgaste setorial intenso gerando provável degradação do <br />conhecimento (TMA elevado).                                        |
| `Ferias_Qtd_Daily`          | `INT`   | `OdsFpw` / GO! | "Fuga de Senioridade". Muitos funcionários em férias forçam novatos expostos ao atendimento, <br />reduzindo acerto na 1ª chamada (FCR).                         |
| `Faltas_Qtd_Daily`          | `INT`   | `OdsFpw` / GO! | "Gatilho de Severidade Operacional". Faltas agressivas quebram o planejamento logístico <br />diferente de atrasos mitigáveis.                                     |
| `WAHA_Qtd_Daily`            | `INT`   | `OdsFpw` / GO! | Quantitativo de logs remotos (Home Office). Isola falhas corporativas globais de oscilações <br />na rede elétrica ou residencial do agente (In Company vs WAHA). |

---

**Nota Técnica:** Para o processamento em Machine Learning (Python), variáveis de *KPIs Relativos* como `Taxa de Absenteísmo` e *Deltas* não residem no Banco de Dados. A view do SQL atua fornecendo variáveis massivas e cruas (Tempos e Quantidades absolutas), garantindo que a etapa de Engenharia de Features (`build_features.py`) calcule coeficientes de cruzamento livremente, o que fortifica o treinamento isolado de algoritmos como XGBoost e Random Forest.
