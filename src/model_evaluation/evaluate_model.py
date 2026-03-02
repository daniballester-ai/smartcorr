import pandas as pd
import logging
import os
import yaml
import json
import joblib
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split

logger = logging.getLogger(__name__)

def load_config():
    with open("params.yaml", "r") as f:
        return yaml.safe_load(f)

def avaliar_modelo(modelo, X_teste, y_teste):
    """
    Avalia o modelo nos dados de teste e retorna métricas.
    """
    y_predito = modelo.predict(X_teste)
    
    metricas = {
        "r2_score": r2_score(y_teste, y_predito),
        "mse": mean_squared_error(y_teste, y_predito),
        "mae": mean_absolute_error(y_teste, y_predito),
        "n_amostras_teste": len(y_teste)
    }
    
    return metricas

def main():
    config = load_config()
    caminho_modelo = config['model']['path']
    caminho_treino = config['data']['processed_train_path']
    caminho_metricas = config['model']['metrics_path'].replace('train_metrics', 'evaluation')
    
    features = config['data']['features']
    target = config['data']['target']
    
    os.makedirs(os.path.dirname(caminho_metricas), exist_ok=True)
    
    # Carrega modelo
    logger.info(f"Carregando modelo de: {caminho_modelo}")
    if not os.path.exists(caminho_modelo):
        logger.error("Modelo não encontrado. Execute o treinamento primeiro.")
        return
        
    modelo = joblib.load(caminho_modelo)
    
    # Carrega dados de treino para split de teste
    # Idealmente teríamos um test_processed.csv separado, mas vamos simular aqui
    logger.info(f"Carregando dados de: {caminho_treino}")
    df = pd.read_csv(caminho_treino)
    
    # Validação de colunas
    colunas_faltantes = [col for col in features + [target] if col not in df.columns]
    if colunas_faltantes:
        raise ValueError(f"Colunas ausentes: {colunas_faltantes}")
    
    X = df[features]
    y = df[target]
    
    # Split holdout para avaliação (20% dos dados)
    _, X_teste, _, y_teste = train_test_split(X, y, test_size=0.2, random_state=42)
    
    # Avaliação
    logger.info("Avaliando modelo...")
    metricas = avaliar_modelo(modelo, X_teste, y_teste)
    
    logger.info(f"Métricas de Avaliação: R²={metricas['r2_score']:.4f}, MSE={metricas['mse']:.6f}, MAE={metricas['mae']:.6f}")
    
    # Salva métricas
    with open(caminho_metricas, 'w') as f:
        json.dump(metricas, f, indent=4)
    logger.info(f"Métricas salvas em: {caminho_metricas}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
