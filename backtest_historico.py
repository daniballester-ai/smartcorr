import os
import pandas as pd
import numpy as np
import joblib
import yaml
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.metrics import mean_absolute_error, r2_score

def carregar_params():
    with open("params.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def run_backtest():
    print("=== INICIANDO BACKTEST HISTÓRICO ===")
    config = carregar_params()
    
    test_path = config["data"]["processed_test_path"]
    if not os.path.exists(test_path):
        print(f"Arquivo de teste não encontrado: {test_path}")
        return
        
    df = pd.read_csv(test_path)
    df["DataHora"] = pd.to_datetime(df["DataHora"])
    df = df.sort_values("DataHora")
    
    programas = config["data"]["programas"]
    target = config["data"]["target"]
    features = config["data"]["features"]
    limite_correcao = config["model"].get("limite_correcao_residuo", 0.15)
    
    os.makedirs("metrics/backtest", exist_ok=True)
    os.makedirs("images", exist_ok=True)
    
    resultados_completos = []

    for programa in programas:
        print(f"\n--- Processando Programa {programa} ---")
        model_path = f"models/model_{programa}.pkl"
        if not os.path.exists(model_path):
            print(f"Modelo não encontrado para o programa {programa}")
            continue
            
        modelo = joblib.load(model_path)
        
        df_prog = df[df["CodPrograma"] == programa].copy()
        if df_prog.empty:
            print(f"Sem dados de teste para o programa {programa}")
            continue
            
        # Garantir que todas as features existem
        for f in features:
            if f not in df_prog.columns:
                df_prog[f] = 0.0
                
        # Fazer predição (garantindo a ordem das features)
        features_modelo = getattr(modelo, "feature_names_in_", features)
        X = df_prog[features_modelo]
        
        pred_ns_direto = modelo.predict(X)
        
        df_prog["NS_Final_Previsto"] = np.clip(pred_ns_direto, 0.0, 1.0)
        df_prog["NS_Real"] = np.clip(df_prog[target], 0.0, 1.0)
        
        if "NS_Previsto_Erlang" in df_prog.columns:
            df_prog["NS_Previsto_Erlang"] = pd.to_numeric(df_prog["NS_Previsto_Erlang"], errors="coerce").fillna(0.0).clip(0, 1)
            
        # Calcular Métricas
        mae_erlang = mean_absolute_error(df_prog["NS_Real"], df_prog["NS_Previsto_Erlang"])
        mae_smartcorr = mean_absolute_error(df_prog["NS_Real"], df_prog["NS_Final_Previsto"])
        r2_smartcorr = r2_score(df_prog["NS_Real"], df_prog["NS_Final_Previsto"])
        
        uplift = ((mae_erlang - mae_smartcorr) / mae_erlang) * 100 if mae_erlang > 0 else 0
        
        print(f"Métricas do Backtest:")
        print(f"MAE Erlang: {mae_erlang:.4f}")
        print(f"MAE SmartCorr: {mae_smartcorr:.4f} (Melhoria de {uplift:.1f}%)")
        print(f"R² SmartCorr: {r2_smartcorr:.4f}")
        
        resultados_completos.append(df_prog)
        
        # Salvar gráfico dos últimos 7 dias (ou total se menor)
        data_corte = df_prog["DataHora"].max() - pd.Timedelta(days=7)
        df_plot = df_prog[df_prog["DataHora"] >= data_corte]
        
        plt.figure(figsize=(15, 6))
        plt.plot(df_plot["DataHora"], df_plot["NS_Real"], label="NS Real", color="black", linewidth=2)
        plt.plot(df_plot["DataHora"], df_plot["NS_Previsto_Erlang"], label="NS Erlang", color="red", linestyle="--", alpha=0.6)
        plt.plot(df_plot["DataHora"], df_plot["NS_Final_Previsto"], label="NS SmartCorr", color="blue", linewidth=2)
        
        plt.title(f"Backtest SmartCorr - Últimos 7 Dias (Programa {programa})")
        plt.xlabel("DataHora")
        plt.ylabel("Nível de Serviço (NS)")
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        
        caminho_imagem = f"images/backtest_{programa}.png"
        plt.savefig(caminho_imagem)
        print(f"Gráfico salvo em: {caminho_imagem}")
        
    if resultados_completos:
        df_final = pd.concat(resultados_completos)
        df_final.to_csv("metrics/backtest/resultados_historicos.csv", index=False)
        print("\nBacktest concluído! Resultados salvos em metrics/backtest/resultados_historicos.csv")

if __name__ == "__main__":
    run_backtest()
