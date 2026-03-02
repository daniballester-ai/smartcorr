import pyodbc
import os
from src.database import get_connection_string

def test_connection():
    print("--- Teste de Conectividade Simplificado ---")
    conn_str = get_connection_string()
    print(f"String de Conexão: {conn_str}")
    
    try:
        print("Tentando conectar (Timeout padrão)...")
        conn = pyodbc.connect(conn_str, timeout=10)
        print("Conexão SUCESSO!")
        
        cursor = conn.cursor()
        cursor.execute("SELECT @@VERSION")
        row = cursor.fetchone()
        print(f"Versão SQL Server: {row[0]}")
        
        conn.close()
        return True
    except Exception as e:
        print(f"FALHA na conexão: {e}")
        return False

if __name__ == "__main__":
    test_connection()
