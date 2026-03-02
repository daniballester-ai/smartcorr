import os
import pyodbc
import logging
import yaml

# Logger configuration
logger = logging.getLogger(__name__)

def load_config():
    """Carrega as configurações do arquivo params.yaml"""
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'params.yaml')
    with open(config_path, 'r') as file:
        return yaml.safe_load(file)

def get_connection_string():
    """Gera a string de conexão baseada em configurações e credenciais."""
    
    # Tenta carregar credenciais locais
    try:
        # Adiciona o diretório atual ao path para importar credencial se necessário
        # Assumindo que credencial.py está no mesmo nível deste script ou root
        import sys
        sys.path.append(os.path.dirname(os.path.abspath(__file__)))
        from credencial import SERVER_DEST, DATABASE_DEST, USERNAME_DEST, PASSWORD_DEST
    except ImportError:
        logger.warning("Arquivo 'credencial.py' não encontrado. Usando variáveis de ambiente ou placeholders.")
        SERVER_DEST = os.getenv('DB_SERVER', 'SPWS-VM-DB81')
        DATABASE_DEST = os.getenv('DB_NAME', 'OdsCorp')
        USERNAME_DEST = os.getenv('DB_USER', None)
        PASSWORD_DEST = os.getenv('DB_PASS', None)

    # Lógica de conexão (Revertido para padrão do legado SmartCorr_Engine.py)
    driver = 'SQL Server' # Driver genérico que funciona no ambiente do usuário
    
    if not USERNAME_DEST or USERNAME_DEST == 'None':
        # Autenticação Windows
        conn_str = (
            f'DRIVER={driver};'
            f'SERVER={SERVER_DEST};'
            f'DATABASE={DATABASE_DEST};'
            f'Trusted_Connection=yes;'
        )
        logger.info(f"Configurando conexão (Win Auth - Legacy Driver): Server={SERVER_DEST}, DB={DATABASE_DEST}")
    else:
        # Autenticação SQL
        conn_str = (
            f'DRIVER={driver};'
            f'SERVER={SERVER_DEST};'
            f'DATABASE={DATABASE_DEST};'
            f'UID={USERNAME_DEST};'
            f'PWD={PASSWORD_DEST};'
        )
        logger.info(f"Configurando conexão (SQL Auth - Legacy Driver): Server={SERVER_DEST}, DB={DATABASE_DEST}")
    
    return conn_str

def get_connection():
    """Retorna um objeto de conexão pyodbc."""
    conn_str = get_connection_string()
    try:
        # Timeout aumentado para 10 minutos (600s) devido ao volume de dados
        conn = pyodbc.connect(conn_str, timeout=600)
        return conn
    except Exception as e:
        logger.error(f"Erro ao conectar ao banco de dados: {e}")
        raise
