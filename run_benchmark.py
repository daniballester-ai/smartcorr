"""
SmartCorr - Benchmark de Avaliação Retroativa
==============================================
Script para gerar predições nos últimos N dias (onde já existem dados reais)
e comparar automaticamente com o NS_Real observado.

Uso:
    python run_benchmark.py                     # Últimos 7 dias (padrão)
    python run_benchmark.py --dias 14           # Últimos 14 dias
    python run_benchmark.py --dias 7 --salvar   # Salva resultados no banco

O script NÃO altera os dados de produção (FactSmartCorr_Previsao).
Os resultados são salvos em CSV e gráficos na pasta reports/benchmark/.
"""

import json
import logging
import os
import sys
import time
from argparse import ArgumentParser
from datetime import datetime, timedelta

import joblib
import numpy as np
import pandas as pd
import yaml

# Garantir que o diretório raiz esteja no path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

PILARES: dict = {
    "Volumetria": [
        "Vol_Previsto", "Desvio_Volume_Pct_Lag_1",
    ],
    "Pessoas": [
        "HC_Previsto", "ABS_Taxa_Daily", "Turnover_Taxa_Daily",
        "Ferias_Qtd_Daily", "Faltas_Qtd_Daily", "PerdaLog_Taxa_Daily",
        "NewHire_Pct_Daily", "AgentIssues_Taxa_Daily",
    ],
    "TMA": [
        "Tempo_AHT_Previsto_Total", "TME_Real_Avg_Lag_1", "Delta_TMA_Lag_1",
    ],
    "Saude_Operacional": [
        "Pressao_Prevista_Vol_HC", "Indicador_Sufoco",
        "Vol_Por_Agente", "Margem_Capacidade", "Ocupacao_Sintetica",
    ],
    "Contexto_Temporal": [
        "Hora", "DiaSemana", "Dia_Mes", "Semana_Mes",
        "Dia_Semana", "Is_Inicio_Fim_Mes", "Is_Segunda_Sexta",
    ],
    "Contexto_Operacional": [
        "Meta_Intervalo_SLA", "Meta_Intervalo_SLA_Canal",
    ],
}

# Configuração de Logs
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("SmartCorr_Benchmark")


def carregar_configuracoes() -> dict:
    """Carrega as configurações do arquivo params.yaml."""
    with open("params.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def extrair_dados_retroativos(config: dict, dias_retroativos: int) -> pd.DataFrame:
    """Extrai dados dos últimos N dias do banco de dados (com dados reais).

    Usa a mesma query de produção, mas com janela temporal ajustada
    para capturar apenas dados passados onde NS_Real já existe.

    Args:
        config: Configurações do params.yaml
        dias_retroativos: Quantidade de dias para trás a avaliar

    Returns:
        pd.DataFrame: Dados consolidados com valores reais
    """
    from src.data_loading.load_data import (
        load_queries,
        _build_programas_filter,
        _fetch_smartcorr_data,
        _fetch_perda_log_data,
        _merge_daily_data,
    )
    from src.database import get_connection

    consultas = load_queries(config["data"]["queries_file"])
    filtro_programas = _build_programas_filter(config["data"]["programas"])
    canal = config["data"].get("canal", 7)

    # Janela de dados: últimos (dias_retroativos + margem_lags) até hoje
    # A margem extra garante que os lags e médias móveis sejam calculados
    margem_lags = 15
    janela_total = dias_retroativos + margem_lags

    expressao_data_base = "GETDATE()"
    # Limitar ao passado: apenas dados até ontem (para garantir dados reais completos)
    limite_smartcorr = "AND [DataRef] < CAST(GETDATE() AS DATE)"
    limite_perda_log = "AND F.[Date] < CAST(GETDATE() AS DATE)"

    logger.info(
        f"Extraindo dados retroativos: últimos {janela_total} dias "
        f"(avaliação={dias_retroativos}d + margem_lags={margem_lags}d)"
    )

    engine = get_connection()
    try:
        df_smartcorr = _fetch_smartcorr_data(
            engine, consultas["smartcorr"], janela_total,
            expressao_data_base, limite_smartcorr,
            filtro_programas, canal,
        )

        df_perda_log = _fetch_perda_log_data(
            engine, consultas["perda_log"], janela_total,
            expressao_data_base, limite_perda_log,
            filtro_programas,
        )

        df = _merge_daily_data(df_smartcorr, df_perda_log)

        # Ordenar por data e intervalo
        colunas_ordenacao = [col for col in ["DataRef", "Intervalo"] if col in df.columns]
        if colunas_ordenacao:
            df = df.sort_values(by=colunas_ordenacao).reset_index(drop=True)

        return df

    finally:
        engine.dispose()


def processar_pipeline(df_bruto: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Executa os estágios de limpeza e engenharia de features.

    Args:
        df_bruto: DataFrame com dados brutos do banco
        config: Configurações do params.yaml

    Returns:
        pd.DataFrame: DataFrame com todas as features calculadas
    """
    from src.data_preprocessing.clean_data import clean
    from src.feature_engineering.build_features import build_features

    caminho_encoding = config["data"].get(
        "target_encoding_path", "models/target_encoding.json"
    )

    logger.info("Pipeline: Limpeza de dados...")
    # Forçar modo inference para não filtrar registros operacionais
    config_benchmark = config.copy()
    config_benchmark["data"] = config["data"].copy()
    config_benchmark["data"]["mode"] = "inference"
    df_limpo = clean(df_bruto, config_benchmark)

    logger.info("Pipeline: Engenharia de features...")
    df_features = build_features(df_limpo, encoding_path=caminho_encoding, modo="inferencia")

    return df_features


def filtrar_janela_avaliacao(
    df: pd.DataFrame, dias_retroativos: int
) -> pd.DataFrame:
    """Filtra apenas os registros da janela de avaliação (últimos N dias).

    Os registros anteriores à janela servem apenas para calcular lags
    e médias móveis, e são descartados após o cálculo das features.

    Args:
        df: DataFrame com features calculadas
        dias_retroativos: Quantidade de dias a avaliar

    Returns:
        pd.DataFrame: Apenas registros dentro da janela de avaliação
    """
    df["DataHora"] = pd.to_datetime(df["DataHora"])
    data_corte = pd.to_datetime(datetime.now().date()) - timedelta(days=dias_retroativos)

    df_janela = df[df["DataHora"] >= data_corte].copy()
    logger.info(
        f"Janela de avaliação: {data_corte.date()} até ontem. "
        f"Registros: {len(df_janela)}"
    )
    return df_janela


def gerar_predicoes(
    df: pd.DataFrame, config: dict,
    suffix: str = "", diretorio_saida: str = "reports/benchmark"
) -> pd.DataFrame:
    """Gera predições usando os modelos treinados para cada programa.

    Args:
        df: DataFrame com features na janela de avaliação
        config: Configurações do params.yaml

    Returns:
        pd.DataFrame: DataFrame com colunas NS_Real e NS_Previsto_SmartCorr
    """
    features_global = config["data"]["features"]
    diretorio_modelos = config["model"].get("models_dir", "models")
    transformacao_target = config["model"].get("target_transformation", False)
    target = config["data"].get("target", "NS_Real")

    # Verificar feature registry
    use_feature_registry = config["data"].get("use_feature_registry", False)
    HAS_FEATURE_REGISTRY = False
    if use_feature_registry:
        try:
            from src.config.feature_registry import get_features_for_program
            HAS_FEATURE_REGISTRY = True
        except ImportError:
            pass

    programas = sorted(df["CodPrograma"].unique())
    logger.info(f"Programas para benchmark: {list(programas)}")

    resultados_lista = []

    for programa in programas:
        caminho_modelo = os.path.join(diretorio_modelos, f"model_{programa}.pkl")

        if not os.path.exists(caminho_modelo):
            logger.warning(f"Programa {programa}: modelo não encontrado. Pulando.")
            continue

        df_prog = df[df["CodPrograma"] == programa].copy()
        if df_prog.empty:
            continue

        modelo = joblib.load(caminho_modelo)

        # Carregar encoding per-programa
        dir_encodings = config["data"].get("target_encoding_dir", "models/encodings/")
        caminho_enc = os.path.join(dir_encodings, f"target_encoding_{programa}.json")
        if os.path.exists(caminho_enc):
            with open(caminho_enc, "r", encoding="utf-8") as f:
                dados_enc = json.load(f)
            df_prog["Programa_Target_Enc"] = float(dados_enc["encoding"])

        # Determinar features
        if HAS_FEATURE_REGISTRY:
            features_prog = get_features_for_program(programa, features_global)
        else:
            features_prog = features_global

        # Preparar X conforme o modelo espera
        if hasattr(modelo, "feature_names_in_"):
            expected = list(modelo.feature_names_in_)
            disponveis = [f for f in expected if f in df_prog.columns]
            X = df_prog[disponveis]
        else:
            X = df_prog[features_prog]

        # Predição
        predicoes_trans = modelo.predict(X)

        if transformacao_target and target != "NS_Residuo":
            predicoes = 1.0 - np.expm1(predicoes_trans)
        else:
            predicoes = predicoes_trans

        # Pós-processamento: Vol_Previsto == 0 → NS = 0
        vol_previsto = df_prog["Vol_Previsto"].values
        predicoes = np.where(vol_previsto == 0, 0.0, predicoes)
        predicoes = np.clip(predicoes, 0.0, 1.0)

        df_prog["NS_Previsto_SmartCorr"] = predicoes

        # Calcular Impacto_Pilar via SHAP (vectorized)
        try:
            import shap
            features_shap = disponveis if hasattr(modelo, "feature_names_in_") else features_prog
            X_shap = df_prog[features_shap]
            explainer = shap.TreeExplainer(modelo)
            shap_values = explainer.shap_values(X_shap)

            for pilar_nome, vars_pilar in PILARES.items():
                col_name = f"Impacto_Pilar_{pilar_nome}"
                indices = [i for i, f in enumerate(features_shap) if f in vars_pilar]
                if indices:
                    df_prog[col_name] = shap_values[:, indices].sum(axis=1)
                else:
                    df_prog[col_name] = 0.0

            # Contexto = Contexto_Temporal + Contexto_Operacional
            ctx_vars = PILARES.get("Contexto_Temporal", []) + PILARES.get("Contexto_Operacional", [])
            ctx_indices = [i for i, f in enumerate(features_shap) if f in ctx_vars]
            if ctx_indices:
                df_prog["Impacto_Pilar_Contexto"] = shap_values[:, ctx_indices].sum(axis=1)
            else:
                df_prog["Impacto_Pilar_Contexto"] = 0.0

            # Calcular Ofensores e Impulsionadores (Top 3 SHAP)
            feat_to_pilar = {}
            for p, feats in PILARES.items():
                for f in feats:
                    feat_to_pilar[f] = p

            ofensor_data = {r: {"nome": [], "pilar": [], "impacto": []} for r in range(3)}
            imp_data = {r: {"nome": [], "pilar": [], "impacto": []} for r in range(3)}

            for i in range(len(df_prog)):
                vals = dict(zip(features_shap, shap_values[i]))
                sorted_items = sorted(vals.items(), key=lambda x: abs(x[1]), reverse=True)
                ofensores = []
                impulsionadores = []
                for feat, val in sorted_items:
                    p_desc = feat_to_pilar.get(feat, "Outros")
                    if val < -0.001 and len(ofensores) < 3:
                        ofensores.append((feat, p_desc, val))
                    elif val > 0.001 and len(impulsionadores) < 3:
                        impulsionadores.append((feat, p_desc, val))
                while len(ofensores) < 3:
                    ofensores.append(("Sem Impacto Relevante", "N/A", 0.0))
                while len(impulsionadores) < 3:
                    impulsionadores.append(("Sem Impacto Relevante", "N/A", 0.0))
                for r in range(3):
                    ofensor_data[r]["nome"].append(ofensores[r][0])
                    ofensor_data[r]["pilar"].append(ofensores[r][1])
                    ofensor_data[r]["impacto"].append(ofensores[r][2])
                    imp_data[r]["nome"].append(impulsionadores[r][0])
                    imp_data[r]["pilar"].append(impulsionadores[r][1])
                    imp_data[r]["impacto"].append(impulsionadores[r][2])

            for r in range(3):
                df_prog[f"Ofensor_{r+1}_Nome"] = ofensor_data[r]["nome"]
                df_prog[f"Ofensor_{r+1}_Pilar"] = ofensor_data[r]["pilar"]
                df_prog[f"Ofensor_{r+1}_Impacto"] = ofensor_data[r]["impacto"]
                df_prog[f"Impulsionador_{r+1}_Nome"] = imp_data[r]["nome"]
                df_prog[f"Impulsionador_{r+1}_Pilar"] = imp_data[r]["pilar"]
                df_prog[f"Impulsionador_{r+1}_Impacto"] = imp_data[r]["impacto"]

            # Salvar SHAP summary (importancia media absoluta por feature)
            try:
                mean_abs_shap = np.abs(shap_values).mean(axis=0).tolist()
                shap_summary = dict(zip(features_shap, mean_abs_shap))
                caminho_summary = os.path.join(
                    diretorio_saida,
                    f"shap_summary_{suffix}_{programa}.json",
                )
                with open(caminho_summary, "w", encoding="utf-8") as f:
                    json.dump(shap_summary, f, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.warning(f"  Programa {programa}: erro ao salvar SHAP summary: {e}")

            # Salvar SHAP values para waterfall interativo
            try:
                caminho_shap_npy = os.path.join(
                    diretorio_saida,
                    f"shap_values_{suffix}_{programa}.npy",
                )
                np.save(caminho_shap_npy, shap_values)
                caminho_shap_meta = os.path.join(
                    diretorio_saida,
                    f"shap_values_{suffix}_{programa}.json",
                )
                with open(caminho_shap_meta, "w", encoding="utf-8") as f:
                    json.dump({
                        "features": features_shap,
                        "expected_value": float(explainer.expected_value),
                        "target_transformation": transformacao_target,
                    }, f, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.warning(f"  Programa {programa}: erro ao salvar SHAP values: {e}")

        except Exception:
            logger.warning(
                f"  Programa {programa}: SHAP indisponivel. "
                "Impacto_Pilar preenchido com 0."
            )
            for col_name in [
                "Impacto_Pilar_Volumetria", "Impacto_Pilar_Pessoas",
                "Impacto_Pilar_TMA", "Impacto_Pilar_Saude",
                "Impacto_Pilar_Contexto",
            ]:
                df_prog[col_name] = 0.0
            for r in range(3):
                df_prog[f"Ofensor_{r+1}_Nome"] = "SHAP N/A"
                df_prog[f"Ofensor_{r+1}_Pilar"] = "N/A"
                df_prog[f"Ofensor_{r+1}_Impacto"] = 0.0
                df_prog[f"Impulsionador_{r+1}_Nome"] = "SHAP N/A"
                df_prog[f"Impulsionador_{r+1}_Pilar"] = "N/A"
                df_prog[f"Impulsionador_{r+1}_Impacto"] = 0.0

        resultados_lista.append(df_prog)

        logger.info(
            f"  Programa {programa}: {len(df_prog)} intervalos. "
            f"NS médio previsto={np.mean(predicoes):.4f}, "
            f"NS médio real={df_prog['NS_Real'].mean():.4f}"
        )

    if not resultados_lista:
        logger.error("Nenhuma predição gerada para nenhum programa.")
        return pd.DataFrame()

    return pd.concat(resultados_lista, ignore_index=True)


def calcular_metricas(df: pd.DataFrame) -> dict:
    """Calcula métricas de avaliação comparando predição vs real.

    Args:
        df: DataFrame com colunas NS_Real, NS_Previsto_SmartCorr e NS_Previsto_Erlang

    Returns:
        dict: Dicionário com métricas globais e por programa
    """
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

    # Filtrar apenas intervalos operacionais (Vol_Real > 0)
    df_operacional = df[df["Vol_Real"] > 0].copy()

    if df_operacional.empty:
        logger.warning("Nenhum registro operacional encontrado para calcular métricas.")
        return {}

    real = df_operacional["NS_Real"]
    previsto_sc = df_operacional["NS_Previsto_SmartCorr"]

    # NS Erlang como baseline
    if "NS_Previsto_Erlang" in df_operacional.columns:
        previsto_erlang = pd.to_numeric(
            df_operacional["NS_Previsto_Erlang"], errors="coerce"
        ).fillna(0.0).clip(0, 1)
    else:
        previsto_erlang = pd.Series(0.0, index=df_operacional.index)

    # --- Métricas Globais ---
    metricas_globais = {
        "total_intervalos": len(df_operacional),
        "smartcorr": {
            "MAE": mean_absolute_error(real, previsto_sc),
            "RMSE": np.sqrt(mean_squared_error(real, previsto_sc)),
            "R2": r2_score(real, previsto_sc),
        },
        "erlang": {
            "MAE": mean_absolute_error(real, previsto_erlang),
            "RMSE": np.sqrt(mean_squared_error(real, previsto_erlang)),
            "R2": r2_score(real, previsto_erlang),
        },
    }

    # Uplift (melhoria do SmartCorr sobre o Erlang)
    mae_erlang = metricas_globais["erlang"]["MAE"]
    mae_sc = metricas_globais["smartcorr"]["MAE"]
    metricas_globais["uplift_mae_pct"] = (
        ((mae_erlang - mae_sc) / mae_erlang * 100) if mae_erlang > 0 else 0
    )

    # --- Métricas por Programa ---
    metricas_por_programa = {}
    for programa in sorted(df_operacional["CodPrograma"].unique()):
        df_prog = df_operacional[df_operacional["CodPrograma"] == programa]
        real_prog = df_prog["NS_Real"]
        sc_prog = df_prog["NS_Previsto_SmartCorr"]
        erlang_prog = pd.to_numeric(
            df_prog.get("NS_Previsto_Erlang", 0), errors="coerce"
        ).fillna(0.0).clip(0, 1)

        mae_erlang_prog = mean_absolute_error(real_prog, erlang_prog)
        mae_sc_prog = mean_absolute_error(real_prog, sc_prog)
        rmse_erlang_prog = np.sqrt(mean_squared_error(real_prog, erlang_prog))
        rmse_sc_prog = np.sqrt(mean_squared_error(real_prog, sc_prog))

        prog_dict = {
            "intervalos": len(df_prog),
            "NS_Real_medio": float(real_prog.mean()),
            "NS_SmartCorr_medio": float(sc_prog.mean()),
            "NS_WFM_medio": float(erlang_prog.mean()),
            "MAE_SmartCorr": mae_sc_prog,
            "MAE_Erlang": mae_erlang_prog,
            "RMSE_SmartCorr": rmse_sc_prog,
            "RMSE_Erlang": rmse_erlang_prog,
            "R2_SmartCorr": r2_score(real_prog, sc_prog) if len(real_prog) > 1 else 0,
            "Uplift_MAE_pct": (
                ((mae_erlang_prog - mae_sc_prog) / mae_erlang_prog * 100)
                if mae_erlang_prog > 0
                else 0
            ),
        }
        for pilar in ["Volumetria", "Pessoas", "TMA", "Saude", "Contexto"]:
            col = f"Impacto_Pilar_{pilar}"
            if col in df_prog.columns:
                prog_dict[col] = float(df_prog[col].mean())
        metricas_por_programa[int(programa)] = prog_dict

    metricas_globais["por_programa"] = metricas_por_programa
    return metricas_globais


def gerar_graficos(df: pd.DataFrame, diretorio_saida: str) -> list[str]:
    """Gera gráficos de comparação Real vs Predição por programa.

    Args:
        df: DataFrame com NS_Real e NS_Previsto_SmartCorr
        diretorio_saida: Diretório para salvar os gráficos

    Returns:
        list[str]: Caminhos dos gráficos gerados
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        logger.warning("matplotlib não disponível. Gráficos não serão gerados.")
        return []

    os.makedirs(diretorio_saida, exist_ok=True)
    caminhos_graficos = []

    df_operacional = df[df["Vol_Real"] > 0].copy()
    df_operacional["DataHora"] = pd.to_datetime(df_operacional["DataHora"])

    programas = sorted(df_operacional["CodPrograma"].unique())

    for programa in programas:
        df_prog = df_operacional[df_operacional["CodPrograma"] == programa].sort_values("DataHora")

        if df_prog.empty:
            continue

        fig, ax = plt.subplots(figsize=(16, 6))

        ax.plot(
            df_prog["DataHora"], df_prog["NS_Real"],
            label="NS Real", color="black", linewidth=1.5, alpha=0.8,
        )

        if "NS_Previsto_Erlang" in df_prog.columns:
            erlang = pd.to_numeric(df_prog["NS_Previsto_Erlang"], errors="coerce").fillna(0)
            ax.plot(
                df_prog["DataHora"], erlang,
                label="NS WFM", color="red", linestyle="--", alpha=0.5,
            )

        ax.plot(
            df_prog["DataHora"], df_prog["NS_Previsto_SmartCorr"],
            label="NS SmartCorr", color="#2196F3", linewidth=1.5,
        )

        ax.set_title(f"Benchmark SmartCorr - Programa {programa}", fontsize=14, fontweight="bold")
        ax.set_xlabel("Data/Hora")
        ax.set_ylabel("Nível de Serviço (NS)")
        ax.legend(loc="lower left")
        ax.grid(True, alpha=0.3)
        ax.set_ylim(-0.05, 1.05)

        plt.tight_layout()
        caminho = os.path.join(diretorio_saida, f"benchmark_{programa}.png")
        fig.savefig(caminho, dpi=100)
        plt.close(fig)

        caminhos_graficos.append(caminho)
        logger.info(f"Gráfico salvo: {caminho}")

    return caminhos_graficos


def imprimir_relatorio(metricas: dict, dias: int) -> None:
    """Imprime relatório formatado no console.

    Args:
        metricas: Dicionário de métricas calculadas
        dias: Dias retroativos avaliados
    """
    print("\n" + "=" * 70)
    print(f"  BENCHMARK SMARTCORR - ÚLTIMOS {dias} DIAS")
    print(f"  Data da execução: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("=" * 70)

    print(f"\n  Total de intervalos avaliados: {metricas['total_intervalos']}")
    print(f"\n  {'Métrica':<20} {'SmartCorr':>12} {'WFM':>12} {'Uplift':>12}")
    print(f"  {'-'*56}")

    sc = metricas["smartcorr"]
    er = metricas["erlang"]

    print(f"  {'MAE':<20} {sc['MAE']:>12.4f} {er['MAE']:>12.4f} {metricas['uplift_mae_pct']:>+11.1f}%")
    print(f"  {'RMSE':<20} {sc['RMSE']:>12.4f} {er['RMSE']:>12.4f}")
    print(f"  {'R²':<20} {sc['R2']:>12.4f} {er['R2']:>12.4f}")

    print(f"\n  {'DETALHAMENTO POR PROGRAMA':^56}")
    print(f"  {'-'*70}")
    print(f"  {'Programa':<12} {'N':>6} {'NS Real':>8} {'MAE SC':>8} {'MAE WFM':>8} {'R² SC':>8} {'Uplift':>8}")
    print(f"  {'-'*70}")

    for programa, m in sorted(metricas["por_programa"].items()):
        print(
            f"  {programa:<12} {m['intervalos']:>6} {m['NS_Real_medio']:>8.3f} "
            f"{m['MAE_SmartCorr']:>8.4f} {m['MAE_Erlang']:>8.4f} "
            f"{m['R2_SmartCorr']:>8.4f} {m['Uplift_MAE_pct']:>+7.1f}%"
        )

    print("=" * 70 + "\n")


def executar_benchmark(
    dias_retroativos: int = 7,
    salvar_banco: bool = False,
    progress_callback=None,
    suffix: str = None,
) -> dict:
    """Executa o benchmark completo com suporte a progresso e histórico.

    Args:
        dias_retroativos: Quantidade de dias para trás a avaliar
        salvar_banco: Se True, salva resultados no banco (tabela separada)
        progress_callback: Função opcional (progresso: int, mensagem: str)
        suffix: Sufixo para nomes de arquivo. Se None, usa '{dias}d'

    Returns:
        dict: Métricas calculadas
    """
    logger.info(f"=== BENCHMARK SMARTCORR: ÚLTIMOS {dias_retroativos} DIAS ===")
    if suffix is None:
        suffix = f"{dias_retroativos}d"

    config = carregar_configuracoes()
    diretorio_saida = "reports/benchmark"
    os.makedirs(diretorio_saida, exist_ok=True)

    # 1. Extrair dados retroativos do banco
    logger.info("--- Etapa 1/5: Extração de dados retroativos ---")
    if progress_callback:
        progress_callback(5, "Extraindo dados retroativos do banco...")
    df_bruto = extrair_dados_retroativos(config, dias_retroativos)

    if df_bruto.empty:
        msg = "Nenhum dado retornado do banco."
        logger.error(msg)
        if progress_callback:
            progress_callback(100, f"Erro: {msg}")
        return {}

    # 2. Processar pipeline (limpeza + features)
    logger.info("--- Etapa 2/5: Pipeline de processamento ---")
    if progress_callback:
        progress_callback(25, "Processando pipeline (limpeza + features)...")
    df_processado = processar_pipeline(df_bruto, config)

    if df_processado is None or df_processado.empty:
        msg = "Pipeline retornou DataFrame vazio."
        logger.error(msg)
        if progress_callback:
            progress_callback(100, f"Erro: {msg}")
        return {}

    # 3. Filtrar apenas a janela de avaliação
    logger.info("--- Etapa 3/5: Filtrar janela de avaliação ---")
    if progress_callback:
        progress_callback(45, "Filtrando janela de avaliação...")
    df_avaliacao = filtrar_janela_avaliacao(df_processado, dias_retroativos)

    # 4. Gerar predições
    logger.info("--- Etapa 4/5: Gerando predições retroativas ---")
    if progress_callback:
        progress_callback(60, "Gerando predições por programa...")
    df_resultado = gerar_predicoes(df_avaliacao, config, suffix=suffix, diretorio_saida=diretorio_saida)

    if df_resultado.empty:
        msg = "Nenhuma predição gerada."
        logger.error(msg)
        if progress_callback:
            progress_callback(100, f"Erro: {msg}")
        return {}

    # 5. Calcular métricas e gerar relatório
    logger.info("--- Etapa 5/5: Calculando métricas e gerando relatório ---")
    if progress_callback:
        progress_callback(85, "Calculando métricas e gerando gráficos...")
    metricas = calcular_metricas(df_resultado)

    if not metricas:
        return {}

    # Salvar resultados em CSV
    caminho_csv = os.path.join(diretorio_saida, f"benchmark_{suffix}.csv")
    colunas_saida = [
        "DataRef", "Intervalo", "CodPrograma", "Canal",
        "Vol_Real", "Vol_Previsto", "HC_Previsto",
        "NS_Real", "NS_Previsto_WFM", "NS_Previsto_SmartCorr",
        "Impacto_Pilar_Volumetria", "Impacto_Pilar_Pessoas", "Impacto_Pilar_TMA",
        "Impacto_Pilar_Saude", "Impacto_Pilar_Contexto",
        "Ofensor_1_Nome", "Ofensor_1_Pilar", "Ofensor_1_Impacto",
        "Ofensor_2_Nome", "Ofensor_2_Pilar", "Ofensor_2_Impacto",
        "Ofensor_3_Nome", "Ofensor_3_Pilar", "Ofensor_3_Impacto",
        "Impulsionador_1_Nome", "Impulsionador_1_Pilar", "Impulsionador_1_Impacto",
        "Impulsionador_2_Nome", "Impulsionador_2_Pilar", "Impulsionador_2_Impacto",
        "Impulsionador_3_Nome", "Impulsionador_3_Pilar", "Impulsionador_3_Impacto",
    ]
    df_csv = df_resultado.rename(columns={"NS_Previsto_Erlang": "NS_Previsto_WFM"})
    colunas_existentes = [c for c in colunas_saida if c in df_csv.columns]
    df_csv[colunas_existentes].to_csv(caminho_csv, index=False)
    logger.info(f"Resultados salvos em: {caminho_csv}")

    # Adicionar metadata da execução no JSON
    metricas["_metadata"] = {
        "data_execucao": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "timestamp": datetime.now().strftime("%Y%m%d_%H%M%S"),
        "dias_retroativos": dias_retroativos,
        "suffix": suffix,
    }

    # Salvar métricas em JSON
    caminho_metricas = os.path.join(diretorio_saida, f"metricas_{suffix}.json")
    with open(caminho_metricas, "w", encoding="utf-8") as f:
        json.dump(metricas, f, indent=2, ensure_ascii=False)
    logger.info(f"Métricas salvas em: {caminho_metricas}")

    # Gerar gráficos
    if progress_callback:
        progress_callback(95, "Gerando gráficos...")
    gerar_graficos(df_resultado, diretorio_saida)

    # Imprimir relatório no console
    imprimir_relatorio(metricas, dias_retroativos)

    logger.info("=== BENCHMARK FINALIZADO COM SUCESSO ===")
    if progress_callback:
        progress_callback(100, "Benchmark concluído com sucesso!")

    return metricas


def main(dias_retroativos: int = 7, salvar_banco: bool = False) -> dict:
    """Wrapper CLI. Mantém compatibilidade com chamadas externas."""
    return executar_benchmark(
        dias_retroativos=dias_retroativos,
        salvar_banco=salvar_banco,
    )


if __name__ == "__main__":
    analisador = ArgumentParser(
        description="SmartCorr - Benchmark de Avaliação Retroativa"
    )
    analisador.add_argument(
        "--dias", type=int, default=7,
        help="Quantidade de dias retroativos para avaliar (padrão: 7)",
    )
    analisador.add_argument(
        "--salvar", action="store_true",
        help="Salvar resultados no banco de dados (tabela separada)",
    )

    argumentos = analisador.parse_args()
    main(dias_retroativos=argumentos.dias, salvar_banco=argumentos.salvar)
