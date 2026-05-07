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
from argparse import ArgumentParser
from datetime import datetime, timedelta

import joblib
import numpy as np
import pandas as pd
import yaml

# Garantir que o diretório raiz esteja no path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

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
    df: pd.DataFrame, config: dict
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

        metricas_por_programa[int(programa)] = {
            "intervalos": len(df_prog),
            "NS_Real_medio": float(real_prog.mean()),
            "MAE_SmartCorr": mae_sc_prog,
            "MAE_Erlang": mae_erlang_prog,
            "R2_SmartCorr": r2_score(real_prog, sc_prog) if len(real_prog) > 1 else 0,
            "Uplift_MAE_pct": (
                ((mae_erlang_prog - mae_sc_prog) / mae_erlang_prog * 100)
                if mae_erlang_prog > 0
                else 0
            ),
        }

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


def main(dias_retroativos: int = 7, salvar_banco: bool = False) -> dict:
    """Executa o benchmark completo.

    Args:
        dias_retroativos: Quantidade de dias para trás a avaliar
        salvar_banco: Se True, salva resultados no banco (tabela separada)

    Returns:
        dict: Métricas calculadas
    """
    logger.info(f"=== BENCHMARK SMARTCORR: ÚLTIMOS {dias_retroativos} DIAS ===")

    config = carregar_configuracoes()
    diretorio_saida = "reports/benchmark"
    os.makedirs(diretorio_saida, exist_ok=True)

    # 1. Extrair dados retroativos do banco
    logger.info("--- Etapa 1/5: Extração de dados retroativos ---")
    df_bruto = extrair_dados_retroativos(config, dias_retroativos)

    if df_bruto.empty:
        logger.error("Nenhum dado retornado do banco. Verifique a conexão e os filtros.")
        return {}

    # 2. Processar pipeline (limpeza + features)
    logger.info("--- Etapa 2/5: Pipeline de processamento ---")
    df_processado = processar_pipeline(df_bruto, config)

    if df_processado is None or df_processado.empty:
        logger.error("Pipeline retornou DataFrame vazio.")
        return {}

    # 3. Filtrar apenas a janela de avaliação
    logger.info("--- Etapa 3/5: Filtrar janela de avaliação ---")
    df_avaliacao = filtrar_janela_avaliacao(df_processado, dias_retroativos)

    # 4. Gerar predições
    logger.info("--- Etapa 4/5: Gerando predições retroativas ---")
    df_resultado = gerar_predicoes(df_avaliacao, config)

    if df_resultado.empty:
        logger.error("Nenhuma predição gerada.")
        return {}

    # 5. Calcular métricas e gerar relatório
    logger.info("--- Etapa 5/5: Calculando métricas e gerando relatório ---")
    metricas = calcular_metricas(df_resultado)

    if not metricas:
        return {}

    # Salvar resultados em CSV
    caminho_csv = os.path.join(diretorio_saida, f"benchmark_{dias_retroativos}d.csv")
    colunas_saida = [
        "DataRef", "Intervalo", "CodPrograma", "Canal",
        "Vol_Real", "Vol_Previsto", "HC_Previsto",
        "NS_Real", "NS_Previsto_WFM", "NS_Previsto_SmartCorr",
    ]
    df_csv = df_resultado.rename(columns={"NS_Previsto_Erlang": "NS_Previsto_WFM"})
    colunas_existentes = [c for c in colunas_saida if c in df_csv.columns]
    df_csv[colunas_existentes].to_csv(caminho_csv, index=False)
    logger.info(f"Resultados salvos em: {caminho_csv}")

    # Salvar métricas em JSON
    caminho_metricas = os.path.join(diretorio_saida, f"metricas_{dias_retroativos}d.json")
    with open(caminho_metricas, "w", encoding="utf-8") as f:
        json.dump(metricas, f, indent=2, ensure_ascii=False)
    logger.info(f"Métricas salvas em: {caminho_metricas}")

    # Gerar gráficos
    gerar_graficos(df_resultado, diretorio_saida)

    # Imprimir relatório no console
    imprimir_relatorio(metricas, dias_retroativos)

    logger.info("=== BENCHMARK FINALIZADO COM SUCESSO ===")
    return metricas


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
