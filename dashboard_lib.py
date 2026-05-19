import glob
import json
import os
import re
import sys
import time
from datetime import datetime

import pandas as pd

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

DIRETORIO_BENCHMARK = "reports/benchmark"
ARQUIVO_NOMES_PROGRAMAS = "config/programs.csv"

PILARES = {
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
    "Drivers_Operacionais": [
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


def get_pilar_da_feature(feature_name: str) -> str:
    for pilar, vars_pilar in PILARES.items():
        if feature_name in vars_pilar:
            return pilar
    return "Outros"


def _carregar_nomes_programas() -> dict:
    caminho = os.path.join(os.path.dirname(os.path.abspath(__file__)), ARQUIVO_NOMES_PROGRAMAS)
    if not os.path.exists(caminho):
        return {}
    df = pd.read_csv(caminho, sep=";", header=None, names=["codigo", "nome"], dtype=str)
    nomes = {}
    for _, row in df.iterrows():
        cod = row["codigo"].strip()
        nome = row["nome"].strip()
        if cod and nome:
            nomes[cod] = nome
    return nomes


_NOMES_CACHE = None  # type: dict | None


def get_nome_programa(codigo) -> str:  # int or str
    global _NOMES_CACHE
    if _NOMES_CACHE is None:
        _NOMES_CACHE = _carregar_nomes_programas()
    return _NOMES_CACHE.get(str(codigo), "")


def _extrair_suffix(nome_arquivo: str) -> str:
    """Extrai o suffix de um nome de arquivo metricas_*.json ou benchmark_*.csv.

    Exemplos:
        metricas_7d.json        -> '7d'
        metricas_20260511_1430_7d.json -> '20260511_1430_7d'
        benchmark_7d.csv        -> '7d'
    """
    nome_sem_ext = nome_arquivo.rsplit(".", 1)[0]
    # Remove prefixo 'metricas_' ou 'benchmark_'
    for prefixo in ["metricas_", "benchmark_"]:
        if nome_sem_ext.startswith(prefixo):
            return nome_sem_ext[len(prefixo):]
    return nome_sem_ext


def list_benchmark_runs() -> pd.DataFrame:
    """Escaneia reports/benchmark/ por metricas_*.json e retorna DataFrame
    com metadados de todas as execuções disponíveis, ordenado por data descendente.
    """
    if not os.path.isdir(DIRETORIO_BENCHMARK):
        return pd.DataFrame(columns=["suffix", "data_execucao", "dias", "arquivo"])

    padrao = os.path.join(DIRETORIO_BENCHMARK, "metricas_*.json")
    arquivos = glob.glob(padrao)

    registros = []
    for caminho in sorted(arquivos, reverse=True):
        nome = os.path.basename(caminho)
        suffix = _extrair_suffix(nome)
        try:
            with open(caminho, "r", encoding="utf-8") as f:
                dados = json.load(f)
            metadata = dados.get("_metadata", {})
            data_exec = metadata.get("data_execucao", "") or _parse_timestamp_from_suffix(suffix) or "desconhecida"
            dias = metadata.get("dias_retroativos", _guess_dias(suffix))
            registros.append({
                "suffix": suffix,
                "data_execucao": data_exec,
                "dias": dias,
                "arquivo": caminho,
            })
        except (json.JSONDecodeError, KeyError):
            continue

    if not registros:
        return pd.DataFrame(columns=["suffix", "data_execucao", "dias", "arquivo"])

    df = pd.DataFrame(registros)
    df = df.sort_values("data_execucao", ascending=False).reset_index(drop=True)
    return df


def _guess_dias(suffix: str) -> int:
    """Tenta extrair número de dias de um suffix como '7d' ou '20260511_1430_7d'."""
    match = re.search(r"_(\d+)d$", suffix)
    if match:
        return int(match.group(1))
    match = re.match(r"^(\d+)d$", suffix)
    if match:
        return int(match.group(1))
    return 0


def _parse_timestamp_from_suffix(suffix: str) -> str:
    """Tenta extrair timestamp ISO de um suffix como '20260507_164441_7d'.

    Retorna string vazia se não conseguir parsear.
    """
    match = re.match(r"^(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})_", suffix)
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)} {match.group(4)}:{match.group(5)}:{match.group(6)}"
    return ""


def load_metrics(suffix: str) -> dict:
    """Carrega o JSON de métricas de uma execução específica."""
    caminho = os.path.join(DIRETORIO_BENCHMARK, f"metricas_{suffix}.json")
    if not os.path.exists(caminho):
        return {}
    with open(caminho, "r", encoding="utf-8") as f:
        return json.load(f)


def load_predictions_csv(suffix: str) -> pd.DataFrame:
    """Carrega o CSV de predições de uma execução específica."""
    caminho = os.path.join(DIRETORIO_BENCHMARK, f"benchmark_{suffix}.csv")
    if not os.path.exists(caminho):
        return pd.DataFrame()
    return pd.read_csv(caminho, parse_dates=["DataRef"])


def run_benchmark(dias: int, progress_callback=None) -> dict:
    """Executa o benchmark com timestamp para acumular histórico.

    Args:
        dias: Número de dias retroativos
        progress_callback: Função(progresso: int, mensagem: str)

    Returns:
        dict: Métricas calculadas
    """
    from run_benchmark import executar_benchmark

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = f"{timestamp}_{dias}d"

    return executar_benchmark(
        dias_retroativos=dias,
        progress_callback=progress_callback,
        suffix=suffix,
    )


def get_evolution_data() -> pd.DataFrame:
    """Cruza todos os JSONs de métricas e monta DataFrame de evolução temporal."""
    runs = list_benchmark_runs()
    if runs.empty:
        return pd.DataFrame()

    registros = []
    for _, row in runs.iterrows():
        dados = load_metrics(row["suffix"])
        if not dados:
            continue

        meta = dados.get("_metadata", {})
        data = meta.get("data_execucao", "") or _parse_timestamp_from_suffix(row["suffix"])
        dias = meta.get("dias_retroativos", 0) or _guess_dias(row["suffix"])

        registros.append({
            "data_execucao": data,
            "dias": dias,
            "suffix": row["suffix"],
            "MAE_SmartCorr": dados.get("smartcorr", {}).get("MAE"),
            "RMSE_SmartCorr": dados.get("smartcorr", {}).get("RMSE"),
            "R2_SmartCorr": dados.get("smartcorr", {}).get("R2"),
            "MAE_WFM": dados.get("erlang", {}).get("MAE"),
            "RMSE_WFM": dados.get("erlang", {}).get("RMSE"),
            "R2_WFM": dados.get("erlang", {}).get("R2"),
            "Uplift_MAE_pct": dados.get("uplift_mae_pct"),
            "total_intervalos": dados.get("total_intervalos"),
        })

    df = pd.DataFrame(registros)
    if not df.empty:
        df["data_execucao"] = pd.to_datetime(df["data_execucao"], errors="coerce")
        df = df.sort_values("data_execucao").reset_index(drop=True)
    return df


def get_programas_comuns() -> list:
    """Retorna lista de programas que aparecem em TODAS as execuções."""
    runs = list_benchmark_runs()
    progs_por_run = []
    for _, row in runs.iterrows():
        progs = get_programas_disponiveis(row["suffix"])
        progs_por_run.append(set(progs))
    if not progs_por_run:
        return []
    comuns = set.intersection(*progs_por_run)
    return sorted(comuns, key=int)


def get_evolution_data_por_programa() -> pd.DataFrame:
    """Monta DataFrame de evolução temporal por programa (cruzando todas as execuções)."""
    runs = list_benchmark_runs()
    if runs.empty:
        return pd.DataFrame()

    registros = []
    for _, row in runs.iterrows():
        dados = load_metrics(row["suffix"])
        if not dados:
            continue

        meta = dados.get("_metadata", {})
        data = meta.get("data_execucao", "") or _parse_timestamp_from_suffix(row["suffix"])
        dias = meta.get("dias_retroativos", 0) or _guess_dias(row["suffix"])
        por_programa = dados.get("por_programa", {})

        for prog, metrics in por_programa.items():
            registros.append({
                "data_execucao": data,
                "dias": dias,
                "suffix": row["suffix"],
                "programa": int(prog),
                "intervalos": metrics.get("intervalos", 0),
                "NS_Real_medio": metrics.get("NS_Real_medio"),
                "MAE_SmartCorr": metrics.get("MAE_SmartCorr"),
                "MAE_WFM": metrics.get("MAE_Erlang"),
                "RMSE_SmartCorr": metrics.get("RMSE_SmartCorr"),
                "R2_SmartCorr": metrics.get("R2_SmartCorr"),
                "Uplift_MAE_pct": metrics.get("Uplift_MAE_pct"),
            })

    df = pd.DataFrame(registros)
    if not df.empty:
        df["data_execucao"] = pd.to_datetime(df["data_execucao"], errors="coerce")
        df = df.sort_values("data_execucao").reset_index(drop=True)
    return df


def get_programas_disponiveis(suffix: str) -> list:
    """Retorna lista de programas disponíveis em uma execução."""
    dados = load_metrics(suffix)
    if not dados:
        return []
    prog = dados.get("por_programa", {})
    return sorted(prog.keys(), key=lambda x: int(x))


def load_shap_summary(run_suffix: str, programa: int) -> dict:
    """Carrega SHAP summary de um programa especifico.

    Args:
        run_suffix: Sufixo da execucao (ex: '20260507_164441_7d')
        programa: Codigo do programa

    Returns:
        dict: {feature_name: mean_abs_shap} ou dict vazio se nao encontrado
    """
    caminho = os.path.join(
        DIRETORIO_BENCHMARK,
        f"shap_summary_{run_suffix}_{programa}.json",
    )
    if not os.path.exists(caminho):
        return {}
    with open(caminho, "r", encoding="utf-8") as f:
        return json.load(f)


def load_shap_values(run_suffix: str, programa: int):
    """Carrega matriz SHAP e metadados para waterfall interativo.

    Args:
        run_suffix: Sufixo da execucao (ex: '20260507_164441_7d')
        programa: Codigo do programa

    Returns:
        tuple: (expected_value, features, shap_matrix, target_transformation) ou None se nao encontrado
    """
    import numpy as np
    npy_path = os.path.join(
        DIRETORIO_BENCHMARK,
        f"shap_values_{run_suffix}_{programa}.npy",
    )
    meta_path = os.path.join(
        DIRETORIO_BENCHMARK,
        f"shap_values_{run_suffix}_{programa}.json",
    )
    if not os.path.exists(npy_path) or not os.path.exists(meta_path):
        return None
    shap_matrix = np.load(npy_path)
    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)
    return meta["expected_value"], meta["features"], shap_matrix, meta.get("target_transformation", False)


def get_nome_legivel(suffix: str) -> str:
    """Converte suffix em nome legível para exibição.

    Formatos:
        '7d'                          -> 'Benchmark de 7 dias'
        '20260511_1430_7d'            -> 'Benchmark de 7 dias - 2026-05-11 14:30'
    """
    match = re.match(r"^(\d{8})_(\d{4})(?:\d{2})?_(\d+)d$", suffix)
    if match:
        data_raw = match.group(1)
        hora_raw = match.group(2)
        dias = match.group(3)
        data = f"{data_raw[:4]}-{data_raw[4:6]}-{data_raw[6:8]}"
        hora = f"{hora_raw[:2]}:{hora_raw[2:]}"
        return f"Benchmark de {dias} dias - {data} {hora}"
    match = re.match(r"^(\d+)d$", suffix)
    if match:
        return f"Benchmark de {match.group(1)} dias"
    return suffix
