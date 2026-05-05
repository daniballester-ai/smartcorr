"""
Feature Registry - Controle granular de features por programa.

Estrutura:
- global: features sempre inclusas em todos os programas
- optional: features com lista de programas que devem usá-las (None = todos)
- exclude: features explicitamente excluídas por programa

用法:
    from src.config.feature_registry import get_features_for_program
    features = get_features_for_program(589361)
"""

FEATURE_REGISTRY = {
    "global": [
        "Hora",
        "DiaSemana",
        "Vol_Previsto",
        "HC_Previsto",
        "Tempo_AHT_Previsto_Total",
        "ABS_Taxa_Daily",
        "TME_Real_Avg_Lag_1",
        "Desvio_Volume_Pct_Lag_1",
        "Delta_TMA_Lag_1",
        "Pressao_Prevista_Vol_HC",
        "Indicador_Sufoco",
        "Vol_Por_Agente",
        "Margem_Capacidade",
        "Ocupacao_Sintetica",
        "PerdaLog_Taxa_Daily",
        "NS_Media_Movel_3",
        "NS_Media_Movel_6",
        "NS_Std_Movel_6",
        "Delta_Aceleracao_NS",
        "Is_Horario_Pico",
    ],
    "optional": {
        "Turnover_Taxa_Daily": None,
        "Ferias_Qtd_Daily": None,
        "Faltas_Qtd_Daily": None,
        "NewHire_Pct_Daily": None,
        "AgentIssues_Taxa_Daily": None,
    },
    "LAG_EXCLUDE": [],  # NS_Lags são features válidas (30min antes)
    "exclude": {
        "589361": [
            "NewHire_Pct_Daily",
            "AgentIssues_Taxa_Daily",
            "Programa_Target_Enc",
            "Ferias_Qtd_Daily",
            "NS_Lag_2",
            "Is_Fim_Semana",
        ],
    },
}


def get_features_for_program(program_id, all_features: list = None) -> list:
    """
    Retorna lista de features configuradas para um programa.

    Args:
        program_id: CodPrograma (int ou str)
        all_features: Lista completa de features disponíveis (fallback se registry não encontrado)

    Returns:
        Lista de nomes de features para usar no treino
    """
    program_id = str(program_id)

    features = FEATURE_REGISTRY["global"].copy()

    exclude_program = FEATURE_REGISTRY["exclude"].get(program_id, [])

    lag_exclude = FEATURE_REGISTRY.get("LAG_EXCLUDE", [])

    for feat, allowed_programs in FEATURE_REGISTRY["optional"].items():
        if feat in exclude_program:
            continue
        if allowed_programs is None or program_id in [str(p) for p in allowed_programs]:
            features.append(feat)

    if all_features is not None:
        for f in all_features:
            if f not in features and f not in exclude_program and f not in lag_exclude:
                features.append(f)

    return features


def get_lag_features_excluded() -> list:
    """Retorna lista de features de lag excluídas por leakage."""
    return FEATURE_REGISTRY.get("LAG_EXCLUDE", [])


def get_excluded_features(program_id) -> list:
    """Retorna lista de features excluídas para um programa."""
    return FEATURE_REGISTRY["exclude"].get(str(program_id), [])


def list_programs() -> list:
    """Lista todos os programas configurados no registry."""
    programs = set()

    for feat, allowed in FEATURE_REGISTRY["optional"].items():
        if allowed:
            programs.update([str(p) for p in allowed])

    programs.update(FEATURE_REGISTRY["exclude"].keys())

    return sorted(programs)


def register_program_exclusions(program_id: int, features: list) -> None:
    """
    Registra exclusões de features para um programa.

    Args:
        program_id: CodPrograma
        features: Lista de features a excluir
    """
    FEATURE_REGISTRY["exclude"][str(program_id)] = features