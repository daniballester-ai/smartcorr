# Dicionário de Dados Semântico - Frontend BI (SmartCorr)

**Fonte de Dados (SQL):** `SmartCorr/SQL/QUERY_FRONTEND_BI.sql`
**Última Atualização:** Março de 2026
**Objetivo:** Este documento descreve as saídas da Camada Semântica otimizada para o Front-end. A tabela consolida os Fatos Reais do Call Center (via Erlang/Avaya) com as Previsões de Machine Learning (XGBoost) e valores de impacto preditivo (SHAP Values).

---

## 1. Chaves da Operação (Dimensões Base)

Essas colunas definem a granularidade primária da linha de dado (Quando, Onde e Como).

| Coluna          |   Tipo   | Descrição / Cálculo                                             |
| :-------------- | :------: | :----------------------------------------------------------------- |
| `DataRef`     | `DATE` | Data referência da operação.                                    |
| `Intervalo`   | `TIME` | Bloco de 30 minutos em formato de hora padrão (ex:`10:30:00`).  |
| `CodPrograma` | `INT` | ID único identificador  / Skill (Fila Pagbank).                  |
| `Canal`       | `INT` | Código do meio de atendimento (Sempre `7` para o canal de Voz). |

---

## 2. Métricas de Volume (Real vs Previsto)

Representam a pressão de demanda que chega até a porta do banco / URA.

| Coluna                    |   Tipo   | Descrição / Cálculo                                                                                                                                              |
| :------------------------ | :-------: | :------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `Vol_Real`              |  `INT`  | Total de ligações que efetivamente entraram na fila (Demand).                                                                                                     |
| `Vol_Previsto`          |  `INT`  | Total de ligações que o setor de Planejamento (*WFM - Erlang*) previu que entrariam.                                                                            |
| `Delta_Volume`          |  `INT`  | **Cálculo:** `(Vol_Real - Vol_Previsto)`. Mostra a diferença bruta. Se positivo (+), a URA está recebendo mais gente <br />do que o planejado (ofensor). |
| `Vol_Atendidas`         |  `INT`  | Total de ligações que conseguiram falar com o operador humano.                                                                                                    |
| `Vol_Atendidas_NS_Real` |  `INT`  | Total de lig. atendidas dentro do SLA limite de tempo de espera.                                                                                                    |
| `Vol_Abandono`          |  `INT`  | Total de clientes que desligaram na cara da URA (Tempo de Espera Estourou).                                                                                         |
| `Taxa_Abandono_Atual`   | `FLOAT` | **Cálculo:** `Vol_Abandono / Vol_Real`. O percentual exato (0 a 1) do nível de desistência atual.                                                        |

---

## 3. Métricas de Capacidade / Pessoas (Real vs Previsto)

Representam os recursos humanos na frente de batalha para escoar os volumes da camada anterior.

| Coluna                   |   Tipo   | Descrição / Cálculo                                                                                                                                                 |
| :----------------------- | :-------: | :--------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `HC_Real_Equiv`        | `FLOAT` | "Headcount Equivalente". Número de pessoas reais logadas atendendo na meia hora.                                                                                      |
| `HC_Previsto`          |  `INT`  | Total de operadores que deveriam estar na cadeira pelo planejamento <br />escalado `(Erlang)`.                                                                       |
| `Delta_HC`             | `FLOAT` | **Cálculo:** `(HC_Real - HC_Previsto)`. Sobra ou Falta de Pessoas. Se negativo (-), significa furo de escala.                                                 |
| `Faltas_Qtd_Daily`     |  `INT`  | Número absoluto dimensional de operadores ausentes (Não bateram ponto hoje).                                                                                         |
| `Ferias_Qtd_Daily`     |  `INT`  | Número absoluto dimensional de operadores logados como em período<br /> de férias para esse setor.                                                                  |
| `ABS_Taxa_Daily_Atual` | `FLOAT` | **Cálculo:** `(Tempo das faltas em segundos / Tempo da Escala Global)`. Qual a % do call center inteiro que faltou hoje, trazendo um KPI consolidado (0 a 1). |

---

## 4. Métricas de Tempo (TMA, TME, Pausas)

Representam a velocidade ou lentidão com as quais as transações/atendimentos ocorrem, provando a eficiência da operação em tempo real.

| Coluna                  |   Tipo   | Descrição / Cálculo                                                                                                                                           |
| :---------------------- | :-------: | :--------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `TMA_Real_Agora`      | `FLOAT` | **Cálculo:** `AHT_Real_Total / Vol_Real`. O Tempo Médio de Atendimento (em segundos) que a operação de fato está <br />conseguindo entregar agora.  |
| `TMA_Previsto_Erlang` | `FLOAT` | **Cálculo:** `AHT_Previsto_Total / Vol_Previsto`. O TMA que a operação "sonhava"/planejou entregar.                                                   |
| `TME_Real_Agora`      | `FLOAT` | **Cálculo:** `Espera_Total / Vol_Atendidas`. O Tempo Médio de Espera na URA antes de alguém dizer "Alô". Um `TME` alto explode o `Vol_Abandono`. |
| `Pausa_Tecnica_Sec`   |  `INT`  | Somatório das pausas improdutivas operacionais (ex: Queda de Sistema).                                                                                          |
| `Pausa_Pessoal_Sec`   |  `INT`  | Somatório das pausas NR17 / Banheiro feitas pela equipe alocada no intervalo.                                                                                   |

---

## 5. Métricas Principais (Batalha: Nível de Serviço Real vs IA)

São as estrelas do sistema e os KPIs de negócio principais para os quais tudo é desenhado.

| Coluna                               |   Tipo   | Descrição / Cálculo                                                                                                                                                                   |
| :----------------------------------- | :-------: | :--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Nivel_Servico_Real_Ate_Agora`     | `FLOAT` | **Cálculo:** `Vol_Atendidas_NS_Real / Vol_Real`. O SLA Crudo e atual da operação <br />entregue pela base da CTI. <br />Limite de 0.0 a 1.0 (0% a 100%).                      |
| `Nivel_Servico_Previsto_IA`        | `FLOAT` | O que o Algoritmo XGBoost (`SmartCorr`) está prevendo de forma acurada para o Nível de Serviço. Diferente do Erlang,<br /> ele considera comportamento de fila e inércia do tempo. |
| `Nivel_Servico_Meia_Hora_Anterior` | `FLOAT` | O estado cronológico exatamente da meia hora passada `(NS_Lag_1)`. Excelente para exibir em setas (Crescimento x Queda) no painel.                                                    |

---

## 6. Análise Macro: XAI Cascata (*Causas - Pilares*)

O algoritmo atribui "pesos percentuais de culpa" (+ ou -). A soma da linha de base algorítmica + Pilares = `Nivel_Servico_Previsto_IA`.
*Se um pilar estiver negativo (ex: -0.15), significa que a categoria foi responsável por deduzir 15% do Nível de Serviço potencial desse horário.*

| Coluna                       |   Tipo   | Visão da Categoria Algorítmica                                                                                 |
| :--------------------------- | :-------: | :--------------------------------------------------------------------------------------------------------------- |
| `Impacto_Pilar_Pessoas`    | `FLOAT` | Variáveis como HC, Desvios de HC, Pausas e Faltômetros formam a culpabilidade<br /> final de RH.               |
| `Impacto_Pilar_Volumetria` | `FLOAT` | Desvios de Demanda e Taxas de Abandono (Pressão entrante do cliente).                                           |
| `Impacto_Pilar_TMA`        | `FLOAT` | O quanto as conversas demoradas ao telefone `(TMA) / TME` afetaram a<br /> quebra de contrato.                 |
| `Impacto_Pilar_Contexto`   | `FLOAT` | A Sazonalidade (Ser segunda-feira, ser meio dia, ou inércia da URA já <br />estar engargalada historicamente). |

---

## 7. Análise Micro (*TOP 3 Ofensores e Impulsionadores*)

A cereja do bolo. Ao invés da diretoria precisar somar ou tentar adivinhar a correlação de Pearson acima, o SHAP já separou com nomes em texto claro quais foram as exatas colunas do banco que mais derrubaram e mais ajudaram o SLA de cada momento.

| Coluna                                        |    Tipo    | Descrição no Card do Dashboard                                                                                                                         |
| :-------------------------------------------- | :---------: | :------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Ofensor_1_Nome<br>`(até o `3`)          | `VARCHAR` | O rótulo em texto puro. Ex:*"Desvio_Volume_Pct_Lag_1"*. Focado no Top 1 a 3 que <br />**mais derrubaram a operação.**                         |
| `Ofensor_1_Peso_NS<br>`(até o `3`)       |  `FLOAT`  | Um valor obrigatoriamente negativo (ex:`-0.20`), ditando a exata intensidade do <br />Dano no SLA da pior variável, da segunda <br />e terceira pior. |
| `Ofensor_1_Pilar<br>`(até o `3`)         | `VARCHAR` | Para o caso do BI querer agrupar os problemas soltos em Cores <br />(Ex: Cor Azul de Pessoas).                                                           |
| `Impulsionador_1_Nome<br>`(até o `3`)    | `VARCHAR` | A Variável (Dentre todos as analisadas) que mais jogou o SLA<br />**para cima** resgatando o atendimento para algo aceitável. (Top 1, 2 e 3).    |
| `Impulsionador_1_Peso_NS<br>`(até o `3`) |  `FLOAT`  | O valor da "Bóia de Salvação". Ex:`+0.42` de SLA recuperado pelo esforço do TMA que foi rápido demais.                                            |
| `Impulsionador_1_Pilar<br>`(até o `3`)   | `VARCHAR` | Categoria na qual a ajuda se enquadra.                                                                                                                   |
