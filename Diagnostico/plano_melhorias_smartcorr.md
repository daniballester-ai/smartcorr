# 🎯 Plano de Melhorias — SmartCorr (Modelo por Programa)

## Diagnóstico

O modelo atual treina um **XGBRegressor por programa**, mas há inconsistências:

| Problema | Impacto |
|----------|---------|
| Target Encoding é salvo em arquivo **único** (`target_encoding.json`) para todos os programas | Na inferência, o encoding é compartilhado, mas deveria ser **por programa** |
| `build_features.py` calcula encoding **global** (todos programas juntos) | Cada modelo vê o encoding de outro programa — contaminação |
| Filtro operacional não é **por programa** | Programas com horários diferentes (ex: 24h vs 8h) têm regras iguais |
| Diretório `models/` só tem `model.pkl` legado | Nenhum `model_{programa}.pkl` existe ainda (nunca foi executado o novo pipeline) |

## Prioridades de Implementação

### ✅ P1 — Modelo por Programa (Treino + Inferência)
- **`train_model.py`**: Já tem a lógica por programa ✅
- **`predict.py`**: Já carrega `model_{programa}.pkl` ✅
- **Ação**: Garantir que Target Encoding seja salvo/carregado **por modelo**

### ✅ P2 — Target Encoding por Programa
- **`build_features.py`**: Alterar `_create_target_encoding()` para salvar `target_encoding_{programa}.json`
- **`predict.py`**: Alterar para carregar encoding específico do programa na inferência

### ✅ P3 — Filtro Operacional por Programa  
- **`clean_data.py`**: Log de diagnóstico por programa no filtro operacional

### ✅ P4 — Retreinar com Dados Limpos
- **`params.yaml`**: Ajustar janela, programas ativos

### ✅ P5 — Escalabilidade
- Apenas adicionar novo `CodPrograma` no `params.yaml` e rodar pipeline

## Arquivos Modificados

| Arquivo | Alteração |
|---------|-----------|
| `build_features.py` | Target encoding por programa |
| `predict.py` | Carregar encoding por programa na inferência |
| `clean_data.py` | Log diagnóstico por programa no filtro operacional |
| `params.yaml` | Ajustar `target_encoding_path` para diretório |
