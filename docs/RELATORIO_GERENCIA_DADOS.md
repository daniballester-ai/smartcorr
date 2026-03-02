# Arquitetura e Engenharia de Dados do SmartCorr

**Para:** Gerência de Informação / Data Analytics
**Assunto:** Homologação Técnica do Pipeline de Machine Learning (XGBoost + SHAP)
**Objetivo:** Transparência nos cálculos estatísticos, arquitetura de extração, mitigação de Data Leakage e validação das saídas geradas para consumo no Power BI.

---

## 1. Origem: O que estamos extraindo? (`load_data.py`)

Toda a inteligência do projeto é alimentada por uma Query parametrizada focada no core business real.

* **Fonte:** `[OdsCorp].[SmartCorr].[vw_SmartCorr_Principal]`
* **Filtros Físicos:**
  * Janela Deslizante de 120 dias Corridos (Atualizada incrementalmente no SQL).
  * Filtragem Tática de Programs específicos (Operações **Pagbank**).
  * `[Canal] = 7` (Somente Voz).
* **A "Massa" de Variáveis Brutas:** Puxamos 24 colunas absolutas da view, estruturadas nos seguintes blocos lógicos:
  1. *Erlang (Previsão do Planejamento):* `Vol_Previsto`, `HC_Previsto`, `Tempo_AHT_Previsto_Total`.
  2. *Capacidade Praticada (Real):* `HC_Real_Equiv` e Carga de Ineficiência em Segundos (`Pausa_Tecnica_Sec`, `Pausa_Pessoal`, `Pausa_Gestao`).
  3. *Demanda Praticada (Real):* `Vol_Real`, `Vol_Atendidas`, `Vol_Atendidas_NS_Real`, `Vol_Abandono`.
  4. *Velocidade Média Total:* Somatório real de Segundos Falados e de Espera na URA (`Tempo_AHT_Real_Total`, `Tempo_Espera_Total`).
  5. *Saúde Operacional BroadCasted (Métricas Diárias de RH):* Volumes Dimensionais de Qtd de Faltas, Qtd de Férias, WAHA, Tempo Segundos Ausentes Absoluto na Escala (Absenteísmo), Turnover.

---

## 2. Processamento e Engenharia: Como estamos calculando? (`build_features.py`)

Não inserimos Números Dimensionais soltos em uma Rede de Regressão. O script injeta o conceito de *Sensação Térmica e Compressão Escalar*. **Importante: Tudo abaixo é deslocado temporariamente como LAG (-30 min) para que a IA não sofra *Data Leakage* advinhando o presente com os dados do próprio presente.**

1. **Engenharia de Erros (% de Erro Erlang):** Transformamos Volumes absolutos em Margem de Erro de Previsão na operação:
   * `Desvio_Volume_Pct` = `(Vol_Real - Vol_Previsto) / Vol_Previsto`
   * `Desvio_HC_Pct` = `(HC_Real_Equiv - HC_Previsto) / HC_Previsto`
2. **Engenharia de "Exaustão dos Recursos" (Taxas de Segundos):** Calculamos as pausas através do seu impacto na aderência global (Total da equipe * 1800 seg do intervalo totalizando o Banco de Tempo da Meia-Hora).
   * `Taxa_Pausa_Tecnica` = `Pausa_Tecnica_Sec / Capacidade_Total_Equipe`
   * `Taxa_Ocupacao` = `(Tempo_Fala + Tempo_Espera) / Capacidade_Total_Equipe`
3. **Engenharia de Gargalo Físico do Cliente:**
   * `TME_Real` = `Tempo_Espera_Total / Vol_Atendidas` (Com safe-guard contra Div/Zero).
   * `Taxa_Abandono` = `Vol_Abandono / Vol_Real`
4. **Inércia Temporal (Lags de Fila):** O modelo é forçado matematicamente a receber o exato `Nível_De_Servico` real de 1, 2 e 3 períodos anteriores, herdando os estouros do Erlang C.

---

## 3. Saída: A Tabela Fato (`predict.py`)

A Injeção Cíclica de 30 em 30 min realiza um *Soft Delete* seguido por um *Bulk Insert Incremental* via `fast_executemany` do Python com 31 novas colunas dimensionadas:

* **Destino:** `[OdsCorp].[SmartCorr].[FactSmartCorr_Previsao]`
* **O NS da Máquina:** Consolidação preditiva pura através da coluna `[NS_Previsto_SmartCorr]`. E de bônus, anexamos a fotografia estática dos Erlangs do momento do cálculo (HC, Vol e AHT previstos).
* **Explainable AI (Algoritmo SHAP Value):** Traduzimos a curva Log-Loss do XGBoost salvando os tensores textuais e vetoriais de culpa individual e macro (Variáveis de Pilar):
  * `[Impacto_Pilar_Contexto]`, `[Impacto_Pilar_Pessoas]`, `[Impacto_Pilar_TMA]`, `[Impacto_Pilar_Volumetria]`
  * Lista tabular plana explicitando Textualmente os `Ofensor_Nome_1`, `Ofensor_Nome_2`, `Ofensor_Nome_3` (Top detratores) e seu inverso: Os Impulsionadores que "salvaram/ajudaram" a meta.

---

## 4. Apresentação End-to-End: O consumo no Power BI Cloud

A arquitetura final do projeto foi construída para alimentar nativamente o nosso Power BI Cloud.

*   **O Consumo Principal:** O Power BI puxa os dados e a matriz de explicação diretamente e unicamente da **Tabela Fato Preditiva** (`[FactSmartCorr_Previsao]`), onde já entregamos os KPIs e as métricas de SHAP Value calculadas na ponta. 
*   **A "Query de Auditoria" (`QUERY_FRONTEND_BI.sql`):** Adicionalmente, deixamos salva no projeto uma Query SQL auxiliar. Ela serve exclusivamente para que a gerência e os analistas possam **ver os dados lado a lado** direto no SGBD (Management Studio). A query faz um LEFT JOIN da Fato com a View Histórica, juntando os números reais da CTI com os Deltas de Planejamento na mesma linha antes deles subirem para o Power BI Cloud.

### 📚 Anexos Documentais para Auditação do Time (Dicionários de Dados)

Para a listagem granular dos tipos de dados na Modelagem Kimble, referenciar os diretórios:

* `/docs/DICIONARIO_DADOS_FRONTEND.md`: Focado nas colunas cruzadas (A Tela de Negócios).
* `/docs/DICIONARIO_FATO_SMARTCORR.md`: Focado na estrutura de destino escrita pelo Script Preditor.
* `/docs/ANALISE_IMPACTO_VARIAVEIS.md`: Focado no relatório contendo a percentualidade e utilidade matemática que o ML achou no Banco Transacional provando a influência vitalística que as "Faltas e Férias" têm no SLA.

(O gerente de Dados está convidado a homologar a integridade lógica e os tratamentos contra *Zero Division* espalhados entre os scripts `.py` de transformação e a `QUERY_FRONTEND_BI.sql` de exibição!)
