import logging
import sys
import os
from datetime import datetime

# Garante que o diretório raiz está no path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Configuração de Logs Específico de Inferência
logging_dir = 'logs'
os.makedirs(logging_dir, exist_ok=True)
log_file = os.path.join(logging_dir, f'smartcorr_inference_{datetime.now().strftime("%Y%m%d_%H%M")}.log')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("SmartCorr_Inference")

def main():
    logger.info("=== INICIANDO PIPELINE DE INFERÊNCIA SMARTCORR ===")
    
    try:
        # Precisa puxar os dados mais recentes do banco a cada meia hora
        logger.info("--- Passo 1: Data Loading (Buscando real e metas) ---")
        from src.data_loading import load_data
        load_data.main()
        
        # Limpar nulos/estruturar campos lógicos
        logger.info("--- Passo 2: Data Preprocessing ---")
        from src.data_preprocessing import clean_data
        clean_data.main()
        
        # Criar as nossas engenharia de features (Lags, Taxas de Fila, Erros)
        logger.info("--- Passo 3: Feature Engineering ---")
        from src.feature_engineering import build_features
        build_features.main()
        
        # ATENÇÃO: Pula o Treinamento! Passamos direto para a Projeção (Predict)
        # 3. Pipeline de Inferência
        logger.info("--- Passo 4: Inference (Modelo prevendo Novos Horários) ---")
        from src.inference import predict
        predict.main()
        
        logger.info("=== INFERÊNCIA EXECUTADA COM SUCESSO. Base ODS Atualizada. ===")

    except Exception as e:
        logger.error(f"Erro fatal durante a inferência: {e}", exc_info=True)
        # Usado para agendadores segurarem o erro na tela (ex: Task Scheduler)
        input("Pressione Enter para fechar...") 
        sys.exit(1)

if __name__ == "__main__":
    main()
