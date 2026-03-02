import sys
import logging

# Configure logging to stdout
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_imports():
    logger.info("Iniciando teste de importação de bibliotecas...")
    
    libs = [
        ('pandas', 'pd'),
        ('numpy', 'np'),
        ('pyodbc', None),
        ('sklearn', None),
        ('sklearn.ensemble', 'RandomForestRegressor')
    ]

    all_success = True
    for lib_name, alias in libs:
        try:
            if alias:
                if alias == 'RandomForestRegressor':
                    from sklearn.ensemble import RandomForestRegressor
                    logger.info(f"SUCESSO: from sklearn.ensemble import RandomForestRegressor")
                else:
                    exec(f"import {lib_name} as {alias}")
                    logger.info(f"SUCESSO: import {lib_name} as {alias}")
            else:
                exec(f"import {lib_name}")
                logger.info(f"SUCESSO: import {lib_name}")
        except Exception as e:
            logger.error(f"FALHA: Erro ao importar {lib_name}: {e}")
            all_success = False

    if all_success:
        logger.info("TODAS AS IMPORTAÇÕES FORAM BEM SUCEDIDAS!")
    else:
        logger.error("HOUVE FALHAS NAS IMPORTAÇÕES.")

if __name__ == "__main__":
    test_imports()
