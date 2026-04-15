# Plano de Refatoração MLOps — SmartCorr

Este documento detalha o planejamento para alinhar o projeto **SmartCorr** à arquitetura de referência `mlops_project`, seguindo as melhores práticas de MLOps (Data/Model Versioning, Tracking e Containerização).

---

## 🎯 Objetivos
- Integrar **DVC** para versionamento de dados e artefatos.
- Integrar **MLflow** para rastreamento de experimentos e registro de modelos.
- Modernizar o gerenciamento de dependências (`pyproject.toml`).
- Garantir reprodutibilidade via **Docker**.
- Manter a lógica de inferência com escrita direta no **SQL Server**.

---

## 🏗️ Fase 1: Fundação & Infraestrutura (Tools Setup)
**Responsável:** @backend-specialist

- [ ] **DVC Init**: Inicializar DVC no projeto.
  - Comando: `dvc init --no-scm` (ou com git se preferir).
- [ ] **MLflow Setup**: Configurar servidor local ou banco SQLite para backend do MLflow.
- [ ] **Environment**: Criar `.env.example` para credenciais do SQL Server e variáveis do MLflow.
- [x] **Packaging**: Migrar `requirements.txt` para `pyproject.toml`.

---

## 🛠️ Fase 2: Modernização do Código (Tracking & Refs)
**Responsável:** @backend-specialist / @project-planner

- [ ] **Instrumentação MLflow**: Adicionar `mlflow.start_run()`, `log_metrics`, `log_params` e `log_model` no `main.py`.
- [ ] **DVC Pipelines**: Criar `dvc.yaml` para definir as etapas do pipeline (pre-process, train, eval).
- [ ] **Refatoração SQL**: Garantir que as credenciais do SQL Server em `credencial.py` e `database.py` usem variáveis de ambiente (`os.getenv`).

---

## 🐳 Fase 3: DevOps & Containerização
**Responsável:** @backend-specialist

- [ ] **Dockerfile**: Criar imagem de produção baseada em Python 3.9 (conforme `requirements_39.txt`).
- [ ] **Docker Compose** (Opcional): Para orquestrar App + SQL Server local se necessário.
- [ ] **.dockerignore**: Filtrar datasets pesados e pastas venv.

---

## ✅ Lista de Verificação (Verification)
1. [ ] Rodar `dvc repro` e verificar se os artefatos são gerados na pasta `artifacts/` (ou `models/`).
2. [ ] Abrir `mlflow ui` e confirmar se os parâmetros do `params.yaml` e métricas do `metrics/` foram logados corretamente.
3. [ ] Build da imagem Docker: `docker build -t smartcorr:latest .`.
4. [ ] Teste de inferência: Verificar se os resultados continuam sendo salvos no banco SQL Server corretamente após o refactoring.

---

## 📅 Cronograma Sugerido
- **Dia 1**: Fase 1 (Setup & pyproject.toml)
- **Dia 2**: Fase 2 (Instrumentação MLflow & DVC)
- **Dia 3**: Fase 3 & Final Checks
