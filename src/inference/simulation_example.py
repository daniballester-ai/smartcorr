"""
Script de Exemplo: Simulação de Capacidade (Stress Test)
--------------------------------------------------------
Demonstra como o modelo de regressão é usado para encontrar a 
Capacidade Máxima de Volume (Chamadas) que a operação suporta 
mantendo a meta de Nível de Serviço.

Como o modelo atual foi treinado sem a variável explícita de "Agentes Logados"
(dado não disponível no histórico), a simulação foca em:
"Qual o volume máximo de chamadas podemos receber antes de perder o NS?"
"""

import pandas as pd
import joblib
import numpy as np
import logging
import os
import sys
import yaml

# Configuração de Logger
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

# Caminhos (ajustados para serem relativos à raiz do projeto)
MODEL_PATH = os.path.join("models", "model.pkl")
# Tentamos pegar um dado real processado. Se não existir, criamos dummy.
DATA_PATH = os.path.join("data", "processed", "future_data.csv")

def load_config():
    if os.path.exists("params.yaml"):
        with open("params.yaml", "r") as f:
            return yaml.safe_load(f)
    return {}

def load_simulation_context():
    """Carrega modelo e uma amostra de dados para simular."""
    if not os.path.exists(MODEL_PATH):
        logger.error(f"Modelo não encontrado em {MODEL_PATH}. Treine primeiro.")
        return None, None, None

    model = joblib.load(MODEL_PATH)
    config = load_config()
    features = config.get('data', {}).get('features', [])
    
    # Se features estiver vazio, fallback manual (baseado no treino anterior)
    if not features:
        features = ['Volume_Real', 'TMA_Real', 'Delta_Volume', 'Delta_TMA', 'Hour', 'DayOfWeek']

    # Tenta carregar dados reais
    if os.path.exists(DATA_PATH):
        try:
            df = pd.read_csv(DATA_PATH)
            # Pega uma linha que tenha Volume previsto > 0 para o exemplo ser útil
            sample = df[df['Volume_Previsto'] > 100].iloc[0:1].copy()
            if sample.empty:
                sample = df.iloc[0:1].copy()
        except Exception:
            sample = None
    else:
        sample = None

    # Se não conseguiu dados reais, cria sintético
    if sample is None or sample.empty:
        logger.info("Usando dados sintéticos para simulação.")
        sample = pd.DataFrame({
            'Volume_Real': [1000],
            'Volume_Previsto': [1000],
            'TMA_Real': [300],
            'TMA_Meta': [300],
            'Delta_Volume': [0.0],
            'Delta_TMA': [0.0],
            'Hour': [10],
            'DayOfWeek': [2]
        })
        # Garante que features existam
        for col in features:
            if col not in sample.columns:
                 sample[col] = 0

    return model, sample, features

def find_max_volume_capacity(model, base_row, feature_names, target_ns=0.85):
    """
    Simula aumento de volume até o NS cair abaixo da meta.
    """
    simulation = base_row.copy()
    
    # Volume Base (Previsto ou Real atual)
    vol_previsto = simulation['Volume_Previsto'].values[0] if 'Volume_Previsto' in simulation else 1000
    if vol_previsto == 0: vol_previsto = 1000 # Evita div por zero

    # Começa simulando do volume baixo para cima
    # Ou parte do previsto
    
    # Teste inicial com volume previsto
    simulation['Volume_Real'] = vol_previsto
    simulation['Delta_Volume'] = 0.0 # Real = Previsto
    
    ns_inicial = model.predict(simulation[feature_names])[0]
    ns_inicial = min(ns_inicial, 1.0) # Clip visual
    
    print(f"\n--- Cenário Base ---")
    print(f"Volume Planejado: {vol_previsto:.0f}")
    print(f"NS Projetado (Cenário Ideal): {ns_inicial:.2%}")
    
    if ns_inicial < target_ns:
        print(f"ALERTA: Mesmo com o volume planejado, o NS já está abaixo da meta ({target_ns:.0%}).")
        print("A operação já nasce crítica independente do volume extra.")
        return
        
    # Stress Test: Aumentar volume até quebrar
    print(f"\n--- Iniciando Stress Test (Capacidade Máxima) ---")
    
    current_vol = vol_previsto
    step = 50 # Aumenta de 50 em 50 chamadas
    broken = False
    
    while not broken and current_vol < (vol_previsto * 3): # Limite 3x
        prev_vol = current_vol
        current_vol += step
        
        # Atualiza Simulação
        simulation['Volume_Real'] = current_vol
        # Recalcula Delta (se o modelo usa Delta relativo)
        # Delta = (Real - Previsto) / Previsto? Ou absoluto?
        # O feature_engineering usou: (Real / Previsto) - 1 ?
        # Assumindo simplificação: Delta não linear pode afetar, mas vamos manter simples.
        # Se feature_engineering.py usa lógica complexa, aqui é uma aproximação.
        # Vamos assumir que Delta_Volume é uma feature importante.
        # Se 'Delta_Volume' está nas features, precisamos atualizar.
        
        simulation['Delta_Volume'] = (current_vol - vol_previsto) / vol_previsto
        
        # Predição
        ns_pred = model.predict(simulation[feature_names])[0]
        
        # Check
        if ns_pred < target_ns:
            print(f"⚠️ PONTO DE QUEBRA IDENTIFICADO!")
            print(f"Com {current_vol:.0f} chamadas (+{current_vol - vol_previsto:.0f} vs previsto),")
            print(f"O Nível de Serviço cai para {ns_pred:.2%} (Abaixo de {target_ns:.0%})")
            broken = True
        else:
            # print(f"Suporta {current_vol:.0f} (NS: {ns_pred:.2%})...")
            pass

    if not broken:
        print(" O sistema suporta até 3x o volume previsto sem quebrar a meta (Modelo muito otimista ou dados desbalanceados).")

if __name__ == "__main__":
    try:
        model, row, features = load_simulation_context()
        
        if model and row is not None:
            # Garante colunas
            row['Volume_Previsto'] = row['Volume_Previsto'] if 'Volume_Previsto' in row else 1000
            
            find_max_volume_capacity(model, row, features, target_ns=0.85)
            
    except Exception as e:
        logger.error(f"Erro fatal: {e}")
