import os

# 1. Configuração e Ambiente: Ativação do Virtual Environment
enable_venv = os.path.join(os.path.dirname(os.path.abspath(__file__)), r'venv\Scripts\activate_this.py')
if os.path.exists(enable_venv):
    exec(open(enable_venv).read(), {'__file__': enable_venv})
else:
    print(f"Aviso: Ambiente virtual não encontrado em {enable_venv}")

# 1.2. Controle de Performance e Concorrência
os.environ["LOKY_MAX_CPU_COUNT"] = "1"

import pandas as pd
import pyodbc
from credencial import SERVER_DEST, DATABASE_DEST, USERNAME_DEST, PASSWORD_DEST

class LeitorBancoDados:
    def __init__(self, server=SERVER_DEST, database=DATABASE_DEST, username=USERNAME_DEST, password=PASSWORD_DEST):
        self.server = server
        self.database = database
        self.username = username
        self.password = password
        self.conexao = None
        self.cursor = None
        
        self.conectar()

    def conectar(self):
        """Estabelece conexão com o SQL Server"""
        try:
            if self.username and self.password:
                # Autenticação SQL Server
                conn_str = (
                    f'DRIVER={{ODBC Driver 17 for SQL Server}};'
                    f'SERVER={self.server};'
                    f'DATABASE={self.database};'
                    f'UID={self.username};'
                    f'PWD={self.password};'
                    f'TrustServerCertificate=yes;'
                )
            else:
                # Autenticação Windows
                print("Tentando conexão com Autenticação do Windows...")
                conn_str = (
                    f'DRIVER={{ODBC Driver 17 for SQL Server}};'
                    f'SERVER={self.server};'
                    f'DATABASE={self.database};'
                    f'Trusted_Connection=yes;'
                    f'TrustServerCertificate=yes;'
                )
                
            self.conexao = pyodbc.connect(conn_str)
            self.cursor = self.conexao.cursor()
            print("Conexão estabelecida com sucesso.")
        except Exception as e:
            print(f"Erro ao conectar ao banco de dados: {e}")
            raise

    def ler_tabela(self, nome_tabela, limite=100):
        """Lê uma tabela do banco de dados e retorna um DataFrame"""
        try:
            query = f"SELECT TOP {limite} * FROM {nome_tabela}"
            print(f"Executando consulta: {query}")
            
            self.cursor.execute(query)
            colunas = [coluna[0] for coluna in self.cursor.description]
            dados = self.cursor.fetchall()
            
            # Convertendo para lista de tuplas para criação do DataFrame
            dados_lista = [tuple(linha) for linha in dados]
            
            df = pd.DataFrame.from_records(dados_lista, columns=colunas)
            print(f"Dados carregados com sucesso. Linhas retornadas: {len(df)}")
            return df
        except Exception as e:
            print(f"Erro ao ler tabela {nome_tabela}: {e}")
            return pd.DataFrame()

    def __del__(self):
        """Fecha a conexão ao destruir o objeto"""
        if hasattr(self, 'cursor') and self.cursor:
            self.cursor.close()
        if hasattr(self, 'conexao') and self.conexao:
            self.conexao.close()
            print("Conexão fechada.")

if __name__ == "__main__":
    # Exemplo de uso
    try:
        leitor = LeitorBancoDados()
        
        # Substitua pelo nome da tabela que deseja testar
        # Exemplo baseado no contexto anterior: [Tp_Analytics].[AbsGuard].[Previsao_Absenteismo]
        tabela_teste = "[OdsFpw].[dbo].[DataFolhaPgto]" 
        
        df_resultado = leitor.ler_tabela(tabela_teste)
        
        if not df_resultado.empty:
            print("\nPrimeiras 5 linhas do DataFrame:")
            print(df_resultado.head())
            
            # Mostra informações sobre os tipos de dados
            print("\nInformações do DataFrame:")
            print(df_resultado.info())
        else:
            print("\nO DataFrame está vazio ou ocorreu um erro.")
            
    except Exception as erro_principal:
        print(f"Erro fatal na execução: {erro_principal}")
