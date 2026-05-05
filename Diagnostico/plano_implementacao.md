# 🛠️ Plano de Implementação — Diagnóstico SmartCorr

## Arquivos Modificados (ordem de dependência)

| # | Arquivo | Mudanças |
|---|---|---|
| 1 | `params.yaml` | Remove 11 features mortas, adiciona 4 novas, aumenta janela, adiciona config `programas` |
| 2 | `config/queries.ini` | Substitui CodPrograma hardcoded por placeholder `{programas_filter}` |
| 3 | `src/data_loading/load_data.py` | Lê lista de programas do config e injeta na query dinamicamente |
| 4 | `src/data_preprocessing/clean_data.py` | Filtra intervalos sem operação real (`Vol_Real == 0`) |
| 5 | `src/feature_engineering/build_features.py` | Adiciona rolling features + Target Encoding para CodPrograma |
| 6 | `src/model_training/train_model.py` | Filtro de segurança + logging aprimorado |
| 7 | `src/model_evaluation/evaluate_model.py` | Métricas por programa |
| 8 | `src/inference/predict.py` | Usa target encoding salvo na inferência |

## Estratégia de Escalabilidade

Para novos clientes/programas:
1. Adicionar os CodPrograma na lista `data.programas` do `params.yaml`
2. O Target Encoding é aprendido automaticamente dos dados
3. Programas novos (sem histórico) recebem a média global como encoding
4. Nenhum código precisa mudar — apenas configuração

## Status

- [x] Diagnóstico concluído
- [ ] Implementação em andamento...
