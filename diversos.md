1. **Combater o Vício no Target Lagado:**
   * Retire as variáveis `NS_Lag_*` temporariamente durante alguns testes. Force o modelo a tentar prever o cenário olhando puramente para a força de trabalho (Faltas, HC, AHT, Volume) em vez de apenas seguir a inércia do NS passado.
   * *Alternativa:* Em vez do NS absoluto no passado, forneça a "Variação/Tendência do NS" (ex: diferença entre NS atual e a média do dia).
2. **Regularização dos Hiperparâmetros (Combate ao Overfitting):**
   * Reduzir o grau de complexidade das árvores do XGBoost. Reduza o `max_depth` (para talvez 3 ou 4), aumente a regularização L1/L2 (`alpha` e `lambda`), e use colsample/subsample (ex: 0.8) para obrigar a árvore a procurar padrões em variáveis que não sejam apenas os lags.
3. **Engenharia de Variáveis Combinadas:**
   * O algoritmo pode estar tendo dificuldade de correlacionar variáveis. Pense em criar  *features sintéticas* , como: `Volume_Por_HC` (Pressão), `Razão_AHT_Volumetria`, em vez de deixar essas variáveis soltas.
