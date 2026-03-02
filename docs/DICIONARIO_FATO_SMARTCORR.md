# Dicionário de Dados - Tabela Fato Preditiva (SmartCorr)

**Fonte de Dados (SQL Server):** `[OdsCorp].[SmartCorr].[FactSmartCorr_Previsao]`
**Criador:** Pipeline de Inferência Python (`run_inference.py` / `predict.py`)
**Última Atualização:** Março de 2026
**Objetivo:** Este documento descreve as colunas escritas nativamente pelo algoritmo de **Inteligência Artificial (XGBoost + SHAP)** na tabela final do Data Warehouse. Diferente da Query do Frontend (que cruza com o Real), esta tabela é estritamente a "fotografia da predição" no instante em que o modelo foi rodado.

---

## 1. Chaves de Particionamento (Granularidade da Fato)
Garante a união cruzada (JOIN) exata e única com qualquer outra dimensão da empresa (Erlang, CTI, Base de RH).

| Coluna | Tipo | Descrição Obrigatória |
| :--- | :---: | :--- |
| `DataRef` | `DATE` | Data referência para a qual a previsão foi feita. |
| `Intervalo` | `TIME` | Bloco exato de 30 minutos previstos (ex: `10:30:00`). |
| `CodPrograma` | `INT` | ID numérico identificador da Célula Comercial/Skill (ex: Pagbank). |
| `Canal` | `INT` | Identificador do canal (Fixo em `7` = Voz). |

---

## 2. Indicadores Numéricos Preditivos (Saída Algorítmica Base)
O que foi entregue para a IA vs O que a IA respondeu.

| Coluna | Tipo | Significado |
| :--- | :---: | :--- |
| `NS_Previsto_SmartCorr` | `FLOAT` | **O ALVO:** A predição final de SLA / Nível de Serviço da máquina para o respectivo intervalo. Limitado organicamente de 0.0 (0%) a 1.0 (100%). |
| `Vol_Previsto` | `INT` | Fotografia de contexto: Qual era o volume do Forecast Erlang no momento da inferência. |
| `HC_Previsto` | `INT` | Fotografia de contexto: Quantas pessoas estavam na meta Erlang no momento da inferência. |
| `TMA_Previsto_Avg` | `FLOAT` | O Tempo Médio de Atendimento planejado pelo setor do WFM. |
| `NS_Lag_1` | `FLOAT` | Memória gravada que ditou 76% da IA: Qual era o NS Real do intervalo cronologicamente exato anterior à predição. |

---

## 3. Matriz XAI: Impactos por Pilar (SHAP Values Agrupados)
Representa de forma consolidada e agregada como a Floresta de Decisões matematicamente calculou o seu Nível de Serviço final. Os valores representam o "Desconto (Negativo)" ou "Crédito (Positivo)" no Nível % de Serviço gerado da base zero.

| Coluna | Tipo | Semântica da Categoria |
| :--- | :---: | :--- |
| `Impacto_Pilar_Volumetria` | `FLOAT` | Peso agregado causado pelas métricas de chamadas, abandonos e desvios de Forecast (Erlang Error). |
| `Impacto_Pilar_Pessoas` | `FLOAT` | Peso agregado de furos de Headcount, quantidades de pausas improdutivas, férias, absenteísmo e ocupação real dos agentes. |
| `Impacto_Pilar_TMA` | `FLOAT` | Peso focado puramente na ineficiência do Tempo Médio das conversas vs a Meta e do Tempo de Espera do Cliente (TME). |
| `Impacto_Pilar_Contexto` | `FLOAT` | Peso da inércia (Engarrafamento natural de meia hora antes - Lags) e variáveis inegociáveis de sazonalidade (Hora / Dia da semana). |

---

## 4. Matriz de Causa-Raiz (TOP 3 Ofensores)
Para justificar o seu card de alerta **Vermelho**, estes são de forma dissecada, em texto claro, os 3 maiores "Inimigos" que forçaram o modelo matemático a não bater a meta de NS do intervalo. O Limiar de Sensibilidade ignora ofensores cujo poder matemático seja irrelevante.

| Coluna | Tipo | O que é registrado pelo Python |
| :--- | :---: | :--- |
| `Ofensor_1_Nome` | `VARCHAR` | O rótulo "vencedor" do pior detrator. (Ex: *"Desvio_HC_Pct_Lag_1"*). |
| `Ofensor_1_Pilar` | `VARCHAR` | Classificação do pilar acima (Ex: *"Pessoas"*). Útil para o PowerBI pintar a linha ou barra gráfica. |
| `Ofensor_1_Impacto` | `FLOAT` | Poder do dano. Sobe no banco com sinal já negativo. Ex: **-0.21** (Tirou 21 pontos percentuais absolutos do NS). |
| `Ofensor_2_...`<br>`Ofensor_3_...` | Vários | As demais 6 colunas que replicam a mesmíssima lógica para o 2º e 3º ofensores sequenciais, garantindo riqueza analítica descritiva na query frontal. |

---

## 5. Matriz de Mérito (TOP 3 Impulsionadores)
Quando o NS não desaba em frente ao colapso, o Diretor e a Operação precisam saber: *"Quem nos salvou do buraco e qual braço da equipe merece os elogios?"*

| Coluna | Tipo | O que é registrado pelo Python |
| :--- | :---: | :--- |
| `Impulsionador_1_Nome` | `VARCHAR` | O herói da meia hora (O fator que mais subiu a conta matematicamente para próximo de 100%). Ex: *"TMA_Real_Agora"*. |
| `Impulsionador_1_Pilar` | `VARCHAR` | Classificação em macro categoria (Ex: *"TMA"*). |
| `Impulsionador_1_Impacto` | `FLOAT` | Poder absoluto de bonificação gerado contra o caos. Escrito com sinal sempre positivo (+). Ex: **+0.15** (Segurou sozinho mais 15 pontos do NS evadindo multa do contrato). |
| `Impulsionador_2_...`<br>`Impulsionador_3_...` | Vários | As demais 6 colunas espelhos para ranquear os próximos fatores que seguraram o negócio acima d'água em 2º ou 3º lugar. |
