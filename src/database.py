import os
import pyodbc
import logging
import yaml

# Logger configuration
logger = logging.getLogger(__name__)

def load_config():
    """Carrega as configurações do arquivo params.yaml"""
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'params.yaml')
    with open(config_path, 'r', encoding='utf-8') as file:
        return yaml.safe_load(file)

def get_connection_string():
    """Gera a string de conexão SQLAlchemy baseada em configurações e credenciais."""
    
    # 1. Se houver uma string de conexão explícita via variável de ambiente (DataCore)
    env_conn_str = os.getenv('DB_CONNECTION_STRING')
    if env_conn_str and env_conn_str != 'None':
        # Clean quotes if passed by the CLI
        env_conn_str = env_conn_str.strip("'\"")
        logger.info("Usando connection string fornecida via ambiente (DataCore).")
        # Convert ODBC to SQLAlchemy format if needed
        if 'DRIVER=' in env_conn_str.upper():
            from urllib.parse import quote_plus
            logger.info("Convertendo ODBC string para formato SQLAlchemy URL...")
            return f"mssql+pyodbc:///?odbc_connect={quote_plus(env_conn_str)}"
        return env_conn_str
    
    # 2. Tenta carregar credenciais locais
    try:
        # Adiciona o diretório atual ao path para importar credencial se necessário
        import sys
        sys.path.append(os.path.dirname(os.path.abspath(__file__)))
        from credencial import SERVER_DEST, DATABASE_DEST, USERNAME_DEST, PASSWORD_DEST
    except ImportError:
        logger.warning("Arquivo 'credencial.py' não encontrado. Usando variáveis de ambiente ou placeholders.")
        SERVER_DEST = os.getenv('DB_SERVER', 'SPWS-VM-DB81')
        DATABASE_DEST = os.getenv('DB_NAME', 'OdsCorp')
        USERNAME_DEST = os.getenv('DB_USER', None)
        PASSWORD_DEST = os.getenv('DB_PASS', None)
    
    # Criar string SQLAlchemy
    if USERNAME_DEST and USERNAME_DEST != 'None':
        # Autenticação SQL - SQLAlchemy com pyodbc
        from urllib.parse import quote_plus
        odbc_str = (
            f"DRIVER={{SQL Server}};"
            f"SERVER={SERVER_DEST};"
            f"DATABASE={DATABASE_DEST};"
            f"UID={USERNAME_DEST};"
            f"PWD={PASSWORD_DEST};"
        )
        conn_str = f"mssql+pyodbc:///?odbc_connect={quote_plus(odbc_str)}"
        logger.info(f"Configurando conexão SQLAlchemy (SQL Auth): Server={SERVER_DEST}, DB={DATABASE_DEST}")
    else:
        # Windows Auth - pode falhar se domínio não for confiável
        from urllib.parse import quote_plus
        odbc_str = (
            f"DRIVER={{SQL Server}};"
            f"SERVER={SERVER_DEST};"
            f"DATABASE={DATABASE_DEST};"
            f"Trusted_Connection=yes;"
        )
        conn_str = f"mssql+pyodbc:///?odbc_connect={quote_plus(odbc_str)}"
        logger.warning(
            f"Usando Windows Auth (Server={SERVER_DEST}, DB={DATABASE_DEST}). "
            f"Se falhar, defina as variáveis de ambiente DB_USER e DB_PASS "
            f"no DataCore para usar SQL Authentication."
        )
    
    return conn_str

def get_connection():
    """Retorna um objeto de conexão SQLAlchemy engine."""
    from sqlalchemy import create_engine
    conn_str = get_connection_string()
    try:
        # Criar engine SQLAlchemy com timeout
        engine = create_engine(conn_str, pool_timeout=600)
        logger.info("Conexão SQLAlchemy estabelecida com sucesso.")
        return engine
    except Exception as e:
        logger.error(f"Erro ao conectar ao banco de dados: {e}")
        raise
