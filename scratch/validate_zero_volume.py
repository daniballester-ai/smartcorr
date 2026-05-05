
import os
import sys
import joblib
import pandas as pd
import numpy as np
import yaml

# Adiciona o diretório raiz ao path para importar src
sys.path.append(os.getcwd())
from src.config.feature_registry import get_features_for_program

def load_config():
    with open("params.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def validate():
    config = load_config()
    programa = 589361
    model_path = f"models/model_{programa}.pkl"
    
    if not os.path.exists(model_path):
        print(f"ERRO: Modelo {model_path} não encontrado.")
        return

    print(f"--- Validando Volume Zero para Programa {programa} ---")
    modelo = joblib.load(model_path)
    
    # Obter features corretas do registry
    all_features_params = config['data']['features']
    features = get_features_for_program(programa, all_features_params)
    
    # Criar amostra de teste (Volume Zero)
    test_data = {feat: 0.0 for feat in features}
    test_data.update({
        'Vol_Previsto': 0,
        'HC_Previsto': 5,
        'Hora': 10,
        'DiaSemana': 1, # Nota: params.yaml tem Hora e DiaSemana no global
        'NS_Lag_1': 1.0,
        'Margem_Capacidade': 1.0, 
        'Indicador_Sufoco': 0.0
    })
    
    df_test = pd.DataFrame([test_data])
    
    # Garantir ordem das colunas
    df_test = df_test[features]
    
    # Predição do Resíduo
    residuo_predito = modelo.predict(df_test)[0]
    
    # No nosso pipeline, se Vol_Previsto = 0, o Erlang Baseline é 1.0
    ns_erlang_baseline = 1.0
    ns_final = np.clip(ns_erlang_baseline + residuo_predito, 0.0, 1.0)
    
    print(f"Resíduo Predito: {residuo_predito:.4f}")
    print(f"NS Erlang Baseline: {ns_erlang_baseline:.4f}")
    print(f"NS Final Calculado: {ns_final:.4f}")
    
    if abs(ns_final - 1.0) < 0.05:
        print("✅ SUCESSO: O modelo manteve o NS próximo a 100% para volume zero.")
    else:
        print(f"⚠️ AVISO: O modelo desviou de 100% ({ns_final:.2%}).")
        print("Isso indica que o modelo está penalizando o NS mesmo sem chamadas, talvez por correlação com Hora/HC.")

if __name__ == "__main__":
    validate()
