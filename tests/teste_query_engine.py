import pandas as pd
import pyodbc
from credencial import SERVER_DEST, DATABASE_DEST, USERNAME_DEST, PASSWORD_DEST
import os
import sys

# Força print imediato e UTF-8
sys.stdout.reconfigure(encoding='utf-8')

server = SERVER_DEST
database = DATABASE_DEST 
username = USERNAME_DEST
password = PASSWORD_DEST

# Configuração de conexão igual ao que funcionou
conn_str = (
    f'DRIVER={{ODBC Driver 17 for SQL Server}};'
    f'SERVER={server};'
    f'DATABASE={database};'
    f'Trusted_Connection=yes;'
    f'TrustServerCertificate=yes;'
    f'Encrypt=yes;'
)

print(f"=== TESTE QUERY ENGINE ===")
print(f"Servidor: {server}")
print(f"Banco Conexao: {database}")

try:
    print("Conectando...")
    conn = pyodbc.connect(conn_str)
    print("Conexão OK!")
    
    # Query simplificada do Engine (TOP 10 e datas recentes)
    # Valida acesso a [OdsCorp]
    query = """
    SELECT TOP 10
        COALESCE(R.program_ccmsid, M.program_ccmsid) AS program_ccmsid,
        COALESCE(R.Channel, M.Channel) AS Channel,
        COALESCE(R.RowDate, M.date) AS Data,
        ISNULL(R.OFERECIDAS, 0) AS Volume_Real
    FROM [OdsCorp].[DataMart].[factIntradayDelivery] R WITH (NOLOCK)
    FULL OUTER JOIN [OdsCorp].[DataMart].[MetasIntradiariasForecastDelivery] M WITH (NOLOCK)
        ON R.program_ccmsid = M.program_ccmsid
        AND R.Channel = M.Channel
        AND R.RowDate = M.date
        AND R.Intervalo = M.interval
    WHERE 
        COALESCE(R.RowDate, M.date) >= DATEADD(DAY, -5, GETDATE())
    """
    
    print("Executando query principal do Engine...")
    df = pd.read_sql(query, conn)
    print(f"Sucesso! Retornou {len(df)} linhas.")
    
    if not df.empty:
        print("\nPrimeiras 5 linhas:")
        print(df.head())
    else:
        print("\nAviso: DataFrame vazio. Verifique se há dados nos últimos 5 dias.")
        
except Exception as e:
    print(f"\nERRO: {e}")
    print("Verifique se o usuário tem permissão de leitura no banco [OdsCorp].")
