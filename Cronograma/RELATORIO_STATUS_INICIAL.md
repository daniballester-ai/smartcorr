# Relatório de Status - SmartCorr (Fase Inicial)

**Data:** 07/02/2026  
**Assunto:** Validação de Conectividade, Estrutura MLOps e Primeiro Ciclo de Predição

## 1. Visão Geral

Este documento reporta o sucesso na configuração inicial da ferramenta **SmartCorr**. Concluímos as etapas de infraestrutura, conexão com banco de dados corporativo (`OdsCorp`) e execução do primeiro pipeline de Inteligência Artificial para previsão de Nível de Serviço.

O objetivo desta fase foi validar a capacidade de processamento e a arquitetura do projeto, utilizando um modelo generalista para múltiplos programas (`program_ccmsid`).

## 2. Conquistas Técnicas

* **Conectividade Total**: Estabelecida conexão segura (Autenticação Windows) com o servidor `SPWS-VM-DB81`.
* **Estrutura MLOps Profissional**: O projeto foi reestruturado para uma arquitetura modular (`src/data`, `src/models`, `params.yaml`), garantindo escalabilidade, organização e fácil manutenção.
* **Pipeline Automatizado**: Implementado fluxo contínuo de ETL (Extração), Pré-processamento, Treinamento e Predição.

## 3. Resultados do Teste (MVP)

O sistema operou com sucesso total no primeiro teste de carga massiva. Os principais destaques foram:

1. **Carga de Dados Robusta**: O sistema processou **6.8 milhões de registros** históricos em aproximadamente 6 minutos, demonstrando estabilidade na conexão.
2. **Performance Otimizada**: Utilizou-se técnica de amostragem inteligente (20% dos dados) para treinar o modelo *Random Forest* em segundos, garantindo velocidade sem comprometer a capacidade de diagnóstico.
3. **Diagnóstico de Causas**: O modelo identificou matematicamente que o **Volume Real** é, de longe, o fator de maior impacto no Nível de Serviço atual do call center (**~92% de importância**), seguido pelos Deltas (Variação Real vs Meta).
4. **Predição em Escala**: Foram geradas automaticamente **~2.8 milhões de previsões** para os próximos dias (horizonte curto prazo).

### Evidência de Execução

![Resultado do Primeiro Teste de Treino](images/primeiro_teste_treino.png)

### Exemplo Real Gerado pelo Modelo:

Para o programa `30389` (Canal 7), projetando a próxima segunda-feira (09/02) às 09:00:

* **Cenário**: Volume previsto de ~5.8 chamadas.
* **Previsão**: O modelo estima um **Nível de Serviço de ~59.1%** (`0.591619`).

## 4. Variáveis do Modelo (Mapeamento de Causas - Coluna B)

O modelo foi desenhado para correlacionar as **Causas Raiz** (baseado na Coluna B do plano de correlação) com o Nível de Serviço:

1. **Volumetria**:

   * **Já Implementado**: *Assertividade de Forecast* (via `Delta_Volume` e `Volume_Previsto`).
   * **Planejado**: *Ura*, *Indisponibilidade sistêmica*, *Rechamada*, *Tabulação (perfil)*, *Transferências*, *Eventos externos (propaganda/clima)*.
2. **TMA**:

   * **Já Implementado**: *Assertividade de Forecast* (via `Delta_TMA` e `TMA_Meta`).
   * **Planejado**: *Lentidão Sistêmica*, *Tabulação*, *Novatos (Curva de Aprendizado)*, *Processos*.
3. **Pessoas**:

   * **Planejado (Prioridade PagBank)**: *Turnover*, *Férias*, *ABS (Absenteísmo)*, *Pausas (Aderência)*, *Gap Log (HC Real vs Planejado)*.

## 5. Próximos Passos e Roadmap

O foco imediato será direcionado para o **Programa PagBank** (Cliente Crítico):

1. **Especialização no Programa PagBank**:
   * Filtrar e treinar o modelo especificamente para os `program_ccmsid` do PagBank para validar aderência em cenário real crítico.
2. **Expansão de Dados (Pilar Pessoas)**:
   * Ingerir as variáveis críticas de Pessoas (% Absenteísmo, Aderência).
   * **Feature Engineering**: Criar novas variáveis complexas (Ex: *Eficiência por Agente*, *Impacto do Absenteísmo no NS*).
3. **Benchmark de Modelos (Performance)**:
   * Testar e comparar performance de **no mínimo 3 algoritmos**:
     * *Random Forest* (Baseline atual).
     * *XGBoost / LightGBM* (para dados tabulares).
     * *Regressão Linear / Neural Net Simples* (Para baseline de tendência).
4. **Estratégia de Modelagem**:
   * Avaliar a criação de modelos específicos ("Clusters") para separar operações de Vendas, Atendimento e Suporte, em vez de um modelo único generalista.
5. **Output (Futuro)**:
   * Implementação da escrita dos resultados em tabela SQL Server (`DataMart`) para consumo automatizado no Dashboard Power BI.

---

**Conclusão**: O teste inicial foi um sucesso e a fundação técnica para o SmartCorr está sólida para evoluir para o piloto PagBank.
