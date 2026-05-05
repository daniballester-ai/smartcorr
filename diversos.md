Link do intraday: https://app.powerbi.com/groups/1ded63f2-6097-4565-ab9b-019057b72f5f/reports/b3981569-e0e0-4fa8-aa58-54079f4307c4/12f6234ca063a4640c98?ctid=638fcbaf-ba4c-43e1-adae-5475c970fe10&experience=power-bi

python -m src.data_loading.load_data
python -m src.preprocessing.clean_data
python -m src.feature_engineering.build_features
python -m src.model_training.train_model
python -m src.inference.predict

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
├── data/                     # Balcão da Qualidade MLOps (Raw, Interim, Processed)
├── models/                   # Artefatos do modelo (.pkl)
├── metrics/                  # Notas estatísticas (JSON) arquivadas por treinamento
├── logs/                     # Rastreabilidade temporal de erros e sucessos do pipeline
├── docs/                     # Repositório Oficial de Documentações (Dicionários, Fluxos)
├── params.yaml               # Cnfigurações (variáveis, limiares, pontes)
└── main.py                   # Orquestrador Mestre: Invoca as subpastas da `src/` em looping
```


pyproject.toml está pronto para uso. Para instalar via este arquivo em um novo ambiente, basta usar `pip install .`.
