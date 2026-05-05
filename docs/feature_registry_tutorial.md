# Tutorial: Feature Registry por Programa

## Cenário Atual

O `params.yaml` define features **globais** para todos os programas. O problema: no programa 589361, `NewHire_Pct_Daily` e `AgentIssues_Taxa_Daily` têm importance zero, mas podem ser relevantes para outros programas.

---

## Passo 1: Analisar Métricas de um Programa

```bash
# Ver métricas de um programa específico
cat SmartCorr/metrics/train_metrics_589361.json
```

Isso mostra as `feature_importances` - quanto cada feature contribuiu para o modelo.

---

## Passo 2: Identificar Features Zeradas

Do arquivo analisado:

| Feature | Importance |
|---------|-----------|
| NewHire_Pct_Daily | **0.0** |
| AgentIssues_Taxa_Daily | **0.0** |
| Programa_Target_Enc | 0.0 |

**Estas deveriam ser removidas apenas deste programa.**

---

## Passo 3: Estrutura do Feature Registry (Proposta)

```python
# src/config/feature_registry.py

"""
Feature Registry - Controle granular de features por programa.

Estrutura:
- global: features sempre inclusas em todos os programas
- optional: features com lista de programas que devem usá-las (None = todos)
- exclude: features explicitamente excluídas por programa
"""

FEATURE_REGISTRY = {
    # Features globais (todos os programas)
    "global": [
        "Hora", "DiaSemana",
        "Vol_Previsto", "HC_Previsto",
        "TME_Real_Avg_Lag_1", "Delta_TMA_Lag_1",
        "NS_Media_Movel_3", "NS_Media_Movel_6",
    ],

    # Features opcionais (disponíveis, mas não garantidas)
    # None = disponível para TODOS os programas
    # Lista = disponível apenas para programas específicos
    "optional": {
        "NewHire_Pct_Daily": None,
        "AgentIssues_Taxa_Daily": None,
        "Ferias_Qtd_Daily": None,
        "Faltas_Qtd_Daily": None,
        "NS_Std_Movel_6": None,
    },

    # Exclusões explícitas por programa
    "exclude": {
        # Exemplo: programa 589361 não usa estas features
        "589361": [
            "NewHire_Pct_Daily",
            "AgentIssues_Taxa_Daily",
            "Programa_Target_Enc",  # target encoding já é por programa
        ],

        # Outros programas podem ter outras exclusões
        "589362": [
            "Some_Problematic_Feature",
        ],
    },
}


def get_features_for_program(program_id: int | str) -> list[str]:
    """
    Retorna lista de features configuradas para um programa.

    Args:
        program_id: CodPrograma

    Returns:
        Lista de nomes de features para usar no treino
    """
    program_id = str(program_id)

    # Começa com features globais
    features = FEATURE_REGISTRY["global"].copy()

    # Adiciona features opcionais
    exclude_program = FEATURE_REGISTRY["exclude"].get(program_id, [])

    for feat, allowed_programs in FEATURE_REGISTRY["optional"].items():
        if feat in exclude_program:
            continue
        # None = disponível para todos, senão verifica lista
        if allowed_programs is None or program_id in [str(p) for p in allowed_programs]:
            features.append(feat)

    return features
```

---

## Passo 4: No params.yaml, usar feature registry

```yaml
data:
  # Em vez de listar todas as features:
  use_feature_registry: true  # Ativa uso do registry

  # Features fixed (sempre incluir, independente do registry)
  fixed_features:
    - Hora
    - DiaSemana

  # Fallback: lista padrão se registry não encontrado
  default_features:
    - Vol_Previsto
    - HC_Previsto
    # ... todas as features atuais
```

---

## Passo 5: Fluxo de Adicionar Novo Programa

```
1. ADICIONAR AO params.yaml
   programas:
     - 366845
     - 589361
     - NOVO_CODIGO  ← novo programa

2. EXECUTAR TREINO
   python main.py
   → Gera metrics/train_metrics_NOVO_CODIGO.json

3. ANALISAR FEATURES ZERADAS
   cat metrics/train_metrics_NOVO_CODIGO.json
   → Verificar feature_importances
   → Identificar features com importance = 0

4. CONFIGURAR NO REGISTRY (se necessário)
   # Se há features com importance zero, adiciona ao exclude no feature_registry.py
   "exclude": {
       "NOVO_CODIGO": ["Feature_Zerada1", "Feature_..."]
   }
```

---

## Passo 6: Script de Diagnóstico (Utilitário)

```python
# scripts/diagnose_program.py

import json
import sys

def diagnose_program(program_id: int):
    metrics_path = f"SmartCorr/metrics/train_metrics_{program_id}.json"

    try:
        with open(metrics_path) as f:
            metrics = json.load(f)
    except FileNotFoundError:
        print(f"Métricas não encontradas: {metrics_path}")
        print("Execute o treino primeiro: python main.py")
        sys.exit(1)

    print(f"=== DIAGNÓSTICO: Programa {program_id} ===\n")
    print(f"Algoritmo: {metrics['algoritmo']}")
    print(f"R² Train: {metrics['r2_train']:.4f}")
    print(f"R² Test:  {metrics['r2_test']:.4f}")
    print(f"MAE Test: {metrics['mae_test']:.4f}")

    print("\n--- Features com Importance ZERO ---")
    zeradas = [(k, v) for k, v in metrics['feature_importances'].items() if v == 0.0]
    if zeradas:
        for feat, imp in zeradas:
            print(f"  ✗ {feat}")
    else:
        print("  Nenhuma feature com importance zero.")

    print("\n--- Top 5 Features ---")
    top = sorted(metrics['feature_importances'].items(), key=lambda x: x[1], reverse=True)[:5]
    for feat, imp in top:
        print(f"  ✓ {feat}: {imp:.4f}")

    print("\n--- RECOMENDAÇÃO ---")
    if metrics['r2_test'] < 0:
        print("  ⚠ R² negativo! Possível overfitting.")
        print("  → Considere reduzir max_depth ou aumentar regularização.")
    elif metrics['r2_test'] < 0.3:
        print("  ⚠ R² baixo. Verificar features disponíveis.")
        print("  → Executar diagnose para analisar features zeradas.")

    # Suggest registry update
    if zeradas:
        print("\n  → Considere adicionar ao feature_registry.py:")
        exclude_entry = ", ".join([f'"{f}"' for f, _ in zeradas])
        print(f'    "{program_id}": [{exclude_entry}],')

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python diagnose_program.py <programa>")
        sys.exit(1)
    diagnose_program(int(sys.argv[1]))
```

---

## Uso

```bash
# Diagnosticar programa 589361
python scripts/diagnose_program.py 589361
```

Saída esperada:
```
=== DIAGNÓSTICO: Programa 589361 ===

Algoritmo: XGBRegressor
R² Train: 0.2767
R² Test:  -0.0306
MAE Test: 0.0789

--- Features com Importance ZERO ---
  ✗ NewHire_Pct_Daily
  ✗ AgentIssues_Taxa_Daily
  ✗ Programa_Target_Enc

--- Top 5 Features ---
  ✓ NS_Media_Movel_6: 0.1235
  ✓ NS_Media_Movel_3: 0.1014
  ✓ HC_Previsto: 0.1008
  ✓ PerdaLog_Taxa_Daily: 0.0821
  ✓ TME_Real_Avg_Lag_1: 0.0657

--- RECOMENDAÇÃO ---
  ⚠ R² negativo! Possível overfitting.
  → Considere reduzir max_depth ou aumentar regularização.

  → Considere adicionar ao feature_registry.py:
    "589361": ["NewHire_Pct_Daily", "AgentIssues_Taxa_Daily", "Programa_Target_Enc"],
```