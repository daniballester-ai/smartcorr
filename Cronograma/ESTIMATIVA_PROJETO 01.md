# Estimativa e Planejamento: Projeto SmartCorr
**Data Base:** 07/02/2026 | **Deadline:** 20/03/2026 (~30 dias úteis)

Este documento detalha o cronograma, gap analysis e estimativa de esforço para a entrega final do projeto SmartCorr, alinhado à arquitetura MLOps e aos requisitos de negócio.

---

## 1. Status Atual vs. Necessidade (Gap Analysis)

| Componente | Status Atual | O Que Falta (To-Do) | Prioridade |
| :--- | :--- | :--- | :--- |
| **Pipeline de Dados** | ✅ Funcional (Carga -> Tratamento -> Features) | 🔴 Integrar novas variáveis (SQL); Implementar **Normalização** (Scaling); Validação de Schema (Pydantic/Great Expectations). | Alta |
| **Data Science** | ⚠️ Modelo Preliminar (Random Forest) | 🔴 **EDA (Análise Exploratória)** profunda; Teste de Hipóteses; Tuning de Hiperparâmetros; Seleção de Features (RFE). | Alta |
| **MLOps (Infra)** | ⚠️ Básico (Logs + Estrutura Modular) | 🔴 **DVC** (Versionamento de Dados); Experiment Tracking (MLflow ou similar); CI/CD básico. | Média |
| **Integração** | ❌ Inexistente | 🔴 **API** de Inferência (FastAPI/Flask); **Write-back** (Salvar predições no SQL Server). | Alta |
| **Front-end** | ❌ Inexistente | 🔴 Dashboard de Visualização (PowerBI ou WebApp Next.js); Sistema de Alertas. | Média |
| **Documentação** | ✅ Técnica e Estratégica (Inicial) | 🟡 Documentação da API; Manual do Usuário; Dicionário de Dados atualizado. | Baixa |

---

## 2. Cronograma Macro (Roadmap)

Considerando o prazo de 20/03, temos **6 semanas**.

### Semana 1: Maturidade de Dados & EDA (07/02 - 14/02)
*O foco é garantir que o modelo está aprendendo a coisa certa.*
- [ ] **Levantamento de Dados:** Mapear e ingerir as "novas variáveis" mencionadas (ex: dados de telefonia, escalas de pausa).
- [ ] **EDA (Análise Exploratória):** Produzir notebook com correlações, distribuição de variáveis e outliers. Identificar o que realmente impacta o NS.
- [ ] **Normalização:** Adicionar etapa de `StandardScaler` ou `MinMaxScaler` no pipeline (`src/preprocessing`).
- **Entregável:** Relatório de Insights e Dataset "Ouro" versionado.

### Semana 2: Refinamento do Modelo & MLOps Core (17/02 - 21/02)
*Profissionalizar o experimento.*
- [ ] **DVC Setup:** Configurar versionamento de dados (`dvc init`, remote storage).
- [ ] **Feature Selection:** Remover ruído e focar nas variáveis de impacto.
- [ ] **Modelo Final:** Retreinar com dados novos e tunar performance.
- **Entregável:** Modelo otimizado e Pipeline rastreável.

### Semana 3: Engenharia de Integração (24/02 - 28/02)
*Conectar o cérebro (Modelo) ao corpo (Operação).*
- [ ] **API de Inferência:** Criar serviço em FastAPI para servir o modelo em tempo real.
- [ ] **SQL Write-back:** Criar script/job para inserir as previsões (`predictions.csv`) de volta em uma tabela do SQL Server (`tb_SmartCorr_Predictions`) para consumo do BI.
- **Entregável:** API rodando e Tabela SQL populada automaticamente.

### Semana 4: Front-end & Visualização (03/03 - 07/03)
*Dar cara ao produto.*
- **Opção A (PowerBI):** Conectar na tabela SQL populada. Criar visualizações de Previsto vs Real, Velocímetro de NS. (Estimativa: 3 dias).
- **Opção B (Next.js):** Desenvolver Web App customizado. (Estimativa: 8-10 dias).
    * *Recomendação:* Dado o prazo (20/03), **PowerBI** é mais seguro. Next.js só se houver requisito de interatividade complexa (simulação em tempo real na tela).
- [ ] **Alertas:** Configurar trigger de e-mail/Teams se `Predição < Meta`.

### Semana 5: Testes Técnicos & Validação DBA (10/03 - 14/03)
- [ ] Teste de Stress (volume alto de requisições na API).
- [ ] **Deploy em Nuvem (PBIP):** Validação técnica pelo time de DBA.
- [ ] Ajustes internos de modelo e interface.

### Semana 6: Homologação de Negócio & Go-Live (17/03 - 20/03)
- [ ] **Reunião de Homologação:** Validação com usuários chave (UAT).
- [ ] Deploy Final em Produção.
- [ ] Workshop de entrega.
- [ ] **Go-Live.**

---

## 3. Detalhamento Técnico das Tarefas Imediatas

### A. Pipeline de Limpeza (Necessita Revisão)
Atualmente temos `clean_data.py`, mas ele apenas padroniza datas.
**Necessidade:**
1.  **Tratamento de Outliers:** Remover ou clipar valores absurdos (ex: TMA > 1 hora).
2.  **Normalização:** Modelos como Regressão Linear ou Redes Neurais exigem dados na mesma escala (0-1 ou Z-score). Árvores (Random Forest) não exigem, mas ajuda na interpretabilidade.
3.  **Input Imputation:** Como tratar Nulos nas novas variáveis? (Média? Zero? KNN?).

### B. Integração (API vs Batch)
Precisamos decidir a arquitetura de consumo:
1.  **Batch (Atual):** O script roda a cada 30min, gera CSV, salva no banco. O PowerBI lê do banco. (Mais Simples e Robusto).
2.  **API (Real-time):** O front-end chama a API enviando o cenário atual e recebe a previsão. (Necessário para a "Simulação/Goal Seeking" interativa).

### C. Alertas
Implementar módulo `src/alerting/` que verifica:
`Se (NS_Predito < 85%) E (Hora < 18:00) -> Enviar Webhook Teams.`

---

## 4. Conclusão da Estimativa

O projeto é **viável** para 20 de Março, mas não há margem para escopo não planejado.

*   **Risco Crítico:** "Novas variáveis". Dependendo da complexidade de extração (bancos legados, planilhas soltas), isso pode atrasar a Semana 1.
*   **Decisão Chave:** Optar por **PowerBI** para visualização inicial garante a entrega. Deixar Next.js para "Fase 2" pós-março.

**Próximo Passo Imediato (Hoje):** Iniciar a **Semana 1** (EDA + Mapeamento das Novas Variáveis).
