import pandas as pd
import numpy as np
import logging
import os
import yaml
import joblib
from datetime import datetime
import shap

from src.database import get_connection

logger = logging.getLogger(__name__)

# Mapeamento do Agrupamento da IA (Inteligência Semântica)
PILARES = {
    'Volumetria': ['Vol_Previsto', 'Vol_Real', 'Vol_Atendidas', 'Vol_Abandono', 'Delta_Volume', 'Taxa_Abandono_Lag_1', 'Desvio_Volume_Pct_Lag_1'],
    'Pessoas': ['HC_Previsto', 'HC_Real_Equiv', 'Pausa_Tecnica_Sec', 'Pausa_Pessoal_Sec', 'Pausa_Gestao_Sec', 'Delta_HC', 'Taxa_Pausa_Tecnica_Lag_1', 'Taxa_Pausa_Pessoal_Lag_1', 'Taxa_Pausa_Gestao_Lag_1', 'Taxa_Ocupacao_Lag_1', 'Desvio_HC_Pct_Lag_1', 'PerdaLog_Taxa_Daily', 'TechIssues_Taxa_Daily', 'NewHire_Pct_Daily', 'AgentIssues_Taxa_Daily'],
    'TMA': ['Tempo_AHT_Previsto_Total', 'Tempo_AHT_Real_Total', 'Tempo_Espera_Total', 'Delta_TMA', 'TME_Real_Avg_Lag_1'],
    'Contexto_Lags': ['Hora', 'DiaSemana', 'NS_Lag_1', 'NS_Lag_2', 'NS_Lag_3']
}

def get_pilar(feature_name):
    """Encontra ao qual pilar analítico uma variável pretence."""
    for pilar, variaveis in PILARES.items():
        if feature_name in variaveis:
            return pilar
    return 'Geral'

def carregar_configuracao():
    with open("params.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def calcular_explicabilidade_shap(modelo, X):
    """Gera os pesos do que influenciou (positiva/negativamente) na tomada de decisão preditiva."""
    explainer = shap.TreeExplainer(modelo)
    shap_values = explainer.shap_values(X)
    return shap_values

def processar_previsoes(df, predicoes, shap_values, features):
    """Transforma o modelo matemático de árvores em Tuplas relacionais preparadas para o Power BI/Next.js"""
    resultados = []
    
    # Tratamento para garantir acesso à data e intervalo
    if 'DataRef' not in df.columns:
        df['DataRef'] = df['DataHora'].astype(str).str[:10]
    if 'Intervalo' not in df.columns:
        df['Intervalo'] = df['DataHora'].astype(str).str[11:19]
    
    for i in range(len(df)):
        linha = df.iloc[i]
        valores_shap = shap_values[i]
        
        # Agrupamento (Pilares)
        impacto_volumetria = 0.0
        impacto_pessoas = 0.0
        impacto_tma = 0.0
        impacto_contexto = 0.0
        
        feature_impactos = []
        
        for j, feature in enumerate(features):
            impacto = float(valores_shap[j])
            pilar = get_pilar(feature)
            
            # Somatório do Efeito Cascata do Pilar
            if pilar == 'Volumetria': impacto_volumetria += impacto
            elif pilar == 'Pessoas': impacto_pessoas += impacto
            elif pilar == 'TMA': impacto_tma += impacto
            elif pilar == 'Contexto_Lags': impacto_contexto += impacto
                
            feature_impactos.append({'nome': feature, 'pilar': pilar, 'impacto': impacto})
            
        # Classificação do Raking: Quem prejudicou? E quem salvou?
        feature_impactos.sort(key=lambda x: x['impacto']) # Do mais negativo pro mais positivo
        
        ofensores = feature_impactos[:3] # Os 3 mais negativos na ponta esquerda
        impulsionadores = feature_impactos[-3:] # Os 3 mais positivos na ponta direita
        impulsionadores.reverse() # Inverter para o Top 1 mais forte vir primeiro
        
        # Limiar de Sensibilidade: Ignorar "ofensores" que afetaram menos que 0.1% do NS.
        ofensores = [o if o['impacto'] < -0.001 else None for o in ofensores]
        impulsionadores = [i if i['impacto'] > 0.001 else None for i in impulsionadores]
        
        # Clip da predição pra não jogar 110% no BI caso o XGBoost tenha passado da margem.
        ns_previsto = min(max(float(predicoes[i]), 0.0), 1.0)
        
        # Configuração de Valores Default limpos para o Power BI
        def_nome = "Sem Impacto Relevante"
        def_pilar = "N/A"
        def_val = 0.000
        
        # Criar Tupla pro `executemany`
        resultados.append((
            linha['DataRef'], linha['Intervalo'], int(linha['CodPrograma']), int(linha.get('Canal', 7)),
            ns_previsto, 
            int(linha.get('Vol_Previsto', 0)), int(linha.get('HC_Previsto', 0)), float(linha.get('TMA_Previsto_Avg', 0.0)), float(linha.get('NS_Lag_1', 0.0)),
            
            impacto_volumetria, impacto_pessoas, impacto_tma, impacto_contexto,
            
            # Ofensores 1 a 3
            ofensores[0]['nome'] if ofensores[0] else def_nome,
            ofensores[0]['pilar'] if ofensores[0] else def_pilar,
            ofensores[0]['impacto'] if ofensores[0] else def_val,
            
            ofensores[1]['nome'] if ofensores[1] else def_nome,
            ofensores[1]['pilar'] if ofensores[1] else def_pilar,
            ofensores[1]['impacto'] if ofensores[1] else def_val,
            
            ofensores[2]['nome'] if ofensores[2] else def_nome,
            ofensores[2]['pilar'] if ofensores[2] else def_pilar,
            ofensores[2]['impacto'] if ofensores[2] else def_val,
            
            # Impulsionadores 1 a 3
            impulsionadores[0]['nome'] if impulsionadores[0] else def_nome,
            impulsionadores[0]['pilar'] if impulsionadores[0] else def_pilar,
            impulsionadores[0]['impacto'] if impulsionadores[0] else def_val,
            
            impulsionadores[1]['nome'] if impulsionadores[1] else def_nome,
            impulsionadores[1]['pilar'] if impulsionadores[1] else def_pilar,
            impulsionadores[1]['impacto'] if impulsionadores[1] else def_val,
            
            impulsionadores[2]['nome'] if impulsionadores[2] else def_nome,
            impulsionadores[2]['pilar'] if impulsionadores[2] else def_pilar,
            impulsionadores[2]['impacto'] if impulsionadores[2] else def_val
        ))
        
    return resultados

def salvar_no_banco(tuplas_dados):
    conn = get_connection()
    cursor = conn.cursor()
    
    query = """
    INSERT INTO [OdsCorp].[SmartCorr].[FactSmartCorr_Previsao] 
    ([DataRef], [Intervalo], [CodPrograma], [Canal], [NS_Previsto_SmartCorr],
     [Vol_Previsto], [HC_Previsto], [TMA_Previsto_Avg], [NS_Lag_1],
     [Impacto_Pilar_Volumetria], [Impacto_Pilar_Pessoas], [Impacto_Pilar_TMA], [Impacto_Pilar_Contexto],
     [Ofensor_1_Nome], [Ofensor_1_Pilar], [Ofensor_1_Impacto],
     [Ofensor_2_Nome], [Ofensor_2_Pilar], [Ofensor_2_Impacto],
     [Ofensor_3_Nome], [Ofensor_3_Pilar], [Ofensor_3_Impacto],
     [Impulsionador_1_Nome], [Impulsionador_1_Pilar], [Impulsionador_1_Impacto],
     [Impulsionador_2_Nome], [Impulsionador_2_Pilar], [Impulsionador_2_Impacto],
     [Impulsionador_3_Nome], [Impulsionador_3_Pilar], [Impulsionador_3_Impacto])
    VALUES (?, ?, ?, ?, ?,   ?, ?, ?, ?,   ?, ?, ?, ?,   ?, ?, ?,   ?, ?, ?,   ?, ?, ?,   ?, ?, ?,   ?, ?, ?,   ?, ?, ?)
    """
    
    try:
        if tuplas_dados:
            # Estratégia do Projeto (code.md): Delete + Insert via fast_executemany
            # Exclusão Cirúrgica "Rolling Forecast": Apaga apenas os registros a partir do menor intervalo calculado
            df_tuplas = pd.DataFrame(tuplas_dados)
            
            # Descobre o menor intervalo de cada DataRef (Col 0 = DataRef, Col 1 = Intervalo)
            agrupado = df_tuplas.groupby(0)[1].min().reset_index()
            
            logger.info("Limpando previsões antigas (Soft Delete cirúrgico) no BD...")
            for _, row in agrupado.iterrows():
                dt_ref = str(row[0])
                min_int = str(row[1])
                query_del = f"DELETE FROM [OdsCorp].[SmartCorr].[FactSmartCorr_Previsao] WHERE [DataRef] = '{dt_ref}' AND [Intervalo] >= '{min_int}'"
                cursor.execute(query_del)
                logger.info(f"Limpo Data={dt_ref} >= Intervalo {min_int}")
            
            logger.info(f"Gravando {len(tuplas_dados)} novos registros SHAP multidimensionais. (fast_executemany=True)")
            cursor.fast_executemany = True
            cursor.executemany(query, tuplas_dados)
            conn.commit()
            logger.info("Transação no Banco efetuada com sucesso!")
    except Exception as e:
        conn.rollback()
        logger.error(f"Erro ao salvar Fato no SQL Server: {e}")
        raise
    finally:
        conn.close()

def main():
    config = carregar_configuracao()
    caminho_modelo = config['model']['path']
    caminho_futuro = config['data']['processed_future_path']
    features = config['data']['features']
    
    if not os.path.exists(caminho_futuro):
        logger.warning(f"Arquivo {caminho_futuro} ausente. Fim da rotina.")
        return
        
    logger.info("1. Carregando modelo Preditivo Treinado (XGBoost)...")
    modelo = joblib.load(caminho_modelo)
    
    logger.info("2. Lendo dados Futuros da Gestão (Forecast vs Capacidade Lags)...")
    df_futuro = pd.read_csv(caminho_futuro)
    
    if df_futuro.empty:
        logger.warning("Base do Futuro vazia. Nenhum intervalo projetado hoje.")
        return
        
    X = df_futuro[features]
    
    logger.info("3. Iniciando Redes de Árvores (Predição do Nível de Serviço)...")
    predicoes = modelo.predict(X)
    
    logger.info("4. Acionando SHAP Values (Cálculo Fino da Explicabilidade por Variável)...")
    shap_values = calcular_explicabilidade_shap(modelo, X)
    
    logger.info("5. Pivotando matriz de impacto multidimensional (Separando Ofensores/Pilares)...")
    tuplas_finais = processar_previsoes(df_futuro, predicoes, shap_values, features)
    
    # ATENÇÃO: Para habilitar a gravação, a Query DDL criada no passo anterior
    # deverá estar previamente executada no Microsoft SQL Server.
    salvar_no_banco(tuplas_finais)
    
    logger.info("Pipeline Finalizado! O BI já pode plugar sua base de forma leve.")
    
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
    main()
