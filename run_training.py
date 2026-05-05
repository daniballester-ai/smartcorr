import os
import sys
from argparse import ArgumentParser

# Ensure the root directory is in the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Enable venv path resolution dynamically for Datacore
venv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".venv", "Lib", "site-packages")
if venv_path not in sys.path:
    sys.path.insert(0, venv_path)

import yaml
import logging

# Configuração de Logs
logging_dir = 'logs'
os.makedirs(logging_dir, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("SmartCorr_Training_Datacore")

def update_params_mode(mode="training"):
    """Update params.yaml with the required mode for the pipeline."""
    params_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "params.yaml")
    if os.path.exists(params_path):
        with open(params_path, "r", encoding="utf-8") as f:
            params = yaml.safe_load(f)
            
        if params.get("data", {}).get("mode") != mode:
            params["data"]["mode"] = mode
            with open(params_path, "w", encoding="utf-8") as f:
                yaml.dump(params, f, sort_keys=False, allow_unicode=True)
            logger.info(f"params.yaml updated to mode: {mode}")

def main():
    logger.info("=== INICIANDO PIPELINE SMARTCORR (TREINAMENTO VIA DATACORE) ===")
    
    # Force params.yaml to training mode
    update_params_mode("training")
    
    try:
        # Import stages
        from src.data_loading import load_data
        from src.data_preprocessing import clean_data
        from src.feature_engineering import build_features
        from src.model_training import train_model
        
        logger.info("--- Estágio 1: Data Loading ---")
        load_data.main()
        
        logger.info("--- Estágio 2: Data Preprocessing ---")
        clean_data.main()
        
        logger.info("--- Estágio 3: Feature Engineering ---")
        build_features.main()
        
        logger.info("--- Estágio 4: Model Training ---")
        train_model.main()
        
        logger.info("=== TREINAMENTO EXECUTADO COM SUCESSO ===")
        return 1  # Retornar 1 como indicativo de sucesso para o Datacore

    except Exception as e:
        logger.error(f"FATAL ERROR no Pipeline de Treinamento: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    argParser = ArgumentParser('SmartCorr - Treinamento Preditivo')
    argParser.add_argument('--InitialDateCtrl', help='Data Inicial de Proceso.', required=False)
    argParser.add_argument('--FinalDateCtrl', help='Data Final de Proceso.', required=False)
    argParser.add_argument('--ProcessTable', help='Tabela do Processo.', required=False)
    argParser.add_argument('--ProcessKey', help='Número do Processo no DataCore.', required=False)
    argParser.add_argument('--connectionString', help='Connection string for the database.', required=False, type=str)
    
    args, unknown = argParser.parse_known_args()
    
    # Injetar a connection string do DataCore nas variáveis de ambiente, se fornecida
    if args.connectionString:
        os.environ['DB_CONNECTION_STRING'] = str(args.connectionString)
    else:
        logger.info("Execução local: Nenhuma connectionString fornecida via CLI. Usando fallback do database.py.")
    
    try:
        rows = main()
        sys.stdout.write(str(rows))
        sys.stdout.flush()
        sys.exit(0x00)
    except Exception as error:
        exc_type, value, traceback = sys.exc_info()
        errmessage = f"Failed: [{exc_type.__name__}] {str(error)[:255]}"
        sys.stdout.write(errmessage)
        sys.stdout.flush()
        sys.exit(0x01)
