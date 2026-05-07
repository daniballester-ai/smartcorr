import json
import logging
import os
from typing import Any

import joblib
import numpy as np
import pandas as pd
import shap
import yaml

from src.database import get_connection

logger = logging.getLogger(__name__)

PILARES: dict[str, list[str]] = {
    "Volumetria": [
        "Vol_Previsto",
        "Desvio_Volume_Pct_Lag_1",
    ],
    "Pessoas": [
        "HC_Previsto",
        "ABS_Taxa_Daily",
        "Turnover_Taxa_Daily",
        "Ferias_Qtd_Daily",
        "Faltas_Qtd_Daily",
        "PerdaLog_Taxa_Daily",
        "NewHire_Pct_Daily",
        "AgentIssues_Taxa_Daily",
    ],
    "TMA": [
        "Tempo_AHT_Previsto_Total",
        "TME_Real_Avg_Lag_1",
        "Delta_TMA_Lag_1",
    ],
    "Causas_Raiz": [
        "Pressao_Prevista_Vol_HC",
        "Indicador_Sufoco",
        "Vol_Por_Agente",
        "Margem_Capacidade",
        "Ocupacao_Sintetica",
    ],
    "Contexto_Temporal": [
        "Hora",
        "DiaSemana",
        "Dia_Mes",
        "Semana_Mes",
        "Dia_Semana",
        "Is_Inicio_Fim_Mes",
        "Is_Segunda_Sexta",
        "Is_Fim_Semana",
        "Hora_Dia_Ciclo",
        "Is_Horario_Pico",
        "NS_Media_Movel_3",
        "NS_Media_Movel_6",
        "NS_Std_Movel_6",
        "NS_Lag_1",
        "NS_Lag_2",
        "NS_Lag_3",
        "Delta_Aceleracao_NS",
        "NS_Previsto_Erlang",
    ],
    "Contexto_Operacional": [
        "Programa_Target_Enc",
    ],
}


def load_config() -> dict:
    """Carrega as configacoes do arquivo params.yaml.

    Returns:
        dict: Configuracoes carregadas
    """
    with open("params.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_pilar(feature_name: str) -> str:
    """Retorna o pilar analitico ao qual uma feature pertence.

    Args:
        feature_name: Nome da feature

    Returns:
        str: Nome do pilar ou 'Geral' se nao encontrada
    """
    for pilar, variaveis in PILARES.items():
        if feature_name in variaveis:
            return pilar
    return "Geral"

def calcular_explicabilidade_shap(
    modelo: Any, X: pd.DataFrame
) -> np.ndarray:
    """Gera os valores SHAP para explicabilidade do modelo.

    Args:
        modelo: Modelo treinado (XGBoost)
        X: DataFrame com features

    Returns:
        np.ndarray: Valores SHAP para cada sample e feature
    """
    explainer = shap.TreeExplainer(modelo)
    shap_values = explainer.shap_values(X)
    return shap_values


def processar_previsoes(
    df: pd.DataFrame,
    predicoes: np.ndarray,
    shap_values: np.ndarray,
    features: list[str],
) -> list[tuple]:
    """Transforma predicoes em tuplas para gracao no banco.

    Args:
        df: DataFrame com dados originais
        predicoes: Array de predicoes do modelo
        shap_values: Array de valores SHAP
        features: Lista de nomes das features

    Returns:
        list[tuple]: Tuplas formatadas para insert no banco
    """
    resultados: list[tuple] = []

    if "DataRef" not in df.columns:
        df["DataRef"] = df["DataHora"].astype(str).str[:10]
    if "Intervalo" not in df.columns:
        df["Intervalo"] = df["DataHora"].astype(str).str[11:19]

    for i in range(len(df)):
        linha = df.iloc[i]
        valores_shap = dict(zip(features, shap_values[i]))
        
        # 5. Agregacao por Pilares (para BI) conforme Architecture Plan
        impacto_volumetria = sum(valores_shap.get(f, 0) for f in PILARES['Volumetria'])
        impacto_pessoas = sum(valores_shap.get(f, 0) for f in PILARES['Pessoas'])
        impacto_tma = sum(valores_shap.get(f, 0) for f in PILARES['TMA'])
        impacto_causas = sum(valores_shap.get(f, 0) for f in PILARES['Causas_Raiz'])
        
        # Une pilares de contexto (Temporal + Operacional)
        impacto_contexto = sum(valores_shap.get(f, 0) for f in PILARES['Contexto_Temporal'])
        impacto_contexto += sum(valores_shap.get(f, 0) for f in PILARES['Contexto_Operacional'])

        # 6. Identificar Principais Ofensores e Impulsionadores (SHAP Top 3)
        # Mapeamento para saber de qual pilar Ã© a feature
        feat_para_pilar = {}
        for p, feats in PILARES.items():
            for f in feats:
                feat_para_pilar[f] = p

        sorted_items = sorted(valores_shap.items(), key=lambda x: abs(x[1]), reverse=True)
        ofensores = []
        impulsionadores = []
        
        for feat, val in sorted_items:
            pilar_desc = feat_para_pilar.get(feat, "Outros")
            if val < -0.001: # Ofensor (Impacto negativo no NS)
                if len(ofensores) < 3:
                    ofensores.append({"nome": feat, "pilar": pilar_desc, "impacto": val})
            elif val > 0.001: # Impulsionador (Impacto positivo no NS)
                if len(impulsionadores) < 3:
                    impulsionadores.append({"nome": feat, "pilar": pilar_desc, "impacto": val})

        # Preenche vazios se necessÃ¡rio
        while len(ofensores) < 3: 
            ofensores.append({"nome": "Sem Impacto Relevante", "pilar": "N/A", "impacto": 0.0})
        while len(impulsionadores) < 3: 
            impulsionadores.append({"nome": "Sem Impacto Relevante", "pilar": "N/A", "impacto": 0.0})

        vol_previsto = int(linha.get("Vol_Previsto", 0))

        # Regra de Pós-processamento WFM: Se Volume Previsto for zero, NS_Real = 0
        if vol_previsto == 0:
            ns_final = 0.0
        else:
            ns_final = float(np.clip(predicoes[i], 0.0, 1.0))

        # Adiciona à lista de gravação (tupla com 34 elementos)
        resultados.append((
            linha["DataRef"],
            linha["Intervalo"],
            int(linha["CodPrograma"]),
            int(linha.get("Canal", 7)),
            ns_final,
            vol_previsto,
            int(linha.get("HC_Previsto", 0)),
            float(linha.get("TMA_Previsto_Avg", 0.0)),
            float(linha.get("NS_Lag_1", 0.0)),
            float(linha.get("TME_Real_Avg_Lag_1", 0.0)),
            float(linha.get("Desvio_Volume_Pct_Lag_1", 0.0)),
            impacto_volumetria,
            impacto_pessoas,
            impacto_tma,
            impacto_causas,
            impacto_contexto,
            ofensores[0]["nome"], ofensores[0]["pilar"], ofensores[0]["impacto"],
            ofensores[1]["nome"], ofensores[1]["pilar"], ofensores[1]["impacto"],
            ofensores[2]["nome"], ofensores[2]["pilar"], ofensores[2]["impacto"],
            impulsionadores[0]["nome"], impulsionadores[0]["pilar"], impulsionadores[0]["impacto"],
            impulsionadores[1]["nome"], impulsionadores[1]["pilar"], impulsionadores[1]["impacto"],
            impulsionadores[2]["nome"], impulsionadores[2]["pilar"], impulsionadores[2]["impacto"]
        ))

    return resultados

def salvar_no_banco(tuplas_dados: list[tuple]) -> None:
    """Salva tuplas de predicao no banco de dados SQL Server.

    Args:
        tuplas_dados: Lista de tuplas com dados de predicao

    Raises:
        Exception: Se ocorrer erro na transacao no banco de dados
    """
    engine = get_connection()
    # Obter a conexao bruta do DBAPI (pyodbc) para usar fast_executemany
    conn = engine.raw_connection()
    cursor = conn.cursor()

    query = """
    INSERT INTO [OdsCorp].[SmartCorr].[FactSmartCorr_Previsao]
    ([DataRef], [Intervalo], [CodPrograma], [Canal], [NS_Previsto_SmartCorr],
     [Vol_Previsto], [HC_Previsto], [TMA_Previsto_Avg], [NS_Lag_1],
     [TME_Real_Lag_1], [Desvio_Volume_Pct_Lag_1],
     [Impacto_Pilar_Volumetria], [Impacto_Pilar_Pessoas], [Impacto_Pilar_TMA], [Impacto_Pilar_Causas], [Impacto_Pilar_Contexto],
     [Ofensor_1_Nome], [Ofensor_1_Pilar], [Ofensor_1_Impacto],
     [Ofensor_2_Nome], [Ofensor_2_Pilar], [Ofensor_2_Impacto],
     [Ofensor_3_Nome], [Ofensor_3_Pilar], [Ofensor_3_Impacto],
     [Impulsionador_1_Nome], [Impulsionador_1_Pilar], [Impulsionador_1_Impacto],
     [Impulsionador_2_Nome], [Impulsionador_2_Pilar], [Impulsionador_2_Impacto],
     [Impulsionador_3_Nome], [Impulsionador_3_Pilar], [Impulsionador_3_Impacto])
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    try:
        if tuplas_dados:
            # Converter tipos numpy para python nativo (evita erro pyodbc float32)
            tuplas_dados = [
                tuple(x.item() if hasattr(x, "item") and not isinstance(x, (str, bytes)) else x for x in t)
                for t in tuplas_dados
            ]
            df_tuplas = pd.DataFrame(tuplas_dados)
            agrupado = df_tuplas.groupby(0)[1].min().reset_index()

            logger.info("Limpando previsoes antigas (Rolling Forecast) no BD...")
            for _, row in agrupado.iterrows():
                dt_ref = str(row[0])
                min_int = str(row[1])
                query_del = f"""DELETE FROM [OdsCorp].[SmartCorr].[FactSmartCorr_Previsao]
                                WHERE [DataRef] = '{dt_ref}' AND [Intervalo] >= '{min_int}'"""
                cursor.execute(query_del)
                logger.info(f"Limpo Data={dt_ref} >= Intervalo {min_int}")

            logger.info(
                f"Gravando {len(tuplas_dados)} registros SHAP. "
                "(fast_executemany=True)"
            )
            cursor.fast_executemany = True
            cursor.executemany(query, tuplas_dados)
            conn.commit()
            logger.info("Transaction on Database successfully!")
    except Exception as e:
        conn.rollback()
        logger.error(f"Erro ao salvar dados de predicao no SQL Server: {e}")
        raise
    finally:
        conn.close()


def main() -> None:
    """Orquestra pipeline de inferencia por programa.

    Para cada programa presente nos dados futuros:
        1. Carrega o modelo especifico (model_{CodPrograma}.pkl)
        2. Realiza predicao do NS
        3. Calcula SHAP values para explicabilidade
        4. Processa impactos por pilar
        5. Salva todas as predicoes no banco
    """
    config = load_config()
    caminho_futuro = config["data"]["processed_future_path"]
    features_global = config["data"]["features"]
    use_feature_registry = config["data"].get("use_feature_registry", False)
    
    # Import feature registry if needed
    if use_feature_registry:
        try:
            from src.config.feature_registry import get_features_for_program
            HAS_FEATURE_REGISTRY = True
        except ImportError:
            HAS_FEATURE_REGISTRY = False
    else:
        HAS_FEATURE_REGISTRY = False
    
    diretorio_modelos = config["model"].get("models_dir", "models")

    if not os.path.exists(caminho_futuro):
        logger.warning(f"Arquivo {caminho_futuro} ausente. Fim da rotina.")
        return

    logger.info("1. Lendo dados Futuros da Gestao...")
    df_futuro = pd.read_csv(caminho_futuro)

    if df_futuro.empty:
        logger.warning("Base do Futuro vazia. Nenhum intervalo projetado hoje.")
        return

    programas_futuro = sorted(df_futuro["CodPrograma"].unique())
    logger.info(f"Programas no futuro: {list(programas_futuro)}")

    todas_tuplas = []

    for programa in programas_futuro:
        caminho_modelo = os.path.join(diretorio_modelos, f"model_{programa}.pkl")

        if not os.path.exists(caminho_modelo):
            logger.warning(
                f"Programa {programa}: modelo nÃ£o encontrado em "
                f"{caminho_modelo}. Pulando inferencia."
            )
            continue

        df_prog = df_futuro[df_futuro["CodPrograma"] == programa].copy()
        if df_prog.empty:
            continue

        logger.info(
            f"2. Programa {programa}: carregando modelo {caminho_modelo}..."
        )
        modelo = joblib.load(caminho_modelo)

        # â”€â”€â”€ Carrega encoding per-programa (P2) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        dir_encodings = config["data"].get(
            "target_encoding_dir", "models/encodings/"
        )
        caminho_enc = os.path.join(
            dir_encodings, f"target_encoding_{programa}.json"
        )
        if os.path.exists(caminho_enc):
            with open(caminho_enc, "r", encoding="utf-8") as f:
                dados_enc = json.load(f)
            valor_enc = float(dados_enc["encoding"])
            # Valida se o CSV tem o mesmo valor
            valor_csv = df_prog["Programa_Target_Enc"].iloc[0]
            if abs(valor_csv - valor_enc) > 1e-6:
                logger.warning(
                    f"Programa {programa}: encoding CSV={valor_csv:.6f} â‰  "
                    f"arquivo={valor_enc:.6f}. Sobrescrevendo com arquivo."
                )
            df_prog["Programa_Target_Enc"] = valor_enc
            logger.info(
                f"   Encoding per-programa carregado: {valor_enc:.6f}"
            )
        else:
            logger.warning(
                f"Programa {programa}: arquivo de encoding nÃ£o encontrado "
                f"em {caminho_enc}. Usando valor do CSV."
            )

        # 1. Determinar lista de features (Registro ou Global)
        if HAS_FEATURE_REGISTRY:
            features_prog = get_features_for_program(programa, features_global)
            logger.info(f"   Using {len(features_prog)} features from registry for programa {programa}")
        else:
            features_prog = features_global

        # 2. Preparar os dados de entrada (X) garantindo a ordem esperada pelo modelo
        if hasattr(modelo, "feature_names_in_"):
            expected_features = list(modelo.feature_names_in_)
            # Filtra e ordena as colunas conforme o modelo foi treinado
            available_features = [f for f in expected_features if f in df_prog.columns]
            if len(available_features) < len(expected_features):
                missing = set(expected_features) - set(available_features)
                logger.warning(f"   Missing features for prediction: {missing}")
            X_filtered = df_prog[available_features]
            logger.info(f"   Using {len(available_features)} features (model expects {len(expected_features)})")
        else:
            X_filtered = df_prog[features_prog]
            logger.info(f"   Using global features: {len(features_prog)}")
        
        logger.info(
            f"3. Programa {programa}: predicao de {len(X_filtered)} intervalos..."
        )
        predicoes_trans = modelo.predict(X_filtered)
        
        target_transformation = config["model"].get("target_transformation", False)
        target = config["data"].get("target", "NS_Real")
        
        if target_transformation and target != "NS_Residuo":
            predicoes = 1.0 - np.expm1(predicoes_trans)
        else:
            predicoes = predicoes_trans

        logger.info(f"4. Programa {programa}: SHAP Values...")
        shap_values = calcular_explicabilidade_shap(modelo, X_filtered)

        logger.info(f"5. Programa {programa}: processando impactos por pilar...")
        tuplas = processar_previsoes(df_prog, predicoes, shap_values, features_prog)
        todas_tuplas.extend(tuplas)

        ns_medio = float(np.mean(np.clip(predicoes, 0.0, 1.0)))
        logger.info(
            f"   Programa {programa}: {len(tuplas)} registros processados. "
            f"NS médio previsto: {ns_medio:.4f}"
        )

    if todas_tuplas:
        salvar_no_banco(todas_tuplas)
        logger.info(f"Total: {len(todas_tuplas)} registros salvos no banco.")
    else:
        logger.warning("Nenhuma predicao gerada para nenhum programa.")

    logger.info("Pipeline de Inferencia Finalizado!")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
    main()
