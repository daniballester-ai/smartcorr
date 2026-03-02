# Estratégia de Arquitetura XAI e Modelagem de Dados - SmartCorr

Este documento serve como material de alinhamento com stakeholders para demonstrar como o projeto SmartCorr evoluiu de um modelo preditivo tradicional (visão restrita ao número final) para uma **Plataforma de Decisão Causal (Database-centric)** focada no plano de ação ágil.

---

## 1. Da Previsão Simples à Plataforma de Decisão (Visão XAI - Explainable AI)

A arquitetura do processo não entrega apenas qual será o Nível de Serviço (NS) futuro. Ela implementa **SHAP Values (SHapley Additive exPlanations)**, um dos conceitos mais robustos e matematicamente elegantes da área de *Explainable AI* (IA Explicável). 

> **A Base Matemática e o Prêmio Nobel:**
> O conceito original (Valor de Shapley) foi fundamentado na **Teoria dos Jogos Cooperativos** pelo matemático Lloyd Shapley, o que lhe rendeu o **Prêmio Nobel de Economia em 2012**. O algoritmo foi desenhado para distribuir de forma rigorosamente justa o "ganho" (resultado) entre vários jogadores (variáveis) que colaboram para um evento.

> **A Integração Tecnológica (TreeSHAP no XGBoost):**
> O framework moderno SHAP (2017) traduz essa matemática complexa para a IA. No projeto SmartCorr, utilizamos a variante computacional **TreeSHAP**, que é uma aproximação extremamente eficiente e nativamente otimizada para o nosso algoritmo de Gradient Boosting (**XGBoost**). 
> *Prova Científica do Algoritmo: ['A Unified Approach to Interpreting Model Predictions' (Lundberg & Lee, 2017)](https://www.researchgate.net/publication/317062430_A_Unified_Approach_to_Interpreting_Model_Predictions)*

Amparado por essas propriedades matemáticas universais de "Aditividade" (Local Accuracy), o modelo ganha uma confiabilidade irrefutável. Isso significa que, além de prever que o NS vai fechar em `63%` às 15:00, a IA abre a sua "caixa-preta" e distribui as responsabilidades numéricas exatas do que puxou esse indicador para cima ou para baixo.

### A. A Visão Macro: Agrupamento por Pilares (Feature Grouping)
Em vez de devolver sentenças matemáticas avulsas pontuais, o algoritmo Python empacota todas as mais de 20 variáveis analisadas e as amarra aos 3 Pilares operacionais de Negócio:
*   **Pessoas** (Faltas, Headcount, Pausas...)
*   **Volumetria** (Volume de chamadas, Abandonos...)
*   **TMA** (Velocidade e Tempo Operacional)

Dessa forma, a Tabela Fato (`FactSmartCorr_Previsao`) registra o saldo financeiro exato de cada um na meta.
**Exemplo Prático na Tabela:**
*   `NS_Previsto`: **63%**
*   `Impacto_Pilar_Pessoas`: **-15%** *(O maior destruidor da meta neste bloco)*
*   `Impacto_Pilar_Volumetria`: **-5%** *(Volume excedente leve auxiliou na queda)*
*   `Impacto_Pilar_TMA`: **+3%** *(O TMA rápido atuou como amortecedor, evitando uma tragédia pior)*

Essa estrutura Wide (larga) permite que o Frontend (Next.js, API ou Power BI) monte um **gráfico de Cascata (Waterfall)** sem necessitar de cálculos complexos em servidor de aplicação ou DAX.

---

## 2. Visão Micro: Ofensores e Impulsionadores (Causa Raiz)

Saber que o Pilar "Pessoas" caiu 15% é um ótimo sinal direcional para o executivo. Mas para o gerente agir na causa, ele pergunta imediatamente: *"O que, dentro de pessoas, deu ruim?"*.

Para isso, modelamos o agrupamento tático. O sistema salva na Tabela Fato localizadores específicos dos **Top 3 Ofensores e Top 3 Impulsionadores**, traduzidos em linguagem de negócio:

### 🚨 Ofensores (Detractors)
*   **Top 1:** `Inércia da Fila (Lag)` | Pilar Contexto_Lags | `-10%`
*   **Top 2:** `Taxa de Abandono` | Pilar Volumetria | `-8%`
*   **Top 3:** `Pausa Técnica` | Pilar Pessoas | `-5%`

### 🏆 Impulsionadores (Boosters)
Para fins de motivação ou reconhecimento sistêmico do que está salvando a operação naquele recorte:
*   **Top 1:** `TMA Real Baixo` | Pilar TMA | `+3%`
*   *(Os demais ausentes registram a nomenclatura padrão "Sem Impacto Relevante" e "0%", limpando a tela do BI para evitar ruídos cognitivos).*

> **O Grande Benefício (Frontend Development):**
> O desenvolvedor Mobile ou React/Next.js não precisa aprender DAX e não precisa ter regras de negócio no código dele. Ao enviar uma requisição `GET /previsao`, ele puxa o pacote mastigado do banco de dados e simplesmente exibe na tela o alerta vermelho e a causa raiz já mastigada.

---

## 3. O Fator de "Inércia" Operacional (Sinal de Fumaça)
Adicionamos ao contexto as variáveis Defasadas (`Lags`). O destaque é o **`NS_Lag_1`**, que armazena a fotografia do exato nível de serviço do intervalo anterior ao planejado.

**Motivo Operacional:** No tráfego de Control Desk, quedas geram "bolas de neve" (Enfileiramento / Backlog). Se o algoritmo prever um NS sofrível de `50%` para as 14:30h com quadros perfeitos de operadores em tela, o gestor poderá questionar o viés da IA. Porém, lendo a variável `NS_Lag_1` de **`30%`**, o gestor rapidamente tem o contexto de que a equipe atual ainda está drenando a fila gigantesca da quebra anterior à eles. É uma calibragem fundamental de expectativa do "Sinal de Fumaça".

---

## 4. Engenharia de Ingestão e Processamento SQL Server

Para suprir toda essa complexidade e dezenas de colunas preditivas preservando o Banco de Dados Relacional, as seguintes técnicas de MLOps foram adotadas:

### Carga Idempotente (Delete + Insert Cirúrgico)
A Tabela Fato **não sofre Truncate total** para permitirmos eventual análise retroativa (Evolução vs Erro do erro modelo ao longo das semanas). 
O pipeline Python, toda vez que é disparado, trabalha sobrepondo predições antigas sem usar comandos lentos como `UPDATE` linha a linha. Como bancos de dados relacionais são muito mais lentos fazendo atualizações isoladas do que inserindo dados novos em lote, a ferramenta utiliza o conceito de **"Delete Cirúrgico + Insert"** baseado na técnica de **Rolling Forecast (Previsão Contínua)**. 

Ele executa um *delete cirúrgico* condicionado apenas para a Data que será re-projetada e injeta o bloco atualizado de predições, o que impede duplicações e é altamente performático de processar. 

O código não possui datas fixas predefinidas (ex: "apague D-1"). Ele é dinâmico e avalia **exclusivamente o novo pacote de dados recém-processado da IA**:
1. O Python avalia o novo bloco de previsões gerado.
2. Agrupa tudo por Data (`DataRef`) e descobre qual é o **primeiro (menor) horário previsto** dentro daquela data.
3. Exclui no banco de dados **apenas daquele horário para frente** naquela respectiva data.
4. Por fim, insere todo o novo bloco em lote.

Isso garante que tudo o que estava "antes" daquele momento (que já se consolidou como passado e realidade) fique intacto, permitindo o cruzamento de "expectativa vs realidade" para medição assertiva da acurácia do modelo ao longo do tempo.

#### Exemplos Práticos do Rolling Forecast:

*   **Cenário 1: Primeira rodada (Ex: 10:00 da manhã de 28/02)**
    *   **Previsões criadas pela IA:** `28/02 das 10:30 até as 23:59`.
    *   **Ação do Python:** Busca o menor horário (10:30). Exclui no banco `DataRef = '2026-02-28'` a partir do `Intervalo >= '10:30'`. Em seguida, insere os dados novos em formato lote. 

*   **Cenário 2: Rodada do meio do dia (Ex: 14:00 da tarde de 28/02)**
    *   **Previsões criadas pela IA:** `28/02 das 14:30 até as 23:59`.
    *   **Ação do Python:** Busca o novo menor horário (14:30). Exclui no banco `DataRef = '2026-02-28'` a partir do `Intervalo >= '14:30'`.
    *   **Resultado do Banco:** As previsões matutinas originais (das 10:30 às 14:00) são **preservadas**, servindo como registro auditável permanente do panorama esperado pela IA na parte da manhã, permitindo análises ricas de variabilidade no Power BI.

*   **Cenário 3: Rodada de virada de dia (Para prever o próximo dia - Ex: 01/03)**
    *   **Previsões criadas pela IA:** `01/03 do horário 00:00 até 23:59`.
    *   **Ação do Python:** Exclui tudo do dia 01/03 (`Intervalo >= '00:00'`) e insere.
    *   **Resultado do Banco:** Todas as predições salvadas ao longo do dia recém fechado (28/02) se mantêm invioladas. O histórico contínuo da Tabela Fato é rico e sem dependência de Truncates.

### O Poder do `fast_executemany`
Se enviássemos um simples Insert Massivo para prever um dia inteiro do contact center via biblioteca `pyodbc`, a rede sofreria envio e recebimento (roundtrips) de linha a linha, durando até 15 minutos e gerando atraso visual no projeto. 

Através da propriedade `cursor.fast_executemany = True`, o Python habilita os **Table-Valued Parameters** do driver ODBC nativo do Microsoft SQL Server. Ele "amassa" milhares de registros (Previsões, Impactos de Pilares, Listas de Ofensores do SHAP) em um arquivo binário único hospedado na memória RAM, enviando esse bloco atômico inteiro de uma só vez para o SQL Server. 

*(Duração Prática: 10 minutos de gravação são transformados em 1-2 segundos absolutos, preservando a cultura Near Real-Time da arquitetura).*

---

## 5. Diferencial Técnico: Erlang C vs. Modelo Empírico (ML)

Atualmente, muitas operações (como o *Intraday BI*) utilizam a fórmula teórica de **Erlang C** calculada externamente. O SmartCorr propõe uma evolução significativa:

| Abordagem              | Erlang C (Teórico)                                                       | XGBoost (SmartCorr)                                                                              |
| :--------------------- | :------------------------------------------------------------------------ | :----------------------------------------------------------------------------------------------- |
| **Premissa**     | Assume eficiência perfeita<br />(Paciência infinita, chegadas Poisson). | Aprende o comportamento<br />**real** da operação (Ineficiências, pausas fora de hora). |
| **Aderência**   | Tende a superestimar a capacidade<br />em cenários caóticos.            | Ajusta-se à "sujeira" do dia-a-dia,<br />capturando padrões ocultos.                           |
| **Manutenção** | Requer parâmetros fixos (AHT ideal).                                     | Requer apenas histórico de dados<br />(aprende novo AHT automaticamente).                       |

**Conclusão:** O SmartCorr não *calcula* Erlang; ele *descobre* a curva de capacidade real da sua operação, resultando em dimensionamentos mais seguros.

---

## 6. Robustez da Engenharia (MLOps)

Para garantir que essas respostas estejam disponíveis sempre que necessárias e operem em escala nas tabelas:

* **Pipeline Resiliente:** O sistema trata automaticamente falhas de conexão (ex: *timeouts* de banco), operando com dados em cache ou degradando graciosamente sem travar a operação.
* **Retreino Contínuo:** O modelo aprende com os dados mais recentes (janela deslizante), adaptando-se a mudanças sazonais ou de perfil de atendimento sem intervenção manual.
