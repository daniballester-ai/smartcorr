import pandas as pd
import pyodbc
from credencial import SERVER_DEST, DATABASE_DEST, USERNAME_DEST, PASSWORD_DEST
import sys

sys.stdout.reconfigure(encoding='utf-8')

conn_str = (
    f'DRIVER={{ODBC Driver 17 for SQL Server}};'
    f'SERVER={SERVER_DEST};'
    f'DATABASE={DATABASE_DEST};'
    f'Trusted_Connection=yes;'
    f'TrustServerCertificate=yes;'
    f'Encrypt=yes;'
)

print(f"Listando colunas de [OdsCorp].[DataMart].[MetasIntradiariasForecastDelivery]...")

try:
    conn = pyodbc.connect(conn_str)
    
    # Query para pegar 1 linha apenas para ver colunas
    query = "SELECT TOP 1 * FROM [OdsCorp].[DataMart].[MetasIntradiariasForecastDelivery]"
    
    cursor = conn.cursor()
    cursor.execute(query)
    
    colunas = [column[0] for column in cursor.description]
    
    print("\nCOLUNAS ENCONTRADAS:")
    for col in sorted(colunas):
        print(f" - {col}")
        
except Exception as e:
    print(f"\nERRO: {e}")
