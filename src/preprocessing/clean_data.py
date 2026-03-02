import pandas as pd
import numpy as np
import logging
import os
import yaml

logger = logging.getLogger(__name__)

def carregar_configuracao():
    """Carrega as configurações do params.yaml"""
    with open("params.yaml", "r") as f:
        return yaml.safe_load(f)

def realizar_limpeza(df):
    """
    Limpeza de dados: formatação de datas, exclusão nulos inúteis, criação do target e features temporais.
    """
    logger.info(f"Linhas antes da limpeza: {len(df)}")

    # 1. Padronização de DataHora e Features Temporais
    if 'DataRef' in df.columns and 'Intervalo' in df.columns:
        # Pega apenas os 8 primeiros caracteres do Intervalo caso venha como "10:00:00.0000000"
        df['Data_Str'] = df['DataRef'].astype(str)
        df['Intervalo_Str'] = df['Intervalo'].astype(str).str[:8] 
        df['DataHora'] = pd.to_datetime(df['Data_Str'] + ' ' + df['Intervalo_Str'], errors='coerce')
        
        # Features temporais básicas (são extraídas da data)
        df['Hora'] = df['DataHora'].dt.hour
        df['DiaSemana'] = df['DataHora'].dt.dayofweek # 0=Segunda, 6=Domingo
        
        # Opcional: Remover as strings agora que temos o objeto DataHora
        df.drop(['Data_Str', 'Intervalo_Str'], axis=1, inplace=True, errors='ignore')

    # 2. Filtro de Relevância (Remover intervalos vazios/fechados)
    # Se a operação não previu chamadas E não atendeu chamadas, é madrugada fechada.
    filtro_relevante = (df['Vol_Previsto'] > 0) | (df['Vol_Real'] > 0)
    df = df[filtro_relevante].copy()
    logger.info(f"Linhas após remover slots completamente vazios: {len(df)}")

    # 3. Calcular Target (Nível de Serviço Real)
    # A fórmula é Atendidas_no_SLA / Oferecidas
    # Tratamento matemático: divisão por zero vira 0 (ou seja, se Vol_Real=0, NS=0)
    df['NS_Real'] = np.where(
        df['Vol_Real'] > 0, 
        df['Vol_Atendidas_NS_Real'] / df['Vol_Real'], 
        0.0
    )
    
    # Prevenção extra: clipping limitando Nível de Serviço entre 0 e 1 (100%)
    df['NS_Real'] = df['NS_Real'].clip(lower=0.0, upper=1.0)

    # 4. Tratar Valores Nulos Adicionais
    # O SQL via ISNULL() resolve a maioria, mas garantimos que as numéricas não tenham NAs
    colunas_numericas = df.select_dtypes(include=[np.number]).columns
    df[colunas_numericas] = df[colunas_numericas].fillna(0.0)

    return df

def main():
    config = carregar_configuracao()
    caminho_raw = config['data']['raw_path']
    caminho_clean = config['data']['clean_path']
    
    # Cria pasta se não existir
    os.makedirs(os.path.dirname(caminho_clean), exist_ok=True)
    
    logger.info(f"Carregando dados brutos de: {caminho_raw}")
    try:
        df_bruto = pd.read_csv(caminho_raw)
        
        df_limpo = realizar_limpeza(df_bruto)
        
        df_limpo.to_csv(caminho_clean, index=False)
        logger.info(f"Dados limpos salvos em: {caminho_clean}. Total processado: {len(df_limpo)} linhas.")
        
    except Exception as e:
        logger.error(f"Erro na limpeza de dados: {e}")
        raise

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
