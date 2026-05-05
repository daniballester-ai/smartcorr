# Estimativa e Planejamento: Projeto SmartCorr

**Data Base:** 21/02/2026 | **Deadline:** 20/03/2026 (~30 dias úteis)

Este documento detalha o cronograma, gap analysis e estimativa de esforço para a entrega final do projeto SmartCorr, alinhado à arquitetura MLOps e aos requisitos de negócio.

---

## 1. Status Atual vs. Necessidade (Gap Analysis)

| Componente                  | Status Atual                                   | O Que Falta (To-Do)                                                                                           | Prioridade |
| :-------------------------- | :--------------------------------------------- | :------------------------------------------------------------------------------------------------------------ | :--------- |
| **Pipeline de Dados** | ✅ Funcional (Carga -> Tratamento -> Features) | 🔴 Integrar novas variáveis (SQL); Validação de Schema (Pydantic/Great Expectations).                      | Alta       |
| **Data Science**      | ✅ Modelo de Produção (XGBoost Regressor)    | 🔴 Teste de Hipóteses contínuo; Tuning de Hiperparâmetros avançado.                                       | Média     |
| **MLOps (Infra)**     | ⚠️ Básico (Logs + Estrutura Modular)        | 🔴**DVC** (Versionamento de Dados); Experiment Tracking (MLflow ou similar); CI/CD básico.             | Média     |
| **Integração**      | ✅ Funcional                                   | 🔴**API** de Inferência (FastAPI/Flask) - Opcional.                                                    | Baixa      |
| **Front-end**         | ⚠️ Parcial                                   | 🔴 Dashboard de Visualização (PowerBI); Validar dados reais e ajustar colunas na query. Sistema de Alertas. | Alta       |
| **Documentação**    | ✅ Técnica e Estratégica (Inicial/SHAP)      | 🟡 Documentação da API; Manual do Usuário; Dicionário de Dados atualizado.                                | Baixa      |

---

## 2. Cronograma Macro (Roadmap)

Considerando o prazo de 20/03, temos **6 semanas**.

### Semana 1: Maturidade de Dados & EDA (07/02 - 14/02)

*O foco é garantir que o modelo está aprendendo a coisa certa.*

- [X] **Levantamento de Dados (Fase 1):** Iniciar com dados já disponíveis (Intraday/Metas). **Nota:** Novas variáveis serão agregadas *continuamente* ao longo do projeto, dependendo do mapeamento de outros projetos de BI.
- [X] **EDA (Análise Exploratória):** Produzir insights não através de notebooks estáticos, mas de forma ativa via IA Explicável (SHAP).
- [X] **Limpeza de Dados:** Implementado processo no `src/preprocessing/clean_data.py` (formatação de datas, criação do target matemático puro, e remoção de slots fechados). **Decisão:** Não usaremos tratamentos complexos de Outliers nem Normalização (Z-score/Scaling) devido à escolha arquitetural do XGBoost.

- **Entregável:** Pipeline inicial sólido e Dataset base tratado.

### Semana 2: Refinamento do Modelo & MLOps Core (16/02 - 20/02)

*Profissionalizar o experimento.*

- [X] **Feature Selection & Engineering:** Selecionar colunas determinantes e criar calculadas de negócio. Criação de Deltas de Capacidade e Lags Inerciais para contextuação de crise histórica (-1, -2, -3).
- [X] **Modelo Final:** Adoção, validação e aplicação do **XGBoost Regressor** em produção batch pela inteligência hierárquica imune a escalas.

- **Entregável:** Modelo preditivo superando precisão estática e Pipeline rastreável operante.

### Semana 3: Engenharia de Integração (23/02 - 27/02)

*Conectar o cérebro (Modelo) ao corpo (Operação).*

- [X] **SQL Write-back:** Criada a injeção em lote extremamente performática (fast_executemany) das previsões para a Tabela Fato definitiva criada no SQL Server (`[OdsCorp].[SmartCorr].[FactSmartCorr_Previsao]`).
- [ ] **API de Inferência:** Criar serviço em FastAPI para servir o modelo em tempo real (Opcional, foco atual no Batch).

- **Entregável:** Integração Banco x IA automatizada.

### Semana 4: Front-end & Visualização (03/03 - 07/03)

*Dar cara ao produto.*

- [ ] **Conexão Front-end BI (Status Parcial):** A ponte do SQL para o Power BI já foi desenhada (`QUERY_FRONTEND_BI.sql`), mas faltam ajustes nas colunas base e checagem de dados reais.
- [ ] **Construção Visual PowerBI:** Criar painéis de Previsto vs Real, Cascata de Impacto de Causa Raiz e Visão do Gestor (Estimativa: 3 dias).
- [ ] **Alertas:** Configurar trigger de e-mail/Teams se `Predição < Meta`.

### Semana 5: Testes Técnicos & Validação DBA (10/03 - 14/03)

- [ ] **DVC Setup:** Configurar versionamento de dados massivos (`dvc init`, remote storage).
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

### A. Pipeline de Limpeza (Validado e Otimizado)

O script `clean_data.py` atua puramente como orquestrador. Ele formata as temporalidades e extrai o target matematicamente (Nível de Serviço = Atendidas SLA / Oferecidas).
Nós não utilizaremos Normalização (Scaling) e nem algoritmos de Outlier Clipping (Tratamento de Anomalias). A justificativa arquitetônica baseia-se unicamente na adoção do **XGBoost**. Árvores de decisão baseadas em nós hierárquicos são naturalmente imunes às disparidades de escala, dispensando desperdício computacional em transformações de simetria de features.

### B. Integração (API vs Batch)

O modelo principal atua em inferência **Batch**: O script roda a cada 30min, aplica o "Soft Delete" na janela e salva no banco via `fast_executemany`. O PowerBI lê do banco.

### C. Alertas

Implementar módulo `src/alerting/` que verifica:
`Se (NS_Predito < 85%) E (Hora < 18:00) -> Enviar Webhook Teams.`

---

## 4. Conclusão da Estimativa

O projeto segue à risca para o prazo de 20 de Março. Vencemos de forma antecipada as barreiras de integração massiva e infraestrutura de modelo. A incorporação de "Novas variáveis" seguirá gradativamente até o Go-Live.
