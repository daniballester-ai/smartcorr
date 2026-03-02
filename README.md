# SmartCorr Engine (MLOps)

> **A fusão entre Precisão Científica, Robustez Operacional e Segurança Psicológica de Decisão.**

O **SmartCorr** é um motor de inteligência artificial projetado para transformar a gestão de SLA intraday. Ele substitui a reação baseada em "palpites" por uma previsão baseada em probabilidade calculada, permitindo ações proativas antes que a meta seja perdida.

---

## 🏗️ Nova Arquitetura Modular

O projeto segue rigorosos padrões de **MLOps** para garantir escalabilidade, manutenibilidade e rastreabilidade. A estrutura segue um pipeline modular conforme estrutura abaixo.

### Estrutura de Diretórios

```bash
SmartCorr/
├── src/
│   ├── data_loading/         # Extração bruta do SQL Server para a pasta data/raw
│   ├── preprocessing/        # Limpeza, tratamentos nulos
│   ├── feature_engineering/  # Criação de Lags, Deltas e Taxas GO!
│   ├── model_training/       # Algoritmos XGBoost com hiperparâmetros
│   ├── model_evaluation/     # Cálculo do Boletim da I.A. (R², MSE, MAE)
│   ├── inference/            # Motor preditivo que devolve pro SQL de 30 em 30 min
│   ├── visualization/        # Gráficos SHAP (Abelha, Cascata)
│   ├── database.py           # Gerenciador único de rotas e conexões de Banco de Dados
│   ├── credencial.py         # Arquivo isolado de segurança/senhas lido pelo database.py

```

---

## 🎯 Objetivo e Justificativa

### O Problema (A Dor)

A gestão intraday tradicional sofre com a incerteza. Gestores sabem que o volume oscila, mas não conseguem quantificar com precisão como isso impactará o Nível de Serviço (NS) no final do dia. Isso gera ansiedade e decisões reativas.

### A Solução (O Valor)

O SmartCorr utiliza um modelo de **Regressão Supervisionada** para prever o valor exato do NS futuro (ex: 82.5%).

- **Diagnóstico:** Explica *por que* o resultado está desviando (ex: "91% do impacto vem do Volume, não do TMA").
- **Predição:** Projeta o fechamento do dia com horas de antecedência.
- **Segurança:** Oferece controle cognitivo sobre a operação, permitindo alocação eficiente de recursos (headcount).

---

## 🚀 Boas Práticas de MLOps Implementadas

1. **Modularidade & Separação de Responsabilidades:** Cada etapa do pipeline (Carga, Treino, Inferência) é um módulo isolado, facilitando testes e manutenção.
2. **Reprodutibilidade:**
   - Uso estrito de **Virtual Environment** (`venv`) para isolamento de dependências.
   - Configurações externas em `params.yaml` (sem hardcoding).
   - Fixação de seeds aleatórias (`random_state=42`) para resultados consistentes.
3. **Observabilidade:**
   - **Logging Robusto:** Logs detalhados em arquivo e console para cada etapa.
   - **Métricas Persistidas:** Métricas de treino e teste salvas em JSON para monitoramento de drift.
4. **Resiliência de Dados:**
   - Tratamento explícito de timouts de banco de dados (ex: conexões longas de 10min+).
   - Pipeline capaz de lidar com grandes volumes (teste de carga com 6.8M linhas aprovado).
   - Fallback para drivers SQL legados para compatibilidade de infraestrutura.
5. **Explicabilidade (XAI):** O modelo não é uma caixa preta; ele fornece a importância de cada variável (Feature Importance) para suportar a decisão de negócio.

---

## ⚙️ Como Executar

### Pré-requisitos

- Python 3.9.13+
- Acesso ao SQL Server (Rede Corporativa/VPN)
- Credenciais configuradas em `src/credencial.py` ou Variáveis de Ambiente.

### Execução do Pipeline Completo

```bash
# 1. Ativar Virtual Environment (Windows PowerShell)
.\venv\Scripts\Activate.ps1

# 2. Executar Orquestrador
python main.py
```

### Saídas Geradas

- **Previsões:** `data/processed/predictions.csv`
- **Relatório de Performance:** `metrics/evaluation.json`
- **Logs:** `logs/smartcorr_pipeline_{YYYYMMDD}.log`

---

## 📚 Documentação Adicional

Toda a base de conhecimento arquitetural, MLOps e dicionários de dados do projeto foram unificadas. Acesse os materiais no repósitorio oficial:

- [📂 Pasta de Documentações Oficiais (docs/)](docs/)
