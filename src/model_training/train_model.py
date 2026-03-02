import pandas as pd
import numpy as np
import logging
import os
import yaml
import json
import joblib
from datetime import datetime

from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, r2_score, mean_absolute_error

try:
    from xgboost import XGBRegressor
    HAS_XGB = True
except ImportError:
    HAS_XGB = False

logger = logging.getLogger(__name__)

def carregar_configuracao():
    with open("params.yaml", "r", encoding='utf-8') as f:
        return yaml.safe_load(f)

def treinar_modelo(X_train, y_train, config_modelo):
    """
    Treina o modelo (XGBoost ou Random Forest) baseado no params.yaml.
    """
    tipo_modelo = config_modelo.get('type', 'RandomForestRegressor')
    parametros = config_modelo.get('params', {})
    
    # Tratamento de n_jobs no YAML
    if 'n_jobs' in parametros:
        parametros['n_jobs'] = int(parametros['n_jobs'])

    logger.info(f"Iniciando treinamento com algoritmo: {tipo_modelo}")
    logger.info(f"Parâmetros: {parametros}")

    if tipo_modelo == 'XGBRegressor':
        if not HAS_XGB:
            logger.warning("XGBoost não está instalado! Voltando para RandomForestRegressor como fallback.")
            modelo = RandomForestRegressor(**parametros)
        else:
            modelo = XGBRegressor(**parametros)
    elif tipo_modelo == 'RandomForestRegressor':
        modelo = RandomForestRegressor(**parametros)
    else:
        raise ValueError(f"Tipo de modelo {tipo_modelo} não suportado.")

    modelo.fit(X_train, y_train)
    return modelo, tipo_modelo

def main():
    config = carregar_configuracao()
    caminho_train = config['data']['processed_train_path']
    caminho_modelo = config['model']['path']
    caminho_metricas = config['model']['metrics_path']
    
    features = config['data']['features']
    target = config['data']['target']
    
    os.makedirs(os.path.dirname(caminho_modelo), exist_ok=True)
    os.makedirs(os.path.dirname(caminho_metricas), exist_ok=True)
    
    logger.info(f"Carregando dados de treino: {caminho_train}")
    df = pd.read_csv(caminho_train)
    
    # Validação de colunas
    colunas_ausentes = [col for col in features + [target] if col not in df.columns]
    if colunas_ausentes:
        raise ValueError(f"Colunas ausentes no dataset de treino: {colunas_ausentes}")
        
    # Ordenar por DataHora para garantir Split Temporal
    if 'DataHora' in df.columns:
        df['DataHora'] = pd.to_datetime(df['DataHora'])
        df.sort_values(by='DataHora', inplace=True)

    X = df[features]
    y = df[target]
    
    # Divisão Treino e Validação (Temporal, sem embaralhar)
    # Isso garante que não usaremos o futuro para prever o passado através dos Lags
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.20, shuffle=False)
    
    logger.info(f"Treino: {len(X_train)} linhas. Teste/Validação: {len(X_test)} linhas (Mais recentes).")
    
    # Treinamento
    start_time = datetime.now()
    modelo, tipo_utilizado = treinar_modelo(X_train, y_train, config['model'])
    duracao = (datetime.now() - start_time).total_seconds()
    
    # Avaliação do Modelo (Acurácia Real vs Previsão)
    predicoes_train = modelo.predict(X_train)
    predicoes_test = modelo.predict(X_test)
    
    score_r2_train = r2_score(y_train, predicoes_train)
    score_r2_test = r2_score(y_test, predicoes_test)
    rmse_test = np.sqrt(mean_squared_error(y_test, predicoes_test))
    mae_test = mean_absolute_error(y_test, predicoes_test)

    logger.info(f"R² (Score) no Treino: {score_r2_train:.4f}")
    logger.info(f"R² (Score) na Validação: {score_r2_test:.4f}")
    logger.info(f"Erro Médio Absoluto (MAE): {mae_test:.4f} pontos percentuais de NS.")
    
    # Métricas de Importância (Feature Importance)
    if hasattr(modelo, 'feature_importances_'):
        importancias = dict(zip(features, [float(v) for v in modelo.feature_importances_]))
    else:
        importancias = {}

    metricas = {
        "algoritmo": tipo_utilizado,
        "duracao_treino_segundos": duracao,
        "linhas_treino": len(X_train),
        "linhas_teste": len(X_test),
        "r2_train": score_r2_train,
        "r2_test": score_r2_test,
        "rmse_test": rmse_test,
        "mae_test": mae_test,
        "feature_importances": importancias
    }
    
    # Salvar Modelo
    joblib.dump(modelo, caminho_modelo)
    logger.info(f"Modelo treinado e salvo em: {caminho_modelo}")
    
    # Salvar Métricas
    with open(caminho_metricas, 'w') as f:
        json.dump(metricas, f, indent=4)
    logger.info(f"Métricas salvas em: {caminho_metricas}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
