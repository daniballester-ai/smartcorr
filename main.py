import logging
import sys
import os
from datetime import datetime

# Garante que o diretório raiz está no path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Configuração de Logs
logging_dir = 'logs'
os.makedirs(logging_dir, exist_ok=True)
log_file = os.path.join(logging_dir, f'smartcorr_pipeline_{datetime.now().strftime("%Y%m%d")}.log')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("SmartCorr_Pipeline")

def main():
    logger.info("=== INICIANDO PIPELINE SMARTCORR (Architecture: MLOps Project) ===")
    
    try:
        # 1. Pipeline de Dados
        logger.info("--- Estágio 1: Data Loading ---")
        from src.data_loading import load_data
        load_data.main()
        
        # Limpeza
        logger.info("--- Estágio 2: Data Preprocessing ---")
        from src.data_preprocessing import clean_data
        clean_data.main()
        
        # Feature Engineering
        logger.info("--- Estágio 3: Feature Engineering ---")
        from src.feature_engineering import build_features
        build_features.main()
        
        # 2. Pipeline de Modelo
        logger.info("--- Estágio 4: Model Training ---")
        from src.model_training import train_model
        train_model.main()
        
        # Avaliação do Modelo
        logger.info("--- Estágio 5: Model Evaluation ---")
        from src.model_evaluation import evaluate_model
        evaluate_model.main()
        
        # 3. Pipeline de Inferência
        logger.info("--- Estágio 6: Inference ---")
        from src.inference import predict
        predict.main()
        
        logger.info("=== PIPELINE EXECUTADO COM SUCESSO ===")

    except Exception as e:
        logger.error(f"FATAL ERROR no Pipeline: {e}", exc_info=True)
        # Segura a janela aberta em caso de erro para leitura
        input("Pressione Enter para fechar...") 
        sys.exit(1)

if __name__ == "__main__":
    main()
