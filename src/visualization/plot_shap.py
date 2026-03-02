import pandas as pd
import xgboost as xgb
import shap
import matplotlib.pyplot as plt
import joblib
import yaml
import os

# Adicionar compatibilidade caso o matplotlib quebre em servidores sem tela
import matplotlib
matplotlib.use('Agg')

def main():
    print("Iniciando geração de Gráficos SHAP para a Diretoria...")

    # 1. Carregar Configurações
    with open("params.yaml", "r", encoding='utf-8') as f:
        config = yaml.safe_load(f)

    # 2. Criar pasta para os relatórios/gráficos caso não exista
    output_dir = "reports/figures"
    os.makedirs(output_dir, exist_ok=True)

    # 3. Carregar o Modelo e os Dados de Treino
    modelo = joblib.load(config['model']['path'])
    features = config['data']['features']
    
    df_train = pd.read_csv(config['data']['processed_train_path'])
    X = df_train[features]

    print(f"Modelo e Dados ({len(X)} linhas) carregados. Calculando SHAP Values matemáticos...")

    # 4. Iniciar o Explainer do SHAP
    # Pegamos uma amostra de 1000 linhas se a base for muito grande para não demorar muito na plotagem
    X_sample = X.sample(n=min(1000, len(X)), random_state=42)
    explainer = shap.TreeExplainer(modelo)
    shap_values = explainer(X_sample)

    # =========================================================================
    # GRÁFICO 1: O "BEE SWARM" (Resumo Global de Impacto)
    # Mostra CLARAMENTE como Volumetria alta puxa pra esquerda (vermelho), etc.
    # =========================================================================
    plt.figure(figsize=(12, 8))
    shap.summary_plot(shap_values, X_sample, show=False)
    plt.title("Visão Diretiva: O que mais impacta o Nível de Serviço na Operação?", fontsize=14, pad=20)
    plt.tight_layout()
    caminho_grafico_1 = os.path.join(output_dir, "01_SHAP_Resumo_Global.png")
    plt.savefig(caminho_grafico_1, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"✅ Gráfico Global Salvo em: {caminho_grafico_1}")

    # =========================================================================
    # GRÁFICO 2: O "WATERFALL" (O Raio-X de uma Crise Específica)
    # Vamos achar a linha no X_sample onde a predição foi a PIOR de todas
    # =========================================================================
    predicoes = modelo.predict(X_sample)
    idx_pior_cenario = predicoes.argmin() # O índice do menor nível de serviço previsto

    plt.figure(figsize=(10, 6))
    shap.waterfall_plot(shap_values[idx_pior_cenario], show=False)
    plt.title(f"Autópsia de uma Crise: Por que este intervalo despencou para {predicoes[idx_pior_cenario]*100:.1f}% ?", fontsize=14, pad=20)
    plt.tight_layout()
    caminho_grafico_2 = os.path.join(output_dir, "02_SHAP_Cachoeira_Crise.png")
    plt.savefig(caminho_grafico_2, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"✅ Gráfico de Autópsia (Crise) Salvo em: {caminho_grafico_2}")

    # =========================================================================
    # GRÁFICO 3: O "WATERFALL" (O Raio-X de uma Hora Perfeita)
    # Vamos achar a linha onde a predição foi maravilhosa
    # =========================================================================
    idx_melhor_cenario = predicoes.argmax()

    plt.figure(figsize=(10, 6))
    shap.waterfall_plot(shap_values[idx_melhor_cenario], show=False)
    plt.title(f"A Anatomia do Sucesso: Por que este intervalo operou em {predicoes[idx_melhor_cenario]*100:.1f}% ?", fontsize=14, pad=20)
    plt.tight_layout()
    caminho_grafico_3 = os.path.join(output_dir, "03_SHAP_Cachoeira_Sucesso.png")
    plt.savefig(caminho_grafico_3, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"✅ Gráfico de Autópsia (Sucesso) Salvo em: {caminho_grafico_3}")

    print("\nTodos os relatórios visuais foram gerados com sucesso para o PowerPoint da reunião!")

if __name__ == "__main__":
    main()
