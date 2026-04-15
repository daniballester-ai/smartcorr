# Documentação do Código Fonte (`src/`)

**Projeto SmartCorr - MLOps e Engenharia de Machine Learning**

Este documento detalha a organização da pasta `src`. A arquitetura segue padrões de MLOps, separando responsabilidades em módulos independentes.

---

## Estrutura de Diretórios 📁

Resumo das responsabilidades de cada módulo dentro de `src/`:

### 1. Conexões e Configurações Globais

* **`database.py`**: Gerencia a conexão com o SQL Server (PyODBC).
* **`credencial.py`**: Armazena as credenciais de acesso ao banco de dados.

### 2. Pipeline de Dados (Data Pipeline)

* **`data_loading/`**: Responsável por extrair os dados brutos do ODSCorp.
* **`data_preprocessing/`**: Executa a limpeza básica e tratamento de nulos.
* **`feature_engineering/`**: Criação de métricas de negócio, deltas e variáveis temporais (Lags).

### 3. Pipeline do Modelo (Model Pipeline)

* **`model_training/`**: Responsável por treinar o modelo.
* **`model_evaluation/`**: Responsável pela auditoria e cálculo de métricas (RMSE, MAE, R²).
* **`inference/`**: Responsável pela predição em tempo real e atualização no Banco de Dados.

> **⚠️ Onde está o arquivo `.pkl`?**
> Para seguir boas práticas de versionamento (Git), o arquivo binário do modelo treinado (`model.pkl`) é salvo no diretório raiz `models/`, e não dentro de `src/`.

### 4. Suporte e Outros

* **`logs/`**: Registros de execução detalhada do sistema.
* **`visualization/`**: Geração de gráficos analíticos de interpretabilidade (ex: SHAP Values).
