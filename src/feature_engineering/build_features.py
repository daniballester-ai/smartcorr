import pandas as pd
import numpy as np
import logging
import os
import yaml
from datetime import datetime

logger = logging.getLogger(__name__)

def carregar_configuracao():
    with open("params.yaml", "r", encoding='utf-8') as f:
        return yaml.safe_load(f)

def criar_features(df):
    """
    Engenharia de Features: Deltas e Lags (Memória histórica).
    """
    if df is None or df.empty:
        return None
        
    df = df.copy()
    
    # Certificar que DataHora é datetime para ordenação e filtro
    if not pd.api.types.is_datetime64_any_dtype(df['DataHora']):
         df['DataHora'] = pd.to_datetime(df['DataHora'])
         
    # 1. Deltas (Erros do Erlang)
    df['Delta_Volume'] = df['Vol_Real'] - df['Vol_Previsto']
    df['Delta_HC'] = df['HC_Real_Equiv'] - df['HC_Previsto']
    
    # O Delta TMA é complexo pois temos AHT Total. O AHT médio = Tempo_Total / Volume
    # Vamos criar TMA_Real_Avg e TMA_Previsto_Avg para achar o Delta TMA
    df['TMA_Real_Avg'] = np.where(df['Vol_Atendidas'] > 0, df['Tempo_AHT_Real_Total'] / df['Vol_Atendidas'], 0.0)
    df['TMA_Previsto_Avg'] = np.where(df['Vol_Previsto'] > 0, df['Tempo_AHT_Previsto_Total'] / df['Vol_Previsto'], 0.0)
    df['Delta_TMA'] = df['TMA_Real_Avg'] - df['TMA_Previsto_Avg']
    
    # 1.5. Engenharia de Features Módulo RH (Indicadores GO!)
    # Previne a distorção do Paradoxo de Simpson calculando a taxa pontual no Python e protegendo contra divisão por zero
    df['ABS_Taxa_Daily'] = np.where(df['ABS_Escala_Sec_Daily'] > 0, df['ABS_Tempo_Sec_Daily'] / df['ABS_Escala_Sec_Daily'], 0.0)
    df['Turnover_Taxa_Daily'] = np.where(df['Turnover_Ativos_Daily'] > 0, df['Turnover_Desligados_Daily'] / df['Turnover_Ativos_Daily'], 0.0)
    
    # 1.6 Fatores de Gargalo / Abandono
    df['Taxa_Abandono'] = np.where(df['Vol_Real'] > 0, df['Vol_Abandono'] / df['Vol_Real'], 0.0)
    
    # 1.7. Engenharia de Tempos de Fila (TME e Ocupação)
    # TME_Real: Transforma o total massivo de segundos de fila em um TME palatável em segundos médios
    df['TME_Real_Avg'] = np.where(df['Vol_Real'] > 0, df['Tempo_Espera_Total'] / df['Vol_Real'], 0.0)
    
    # Ocupação_Real: A porcentagem do tempo logado que foi efetivamente gasto em chamadas ativas
    # Tempo Total Disponível = Headcount Logado * 1800 (pois os intervalos são de 30 minutos)
    tempo_logado_total = df['HC_Real_Equiv'] * 1800
    df['Taxa_Ocupacao'] = np.where(tempo_logado_total > 0, df['Tempo_AHT_Real_Total'] / tempo_logado_total, 0.0)
    
    # 1.8. Taxas de Ineficiência Sistêmicas (Pausas relativas ao Headcount)
    df['Taxa_Pausa_Tecnica'] = np.where(tempo_logado_total > 0, df['Pausa_Tecnica_Sec'] / tempo_logado_total, 0.0)
    df['Taxa_Pausa_Pessoal'] = np.where(tempo_logado_total > 0, df['Pausa_Pessoal_Sec'] / tempo_logado_total, 0.0)
    df['Taxa_Pausa_Gestao'] = np.where(tempo_logado_total > 0, df['Pausa_Gestao_Sec'] / tempo_logado_total, 0.0)
    
    # 1.9. Desvios (Aceleração vs Planejamento) Percentuais
    df['Desvio_HC_Pct'] = np.where(df['HC_Previsto'] > 0, df['Delta_HC'] / df['HC_Previsto'], 0.0)
    df['Desvio_Volume_Pct'] = np.where(df['Vol_Previsto'] > 0, df['Delta_Volume'] / df['Vol_Previsto'], 0.0)
    
    # 2. Lags (Sinais de Fumaça - Evitando Data Leakage do Futuro)
    # Ordenar chronologicamente por operação e canal
    df.sort_values(by=['CodPrograma', 'Canal', 'DataHora'], inplace=True)
    
    # Lags de níveis macro de 1, 2 e 3 períodos anteriores (últimos 90 minutos)
    df['NS_Lag_1'] = df.groupby(['CodPrograma', 'Canal'])['NS_Real'].shift(1)
    df['NS_Lag_2'] = df.groupby(['CodPrograma', 'Canal'])['NS_Real'].shift(2)
    df['NS_Lag_3'] = df.groupby(['CodPrograma', 'Canal'])['NS_Real'].shift(3)
    
    # Transformando as variaveis de Ineficiência/Engenharia em Lags 
    # para prever o futuro baseado no "Gargalo Imediato (D-1 Intervalo)"
    df['Taxa_Abandono_Lag_1'] = df.groupby(['CodPrograma', 'Canal'])['Taxa_Abandono'].shift(1).fillna(0.0)
    df['TME_Real_Avg_Lag_1'] = df.groupby(['CodPrograma', 'Canal'])['TME_Real_Avg'].shift(1).fillna(0.0)
    df['Taxa_Ocupacao_Lag_1'] = df.groupby(['CodPrograma', 'Canal'])['Taxa_Ocupacao'].shift(1).fillna(0.0)
    df['Taxa_Pausa_Tecnica_Lag_1'] = df.groupby(['CodPrograma', 'Canal'])['Taxa_Pausa_Tecnica'].shift(1).fillna(0.0)
    df['Taxa_Pausa_Pessoal_Lag_1'] = df.groupby(['CodPrograma', 'Canal'])['Taxa_Pausa_Pessoal'].shift(1).fillna(0.0)
    df['Taxa_Pausa_Gestao_Lag_1'] = df.groupby(['CodPrograma', 'Canal'])['Taxa_Pausa_Gestao'].shift(1).fillna(0.0)
    df['Desvio_HC_Pct_Lag_1'] = df.groupby(['CodPrograma', 'Canal'])['Desvio_HC_Pct'].shift(1).fillna(0.0)
    df['Desvio_Volume_Pct_Lag_1'] = df.groupby(['CodPrograma', 'Canal'])['Desvio_Volume_Pct'].shift(1).fillna(0.0)
    
    # Tratar os NaNs gerados pelo Lag do NS_Real (preencher com a média do próprio NS_Real, ou 0 se nulo)
    media_ns = df['NS_Real'].mean()
    df['NS_Lag_1'] = df['NS_Lag_1'].fillna(media_ns)
    df['NS_Lag_2'] = df['NS_Lag_2'].fillna(media_ns)
    df['NS_Lag_3'] = df['NS_Lag_3'].fillna(media_ns)
    
    return df

def main():
    config = carregar_configuracao()
    caminho_clean = config['data']['clean_path']
    caminho_train = config['data']['processed_train_path']
    caminho_future = config['data']['processed_future_path']
    
    os.makedirs(os.path.dirname(caminho_train), exist_ok=True)
    
    logger.info(f"Carregando dados limpos de: {caminho_clean}")
    df = pd.read_csv(caminho_clean)
    
    df_processado = criar_features(df)
    
    # ---------------------------------------------------------
    # Lógica de Rolling Forecast: Identificar até quando temos "Real" de fato
    # ---------------------------------------------------------
    mask_real_preenchido = df_processado['Vol_Real'] > 0
    if mask_real_preenchido.any():
        ultimo_intervalo_com_dado = df_processado[mask_real_preenchido]['DataHora'].max()
    else:
        # Se não há dado real novo na base (ex: início de uma nova base de dados), prever desde o começo de hoje
        ultimo_intervalo_com_dado = pd.to_datetime(datetime.now().date())
        
    filtro_futuro = (df_processado['DataHora'] > ultimo_intervalo_com_dado)
    
    # Filtro base: Só consideramos "Futuro de Previsão" o que for de HOJE em diante.
    # Evita que a máquina tente prever "buracos" do mês passado com Vol Real = 0.
    hoje = pd.to_datetime(datetime.now().date())
    filtro_hoje_em_diante = (df_processado['DataHora'] >= hoje)
    
    mask_futuro_final = filtro_futuro & filtro_hoje_em_diante
    
    df_train = df_processado[~mask_futuro_final].copy()
    df_future = df_processado[mask_futuro_final].copy()
    
    if not df_train.empty:
        df_train.to_csv(caminho_train, index=False)
        logger.info(f"Dados de TREINO salvos em: {caminho_train}. Linhas: {len(df_train)}")
    else:
        logger.warning("Nenhum dado de treino encontrado.")
        df_train.to_csv(caminho_train, index=False)
        
    if not df_future.empty:
        df_future.to_csv(caminho_future, index=False)
        logger.info(f"Dados FUTUROS (para predição) salvos em: {caminho_future}. Linhas: {len(df_future)}")
    else:
        logger.info("Nenhum dado futuro encontrado na base.")
        df_future.to_csv(caminho_future, index=False)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
