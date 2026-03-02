# Relatório de Enriquecimento de Variáveis: Modelo SmartCorr

Este documento detalha o dicionário de variáveis consolidadas na construção da `VW_SMARTCORR_PRINCIPAL`. O relatório separa os indicadores do escopo inicial de Operações (Realizado vs. Planejado) das novas features comportamentais de RH implementadas após a engenharia reversa do modelo em Power BI (GO! Gestão Operacional).

---

## 1. Variáveis Existentes (Fase 1 - Core Operacional)

A fundação do dataset foi construída a partir do alinhamento intradiário (blocos de 30 minutos) cruzando o comportamento "Real" com as "Metas".

### 1.1 Escopo Realizado (`factIntradayDelivery`)

- **Vol_Real (Oferecidas), Vol_Atendidas, Vol_Atendidas_NS, Vol_Abandono:** Controlam e medem o fluxo real de chamadas no funil do atendimento.
- **TMP_SERVICO (Logado), TMP_FALADO, TMP_POS_AT, TMP_HOLD, TMP_ESPERA:** Tempos processados em segundos essenciais para medições de TMA, fluidez sistêmica, fricções da chamada e o tempo base da fila.
- **TMP_DISPONIVEL:** Ociosidade (Idle Time). Utilizado com sucesso como Proxy para quantificar o `HC_Real_Equiv` na visão de 30 minutos.
- **Agrupamentos de Pausas (`Pausa_Tecnica_Sec`, `Pausa_Pessoal_Sec`, `Pausa_Gestao_Sec`):** Pausas brutas consolidadas pela inteligência de negócio original (Sistema, Intervalo NR17, Lanche, Feedback, etc.). Isolam o ofensor real da ineficiência operacional por ofensores macro.

### 1.2 Escopo Planejado (Forecast via ERFM)

- **Vol_Previsto, HC_Previsto:** Curva diária de escalonamento prevista originalmente para a Operação em 30 min.
- **NS_Pond_Previsto e TMA_Pond_Previsto:** Componentes não relativos (SLA * Volume) que protegem a matemática da ferramenta ao efetuar cálculos agregados de Target.

---

## 2. Novas Variáveis Incorporadas (Fase 2 - RH & Analytics com GO!)

A partir da exploração das métricas em DAX (`Medidas.tmdl` e `factMicroGestao.tmdl`) do modelo em PowerBI, deciframos a origem técnica real de grandes ofensores do negócio na View Nativa `[OdsCorp].[DataMart].[vw_factMicroGestao]`.

A inteligência de inclusão na infraestrutura de Machine Learning adotou as premissas diárias, espalhando essas dimensões daquele dia por todo o intervalo dos blocos de 30 min.

### 2.1 Variáveis Idealizadas pelo Mapeamento de Negócio

1. **Absenteísmo de Longo Prazo / Faltas (ABS)**

   - **Variáveis Adicionadas:** `ABS_Tempo_Sec_Daily` (Tempo total de ausência em segundos) e `ABS_Escala_Sec_Daily` (Tempo total escalado em segundos).
   - **Cálculo Base (SQL):** `SUM(AbsenteeismTime)` e `SUM(ScheduledWorktime)`.
   - **Por que não trouxemos o percentual (%) pré-calculado?** Em Machine Learning e Análise Exploratória, trabalhar com médias de percentuais consolidados em banco de dados gera distorções matemáticas graves (Paradoxo de Simpson). Importando isoladamente o "Numerador" e o "Denominador", o modelo em Python recalcula a taxa (`ABS_Tempo / ABS_Escala`) de forma unificada, independente do recorte semanal ou dos grupos intradiários montados.
   - **Importância para a I.A.:** O Absenteísmo é o maior inimigo da volumetria projetada. Ao cruzar essas dimensões contra o target real (Ex: abandono ou SLA), o algoritmo matemático aprenderá o "peso real" dessa falta, determinando o quanto "1% a mais de ABS" destrói efetivamente o Nível de Serviço e esgota os ativos disponíveis naquele dia.
2. **Taxa de Atrito de Recursos (Turnover / Rotatividade)**

   - **Variáveis Adicionadas:** `Turnover_Ativos_Daily` (Contagem de colaboradores ativos no cenário diário) e `Turnover_Desligados_Daily` (Contagem de profissionais desligados).
   - **Cálculo Base (SQL):** Sumarização ultra-rápida de flags através de `MAX/SUM` onde `GeneralStatusCode = 1` representa Ativos, e `TypeTurnOver > 0` capta exclusões processadas em D-X.
   - **Importância para a I.A.:** Mais do que reduzir HeadCount natural, altos picos de rotatividade são fortes sinais de "Sangramento Operacional e Qualitativo". Setores ou dias marcados com picos recentes de desligamentos deixam sequelas diretas no desgaste sistêmico e afetam drasticamente a média de TMA, pois há perda de ativos capacitados. O modelo aprenderá a prever as "ondas de lentidão" (Tempos longos de hold e fila) originadas nestes picos de TurnOver.

### 2.2 Variáveis Adicionais (Features e Achados de Correlação no Código)

Durante a engenharia reversa no projeto Power BI (GO!), localizamos 3 variáveis de **altíssimo poder preditivo** disponíveis, e optamos por injetá-las no nosso modelo sem custo. Elas agem como *Modificadoras de Sintomas*, capturando distorções logísticas de RH que os softwares preditivos tradicionais ignoram:

1. **Deficiência Qualitativa de Férias (Fuga de Senioridade)**

   - **Variáveis Adicionadas:** `Ferias_Qtd_Daily` (Quantidade de profissionais mapeados formalmente em período de férias naquele dia).
   - **Cálculo Base (SQL):** Sumarização de recursos pelo enquadramento de negócio clássico do FPW (`GeneralStatusCode = 2`).
   - **Importância para a I.A.:** Modelos padrões como a fórmula Erlang-C olham apenas pro número final do HeadCount escalado. O "lado obscuro" ignorado consiste na *qualidade da escala de hoje*. O período de férias convencionais frequentemente escoa um robusto núcleo formador de Seniores experientes e super eficientes, expondo os "Novatos" no *front* de atendimento. A consequência direta é a explosão do Tempo de Retenção e redução do *First Call Resolution* (Primeira Ligação Resolvida). A variável dá o "poder de visão em Raio-X" pro SmartCorr compreender exatamente o motivo pelo qual um mesmo volume de chamadas resultou em duas métricas tão divergentes.
2. **Severidade Operacional de Ruptura (Faltas)**

   - **Variáveis Adicionadas:** `Faltas_Qtd_Daily` (Número bruto de ocorrências/falhas integrais logadas).
   - **Cálculo Base (SQL):** Captamento do estopim de distanciamento, usando a medição via `SUM(LackOfWorkday)`.
   - **Importância para a I.A.:** Diferencia "Absenteísmo de Atrasos" de um "Abandono Brutal". Atrasos pingados geram perturbações mitigáveis, mas as faltas da totalidade de jornada produzem cristas inefáveis de pressão sobre a escala. Isso servirá de "gatilho de severidade", mostrando ao Python como classificar impactos severos na malha horária.
3. **Carga e Suscetibilidade Logística Domiciliar (WAHA)**

   - **Variáveis Adicionadas:** `WAHA_Qtd_Daily` (Quantificativo de acessos originados via rede remota residencial - Home Office).
   - **Cálculo Base (SQL):** Isolamento métrico em `FlagWaha = 1` versus operações consolidadas nas *Sites* da companhia.
   - **Importância para a I.A.:** Agentes em log domiciliar oscilam sua aderência e sua *Pausa Técnica* de modos diametralmente impares. Ao ter x logados internamente (`In Company`) contra y conectados virtualmente (`WAHA`), o algoritmo passará a isolar os surtos sistêmicos logais (Quedas de energia locais, indisponibilidade local de internet, perturbações perimetrais), justificando *Lentidões por Força Maior*, não confundindo a Inteligência em penalizar a eficiência mecânica da operação por problemas puramente de natureza predial ou residencial.
