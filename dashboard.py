import os
import sys
from datetime import datetime

import numpy as np

# Garantir que o diretório do dashboard seja o working directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import dashboard_lib as dl

# Paleta de cores por pilar (usada em múltiplos gráficos)
CORES_PILARES = {
    "Volumetria": "#2196F3",
    "Pessoas": "#FF9800",
    "TMA": "#9C27B0",
    "Drivers_Operacionais": "#00BCD4",
    "Saude": "#00BCD4",
    "Contexto": "#4CAF50",
    "Outros": "#BDBDBD",
}

st.set_page_config(
    page_title="SmartCorr Benchmark",
    page_icon="📊",
    layout="wide",
)

st.title("SmartCorr — Benchmark Dashboard")
st.markdown("Comparação NS_Real vs NS_WFM vs NS_SmartCorr com histórico de execuções")

runs_df = dl.list_benchmark_runs()
tem_execucoes = not runs_df.empty
ultimo_suffix = runs_df.iloc[0]["suffix"] if tem_execucoes else None

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "▶️ Executar",
    "📊 Visão Geral",
    "📈 Por Programa",
    "⏳ Histórico",
    "📖 Glossário",
])

# ==============================================================================
# TAB 1 - EXECUTAR
# ==============================================================================
with tab1:
    st.subheader("Executar Novo Benchmark")

    # Exibe resultado da execução anterior (se houver)
    status = st.session_state.get("benchmark_status")
    if status:
        if status["ok"]:
            st.success(f"{status['msg']} — Selecione a nova execução nas abas ao lado.")
        else:
            st.error(status["msg"])

    col1, col2 = st.columns([2, 1])
    with col1:
        dias = st.slider(
            "Dias retroativos",
            min_value=1, max_value=90, value=7,
            help="Quantos dias para trás o benchmark irá processar",
        )
    with col2:
        st.markdown("###")
        executar_btn = st.button(
            "▶️ Executar",
            type="primary",
            use_container_width=True,
            disabled=st.session_state.get("executando", False),
        )

    if executar_btn:
        st.session_state["executando"] = True
        st.session_state.pop("benchmark_status", None)
        st.rerun()

    if st.session_state.get("executando", False):
        barra = st.progress(0, text="Iniciando...")
        log_area = st.empty()

        def callback(progresso, mensagem):
            barra.progress(progresso, text=mensagem)
            log_area.info(f"{mensagem} ({progresso}%)")

        try:
            metricas = dl.run_benchmark(dias, progress_callback=callback)
            ok = bool(metricas)
            if ok:
                st.balloons()
            st.session_state["benchmark_status"] = {
                "ok": ok,
                "msg": "Benchmark concluído com sucesso!" if ok else "Benchmark retornou vazio. Verifique os logs.",
            }
        except Exception as e:
            st.session_state["benchmark_status"] = {"ok": False, "msg": f"Erro: {e}"}
            import traceback
            traceback.print_exc()
        finally:
            st.session_state["executando"] = False
            st.rerun()

# ==============================================================================
# TAB 2 - VISÃO GERAL
# ==============================================================================
with tab2:
    st.subheader("Visão Geral")

    if not tem_execucoes:
        st.info("Nenhum benchmark executado ainda. Vá até a aba ▶️ Executar.")
    else:
        run_sel = st.selectbox(
            "Qual execução visualizar?",
            options=runs_df["suffix"].tolist(),
            format_func=lambda s: dl.get_nome_legivel(s),
            key="tab2_run",
        )

        metricas = dl.load_metrics(run_sel)
        if not metricas:
            st.warning("Não foi possível carregar as métricas desta execução.")
        else:
            col_m1, col_m2, col_m3, col_m4 = st.columns(4)
            sc = metricas.get("smartcorr", {})
            er = metricas.get("erlang", {})
            uplift = metricas.get("uplift_mae_pct", 0)

            with col_m1:
                st.metric("MAE SmartCorr", f"{sc.get('MAE', 0):.4f}",
                          delta=f"{sc.get('MAE', 0) - er.get('MAE', 0):.4f}" if er.get('MAE') else None,
                          delta_color="inverse",
                          help="Erro absoluto médio. **Menor = melhor**. Quanto menor a diferença entre predição e real.")
            with col_m2:
                st.metric("RMSE SmartCorr", f"{sc.get('RMSE', 0):.4f}",
                          delta=f"{sc.get('RMSE', 0) - er.get('RMSE', 0):.4f}" if er.get('RMSE') else None,
                          delta_color="inverse",
                          help="Raiz do erro quadrático médio. **Menor = melhor**. Penaliza mais erros grandes que o MAE.")
            with col_m3:
                st.metric("R² SmartCorr", f"{sc.get('R2', 0):.4f}",
                          delta=f"{sc.get('R2', 0) - er.get('R2', 0):.4f}" if er.get('R2') else None,
                          help="Coeficiente de determinação. **Mais próximo de 1 = melhor**. Mede o quão bem o modelo explica a variância dos dados. Pode ser negativo quando o modelo é pior que a média.")
            with col_m4:
                st.metric("Uplift MAE %", f"{uplift:.1f}%",
                          delta=f"{uplift:.1f}pp" if uplift else None,
                          help="Melhoria percentual do SmartCorr sobre o WFM. **Positivo = melhor**. Calculado como (MAE_WFM - MAE_SC) / MAE_WFM * 100.")

            st.markdown("---")
            st.subheader("Métricas por Programa")

            por_programa = metricas.get("por_programa", {})
            if por_programa:
                linhas = []
                for prog, m in sorted(por_programa.items(), key=lambda x: int(x[0])):
                    def _fmt_val(v):
                        if v is None:
                            return "-"
                        if isinstance(v, float):
                            return f"{v:.4f}"
                        return str(v)

                    linhas.append({
                        "Programa": int(prog),
                        "Intervalos": m.get("intervalos", 0),
                        "NS Real Médio": f"{m.get('NS_Real_medio', 0):.3f}",
                        "MAE SmartCorr": f"{m.get('MAE_SmartCorr', 0):.4f}",
                        "MAE WFM": f"{m.get('MAE_Erlang', 0):.4f}",
                        "RMSE SmartCorr": _fmt_val(m.get("RMSE_SmartCorr")),
                        "RMSE WFM": _fmt_val(m.get("RMSE_Erlang")),
                        "Uplift %": f"{m.get('Uplift_MAE_pct', 0):+.1f}%",
                        "Impacto Volumetria": _fmt_val(m.get("Impacto_Pilar_Volumetria")),
                        "Impacto Pessoas": _fmt_val(m.get("Impacto_Pilar_Pessoas")),
                        "Impacto TMA": _fmt_val(m.get("Impacto_Pilar_TMA")),
                    })
                df_prog = pd.DataFrame(linhas)
                st.dataframe(
                    df_prog, use_container_width=True, hide_index=True,
                    column_config={"Programa": st.column_config.NumberColumn(format="%d")},
                )

                csv_data = df_prog.to_csv(index=False)
                st.download_button("📥 Download CSV", csv_data,
                                   f"metricas_por_programa_{run_sel}.csv", "text/csv")

                st.markdown("---")
                st.subheader("Uplift % por Programa")
                st.caption("Percentual de melhoria do SmartCorr sobre o WFM. **Positivo = SmartCorr melhor.**")
                progs_ord = sorted(por_programa.items(), key=lambda x: x[1].get("Uplift_MAE_pct", 0), reverse=True)
                fig = go.Figure()
                fig.add_trace(go.Bar(
                    x=[str(int(p)) for p, _ in progs_ord],
                    y=[m["Uplift_MAE_pct"] for _, m in progs_ord],
                    marker_color=["#4CAF50" if m["Uplift_MAE_pct"] >= 0 else "#F44336"
                                  for _, m in progs_ord],
                    text=[f"{m['Uplift_MAE_pct']:+.1f}%" for _, m in progs_ord],
                    textposition="outside",
                    cliponaxis=False,
                ))
                fig.add_hline(y=0, line_color="gray", line_dash="dot")
                fig.update_layout(xaxis_title="Programa", yaxis_title="Uplift %",
                                  height=400, yaxis=dict(rangemode="tozero"),
                                  xaxis=dict(type="category"))
                st.plotly_chart(fig, use_container_width=True)

            st.caption(f"Total de intervalos: {metricas.get('total_intervalos', 0)}")
            meta = metricas.get("_metadata", {})
            st.caption(f"Executado em: {meta.get('data_execucao', '')}")

# ==============================================================================
# TAB 3 - POR PROGRAMA
# ==============================================================================
with tab3:
    st.subheader("Detalhamento por Programa")

    if not tem_execucoes:
        st.info("Nenhum benchmark executado ainda. Vá até a aba ▶️ Executar.")
    else:
        run_sel = st.selectbox(
            "Qual execução visualizar?",
            options=runs_df["suffix"].tolist(),
            format_func=lambda s: dl.get_nome_legivel(s),
            key="tab3_run",
        )

        programas = dl.get_programas_disponiveis(run_sel)
        if not programas:
            st.warning("Nenhum programa encontrado nesta execução.")
        else:
            def _fmt_prog(p):
                nome = dl.get_nome_programa(p)
                return f"{p} — {nome}" if nome else f"Programa {p}"

            programa_sel = st.selectbox(
                "Selecionar Programa",
                options=programas,
                format_func=_fmt_prog,
            )

            metricas = dl.load_metrics(run_sel)
            prog_metrics = metricas.get("por_programa", {}).get(programa_sel, {})

            if prog_metrics:
                col_p1, col_p2, col_p3, col_p4, col_p5 = st.columns(5)
                with col_p1:
                    st.metric("Intervalos", prog_metrics.get("intervalos", 0))
                with col_p2:
                    st.metric("NS Real Médio", f"{prog_metrics.get('NS_Real_medio', 0):.3f}",
                              help="Média do NS real observado nos intervalos do período.")
                with col_p3:
                    st.metric("MAE SmartCorr", f"{prog_metrics.get('MAE_SmartCorr', 0):.4f}",
                              help="Erro absoluto médio do SmartCorr. **Menor = melhor.**")
                with col_p4:
                    st.metric("MAE WFM", f"{prog_metrics.get('MAE_Erlang', 0):.4f}",
                              help="Erro absoluto médio do WFM (Erlang). **Menor = melhor.**")
                with col_p5:
                    st.metric("Uplift vs WFM", f"{prog_metrics.get('Uplift_MAE_pct', 0):+.1f}%",
                              help="Melhoria percentual do SmartCorr sobre o WFM. **Positivo = SmartCorr melhor.**")

            df_pred = dl.load_predictions_csv(run_sel)
            if not df_pred.empty:
                df_prog = df_pred[df_pred["CodPrograma"] == int(programa_sel)].copy()
                if not df_prog.empty:
                    df_prog["DataHora"] = pd.to_datetime(
                        df_prog["DataRef"].astype(str) + " " + df_prog["Intervalo"].astype(str)
                    )
                    df_prog = df_prog.sort_values("DataHora")

                    st.markdown("---")
                    st.subheader("Série Temporal")
                    st.caption("Intervalos não-operacionais (Vol_Real = 0) aparecem como quebras na linha.")

                    df_chart = df_prog.copy()
                    mask_non_op = df_chart["Vol_Real"] <= 0
                    for col in ["NS_Real", "NS_Previsto_SmartCorr", "NS_Previsto_WFM"]:
                        if col in df_chart.columns:
                            df_chart.loc[mask_non_op, col] = None
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(x=df_chart["DataHora"], y=df_chart["NS_Real"],
                        mode="lines", name="NS Real", line=dict(color="black", width=2), connectgaps=False))
                    if "NS_Previsto_SmartCorr" in df_chart.columns:
                        fig.add_trace(go.Scatter(x=df_chart["DataHora"],
                            y=df_chart["NS_Previsto_SmartCorr"], mode="lines",
                            name="NS SmartCorr", line=dict(color="#2196F3", width=2), connectgaps=False))
                    if "NS_Previsto_WFM" in df_chart.columns:
                        fig.add_trace(go.Scatter(x=df_chart["DataHora"],
                            y=df_chart["NS_Previsto_WFM"], mode="lines",
                            name="NS WFM", line=dict(color="#FF5252", width=1.5, dash="dash"), connectgaps=False))
                    fig.update_layout(xaxis_title="Data/Hora", yaxis_title="Nível de Serviço",
                        yaxis_range=[-0.05, 1.05], height=500, hovermode="x unified",
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5))
                    fig.update_xaxes(
                        rangeslider_visible=True,
                        rangeselector=dict(
                            buttons=list([
                                dict(count=1, label="1d", step="day", stepmode="backward"),
                                dict(count=3, label="3d", step="day", stepmode="backward"),
                                dict(count=7, label="7d", step="day", stepmode="backward"),
                                dict(step="all", label="Tudo")
                            ])
                        )
                    )
                    st.plotly_chart(fig, use_container_width=True)

                    st.markdown("---")
                    st.subheader("Impacto SHAP por Pilar (média do período)")
                    impacto_cols = [
                        "Impacto_Pilar_Volumetria", "Impacto_Pilar_Pessoas",
                        "Impacto_Pilar_TMA", "Impacto_Pilar_Drivers_Operacionais",
                        "Impacto_Pilar_Contexto", "Impacto_Pilar_Saude", # Compatibilidade
                    ]
                    impacto_exist = [c for c in impacto_cols if c in df_prog.columns]
                    if impacto_exist:
                        impacto_means = {c.replace("Impacto_Pilar_", ""): df_prog[c].mean() for c in impacto_exist}
                        
                        # Mapeamento para nomes amigáveis no gráfico
                        nomes_display = {
                            "Drivers_Operacionais": "Drivers Operacionais",
                            "Saude": "Drivers Operacionais",
                            "Contexto": "Contexto",
                        }
                        labels_grafico = [nomes_display.get(k, k) for k in impacto_means.keys()]
                        
                        fig_impacto = go.Figure()
                        fig_impacto.add_trace(go.Bar(
                            x=labels_grafico,
                            y=list(impacto_means.values()),
                            marker=dict(
                                color=[CORES_PILARES.get(k, "#BDBDBD") for k in impacto_means.keys()]
                            ),
                            text=[f"{v:+.4f}" for v in impacto_means.values()],
                            textposition="outside",
                        ))
                        fig_impacto.add_hline(y=0, line_color="gray", line_dash="dot")
                        y_max = max(abs(v) for v in impacto_means.values()) * 1.4 or 0.01
                        fig_impacto.update_layout(
                            xaxis_title="Pilar", yaxis_title="Impacto SHAP médio",
                            height=350,
                            yaxis=dict(range=[-y_max, y_max]),
                            margin=dict(l=10, r=10, t=50, b=30),
                        )
                        st.plotly_chart(fig_impacto, use_container_width=True)
                        st.caption(
                            "**Drivers Operacionais** = indicadores sintéticos de pressão de fila e capacidade (ex: indicador de sufoco, margem).<br>"
                            "**Contexto** = features temporais (hora, dia da semana, início/fim de mês) "
                            "+ operacionais (meta de SLA).<br>"
                            "**Valores negativos** = pilar reduz o valor do modelo, o que **AUMENTA o Nível de Serviço (NS)**.<br>"
                            "**Valores positivos** = pilar aumenta o valor do modelo, o que **REDUZ o Nível de Serviço (NS)**.",
                            unsafe_allow_html=True
                        )

                    with st.expander("🔬 SHAP Summary (importância por feature)"):
                        shap_data = dl.load_shap_summary(run_sel, programa_sel)
                        if shap_data:
                            df_shap = pd.DataFrame(
                                sorted(shap_data.items(), key=lambda x: x[1], reverse=True),
                                columns=["Feature", "|SHAP| médio"],
                            )
                            top_n = min(15, len(df_shap))
                            df_shap_top = df_shap.head(top_n).iloc[::-1]

                            def _cor_feature(f):
                                p = dl.get_pilar_da_feature(f)
                                return CORES_PILARES.get(p, "#BDBDBD")
                            lista_cores = [_cor_feature(f) for f in df_shap_top["Feature"]]

                            fig_shap = go.Figure()
                            fig_shap.add_trace(go.Bar(
                                x=df_shap_top["|SHAP| médio"],
                                y=df_shap_top["Feature"],
                                orientation="h",
                                marker_color=lista_cores,
                                text=df_shap_top["|SHAP| médio"].apply(lambda v: f"{v:.4f}"),
                                textposition="outside",
                            ))
                            fig_shap.update_layout(
                                xaxis_title="Importância média |SHAP|",
                                height=max(300, top_n * 28),
                                margin=dict(l=10, r=80, t=20, b=50),
                            )
                            st.plotly_chart(fig_shap, use_container_width=True)
                            st.markdown(
                                '<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#9C27B0;margin-right:4px;"></span> TMA'
                                '&nbsp;&nbsp;&nbsp;'
                                '<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#FF9800;margin-right:4px;"></span> Pessoas'
                                '&nbsp;&nbsp;&nbsp;'
                                '<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#2196F3;margin-right:4px;"></span> Volumetria'
                                '&nbsp;&nbsp;&nbsp;'
                                '<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#BDBDBD;margin-right:4px;"></span> Outros',
                                unsafe_allow_html=True,
                            )
                        else:
                            st.info("SHAP Summary não disponível para esta execução. Execute um novo benchmark.")

                        # Adicionar Intervalo_Fim (delta de 30 min entre intervalos)
                        intervalos_ord = sorted(df_prog["Intervalo"].unique())
                        if len(intervalos_ord) >= 2:
                            h1, m1 = intervalos_ord[0].split(":")[:2]
                            h2, m2 = intervalos_ord[1].split(":")[:2]
                            delta_min = (int(h2) * 60 + int(m2)) - (int(h1) * 60 + int(m1))
                        else:
                            delta_min = 30
                        df_prog["Intervalo_Inicio"] = df_prog["Intervalo"]
                        minutos = df_prog["Intervalo"].str.split(":").apply(
                            lambda x: int(x[0]) * 60 + int(x[1])
                        )
                        df_prog["Intervalo_Fim"] = (minutos + delta_min).apply(
                            lambda m: f"{m // 60:02d}:{m % 60:02d}:00"
                        )

                    shap_vals = dl.load_shap_values(run_sel, programa_sel)

                    with st.expander("📋 Dados tabulares"):
                        df_tabela = df_prog.copy()
                        df_tabela["_shap_idx"] = range(len(df_tabela))
                        df_tabela = df_tabela.sort_values(
                            ["DataRef", "Intervalo"], ascending=[False, True]
                        ).reset_index(drop=True)
                        cols = ["DataRef", "Intervalo_Inicio", "Intervalo_Fim", "Vol_Real", "Vol_Previsto",
                                "NS_Real", "NS_Previsto_SmartCorr", "NS_Previsto_WFM",
                                "Impacto_Pilar_Volumetria", "Impacto_Pilar_Pessoas",
                                "Impacto_Pilar_TMA", "Impacto_Pilar_Causas",
                                "Impacto_Pilar_Contexto",
                                "Ofensor_1_Nome", "Ofensor_1_Pilar", "Ofensor_1_Impacto",
                                "Impulsionador_1_Nome", "Impulsionador_1_Pilar", "Impulsionador_1_Impacto",
                                ]
                        cols_exist = [c for c in cols if c in df_tabela.columns]
                        sel_event = st.dataframe(
                            df_tabela[cols_exist],
                            use_container_width=True,
                            hide_index=True,
                            on_select="rerun",
                            selection_mode="single-row",
                        )
                        selected_rows = sel_event.selection.rows
                        if selected_rows:
                            st.session_state["_shap_sel_idx"] = int(
                                df_tabela.iloc[selected_rows[0]]["_shap_idx"]
                            )
                        elif "_shap_sel_idx" not in st.session_state:
                            st.session_state["_shap_sel_idx"] = 0

                    st.markdown("---")
                    st.subheader("🔍 Waterfall SHAP do Intervalo")
                    if shap_vals is not None:
                        expected_value, shap_features, shap_matrix, target_trans = shap_vals
                        shap_idx = st.session_state["_shap_sel_idx"]
                        if shap_matrix.shape[0] == len(df_prog):
                            row_shap = shap_matrix[shap_idx]
                            pred_transform = float(expected_value + row_shap.sum())
                            if target_trans:
                                pred_ns = float(1.0 - np.expm1(pred_transform))
                            else:
                                pred_ns = pred_transform
                            row_info = df_prog.iloc[shap_idx]
                            inicio = row_info.get("Intervalo_Inicio", row_info.get("Intervalo", ""))
                            fim = row_info.get("Intervalo_Fim", "")
                            if inicio and fim:
                                row_label = f"{row_info['DataRef']} {inicio}-{fim}"
                            else:
                                row_label = f"{row_info['DataRef']} {inicio}"
                            feat_val_pairs = sorted(
                                zip(shap_features, row_shap),
                                key=lambda x: abs(x[1]), reverse=True,
                            )
                            top_feats = feat_val_pairs[:15]
                            top_names = [f[0] for f in top_feats]
                            top_vals = [f[1] for f in top_feats]

                            if len(feat_val_pairs) > 15:
                                soma_outros = sum([f[1] for f in feat_val_pairs[15:]])
                                top_names.append("Outros (demais features)")
                                top_vals.append(soma_outros)

                            labels = top_names + ["Modelo (base + Σ SHAP)"]
                            measures = ["relative"] * len(top_names) + ["total"]
                            y_vals = list(top_vals) + [pred_transform]

                            fig_wf = go.Figure(go.Waterfall(
                                orientation="v",
                                measure=measures,
                                x=labels,
                                y=y_vals,
                                base=expected_value,
                                text=[f"{v:+.4f}" for v in top_vals] + [f"{pred_ns:.4f}"],
                                textposition="outside",
                                connector={"line": {"color": "lightgray", "width": 1}},
                            ))
                            # Waterfall não aceita marker no construtor; aplica cores via update_traces
                            fig_wf.update_traces(
                                increasing=dict(marker=dict(color="#F44336")),
                                decreasing=dict(marker=dict(color="#4CAF50")),
                                totals=dict(marker=dict(color="#2196F3")),
                            )
                            fig_wf.update_layout(
                                title=f"Waterfall SHAP — {row_label}",
                                height=450,
                                margin=dict(l=10, r=10, t=50, b=120),
                                xaxis_tickangle=-45,
                                showlegend=False,
                            )
                            st.plotly_chart(fig_wf, use_container_width=True)
                            st.caption(
                                f"**Base** = {expected_value:.4f} (valor médio esperado pelo modelo).<br>"
                                f"**Barras verdes (negativas)** indicam features que reduzem o valor do modelo, o que **AUMENTA o NS**.<br>"
                                f"**Barras vermelhas (positivas)** indicam features que aumentam o valor do modelo, o que **REDUZ o NS**.<br>"
                                + (
                                    f"**Modelo (espaço transformado)** = {pred_transform:.4f} → "
                                    f"**NS** = 1 − expm1({pred_transform:.4f}) = **{pred_ns:.4f}**<br>"
                                    if target_trans
                                    else f"**NS** = {pred_transform:.4f}"
                                ),
                                unsafe_allow_html=True
                            )
                        else:
                            st.warning(
                                f"Número de registros ({len(df_prog)}) não corresponde "
                                f"ao SHAP salvo ({shap_matrix.shape[0]}). Reexecute o benchmark."
                            )
                    else:
                        st.info("Dados SHAP não disponíveis. Execute um novo benchmark para habilitar esta análise.")

# ==============================================================================
# TAB 4 - HISTÓRICO
# ==============================================================================
with tab4:
    st.subheader("Evolução das Métricas ao Longo do Tempo")

    df_evo = dl.get_evolution_data()
    if df_evo.empty:
        st.info("Apenas uma execução encontrada. Execute mais benchmarks para ver o histórico evoluir.")
    else:
        st.markdown(f"{len(df_evo)} execuções registradas.")

        col_filtro1, col_filtro2, _ = st.columns([2, 2, 2])
        with col_filtro1:
            dias_hist = st.multiselect(
                "Filtrar por dias",
                options=sorted(df_evo["dias"].unique()),
                default=sorted(df_evo["dias"].unique()),
            )
        with col_filtro2:
            programas_hist = dl.get_programas_comuns()
            def _fmt_prog_hist(p):
                if p == "📊 Geral":
                    return p
                nome = dl.get_nome_programa(p)
                return f"{p} — {nome}" if nome else p

            prog_opcoes = ["📊 Geral"] + [str(p) for p in programas_hist]
            prog_sel = st.selectbox("Filtrar por programa", options=prog_opcoes, format_func=_fmt_prog_hist)

        df_filtrado = df_evo[df_evo["dias"].isin(dias_hist)] if dias_hist else df_evo

        if prog_sel != "📊 Geral":
            df_prog_evo = dl.get_evolution_data_por_programa()
            df_prog_evo = df_prog_evo[df_prog_evo["dias"].isin(dias_hist)] if dias_hist else df_prog_evo
            df_prog_evo = df_prog_evo[df_prog_evo["programa"] == int(prog_sel)]

            if len(df_prog_evo) >= 2:
                nome_prog = dl.get_nome_programa(prog_sel)
                titulo = f"{prog_sel} — {nome_prog}" if nome_prog else prog_sel
                st.markdown(f"### {titulo} — MAE ao Longo do Tempo")
                fig_mae = go.Figure()
                for dias_val in sorted(df_prog_evo["dias"].unique()):
                    df_d = df_prog_evo[df_prog_evo["dias"] == dias_val]
                    fig_mae.add_trace(go.Scatter(x=df_d["data_execucao"], y=df_d["MAE_SmartCorr"],
                        mode="lines+markers", name=f"SmartCorr ({dias_val}d)", line=dict(width=2)))
                    fig_mae.add_trace(go.Scatter(x=df_d["data_execucao"], y=df_d["MAE_WFM"],
                        mode="lines+markers", name=f"WFM ({dias_val}d)", line=dict(dash="dash", width=1.5)))
                fig_mae.update_layout(height=350, hovermode="x unified")
                st.plotly_chart(fig_mae, use_container_width=True)

                st.markdown(f"### {titulo} — Uplift % ao Longo do Tempo")
                fig_up = go.Figure()
                for dias_val in sorted(df_prog_evo["dias"].unique()):
                    df_d = df_prog_evo[df_prog_evo["dias"] == dias_val]
                    fig_up.add_trace(go.Scatter(x=df_d["data_execucao"], y=df_d["Uplift_MAE_pct"],
                        mode="lines+markers", name=f"{dias_val}d", line=dict(width=2)))
                fig_up.add_hline(y=0, line_color="gray", line_dash="dot")
                fig_up.update_layout(height=300, hovermode="x unified")
                st.plotly_chart(fig_up, use_container_width=True)
            else:
                st.info("Precisa de pelo menos 2 execuções com este programa para mostrar evolução.")
        else:
            if len(df_filtrado) >= 2:
                st.markdown("### MAE ao Longo do Tempo")
                fig_mae = go.Figure()
                for dias_val in sorted(df_filtrado["dias"].unique()):
                    df_d = df_filtrado[df_filtrado["dias"] == dias_val]
                    fig_mae.add_trace(go.Scatter(x=df_d["data_execucao"], y=df_d["MAE_SmartCorr"],
                        mode="lines+markers", name=f"SmartCorr ({dias_val}d)", line=dict(width=2)))
                    fig_mae.add_trace(go.Scatter(x=df_d["data_execucao"], y=df_d["MAE_WFM"],
                        mode="lines+markers", name=f"WFM ({dias_val}d)", line=dict(dash="dash", width=1.5)))
                fig_mae.update_layout(height=350, hovermode="x unified")
                st.plotly_chart(fig_mae, use_container_width=True)

                st.markdown("### Uplift % ao Longo do Tempo")
                fig_up = go.Figure()
                for dias_val in sorted(df_filtrado["dias"].unique()):
                    df_d = df_filtrado[df_filtrado["dias"] == dias_val]
                    fig_up.add_trace(go.Scatter(x=df_d["data_execucao"], y=df_d["Uplift_MAE_pct"],
                        mode="lines+markers", name=f"{dias_val}d", line=dict(width=2)))
                fig_up.add_hline(y=0, line_color="gray", line_dash="dot")
                fig_up.update_layout(height=300, hovermode="x unified")
                st.plotly_chart(fig_up, use_container_width=True)
            else:
                st.info("Precisa de pelo menos 2 execuções com o mesmo período para mostrar evolução.")

        st.markdown("---")
        st.subheader("Todas as Execuções")

        df_exibir = df_filtrado.copy()
        if not df_exibir.empty:
            df_exibir["data_execucao"] = df_exibir["data_execucao"].dt.strftime("%Y-%m-%d %H:%M")
            cols_exibir = ["data_execucao", "dias", "total_intervalos",
                           "MAE_SmartCorr", "MAE_WFM", "R2_SmartCorr", "Uplift_MAE_pct"]
            df_tabela = df_exibir[cols_exibir].rename(columns={
                "data_execucao": "Data", "dias": "Dias", "total_intervalos": "Intervalos",
                "MAE_SmartCorr": "MAE SC", "MAE_WFM": "MAE WFM",
                "R2_SmartCorr": "R² SC", "Uplift_MAE_pct": "Uplift %",
            })
            st.dataframe(df_tabela, use_container_width=True, hide_index=True)

            csv_hist = df_tabela.to_csv(index=False)
            st.download_button("📥 Download Histórico CSV", csv_hist,
                               "historico_benchmark.csv", "text/csv")

# ==============================================================================
# TAB 5 - GLOSSÁRIO
# ==============================================================================
with tab5:
    st.subheader("📖 Glossário de Variáveis e Pilares")
    st.markdown("""
    Nesta seção, detalhamos as principais *features* utilizadas pelo SmartCorr, divididas por Pilares Analíticos.
    
    ### 🔄 A Matemática do Nível de Serviço (NS)
    `NS = 1 - expm1(Predição do Modelo)`
    
    * **Impacto Positivo (Vermelho):** Aumenta o valor do modelo → **REDUZ o NS**.
    * **Impacto Negativo (Verde):** Reduz o valor do modelo → **AUMENTA o NS**.

    ---

    ### 📦 Pilares e Features

    #### 1. Volumetria (Demanda)
    | Feature | Descrição | Fórmula / Origem |
    | :--- | :--- | :--- |
    | `Vol_Previsto` | Volume planejado/previsto de contatos. | Forecast Planejamento |
    | `Desvio_Volume_Pct_Lag_1` | Desvio percentual do volume no intervalo anterior. | `(Vol_Real - Vol_Prev) / Vol_Prev` |

    #### 2. Pessoas (Headcount & Perdas)
    | Feature | Descrição | Fórmula / Origem |
    | :--- | :--- | :--- |
    | `HC_Previsto` | Agentes escalados para o intervalo. | Escala Planejamento |
    | `ABS_Taxa_Daily` | Taxa de absenteísmo diária observada. | `Tempo_Faltas / Tempo_Escala` |
    | `Turnover_Taxa_Daily` | Taxa de rotatividade diária. | `Desligados / Ativos` |
    | `PerdaLog_Taxa_Daily` | Perda por problemas de login/acesso. | `Tempo_Perda_Log / PPH_Total` |
    | `NewHire_Pct_Daily` | Proporção de operadores em curva de aprendizado. | `HC_Novatos / HC_Total` |

    #### 3. TMA (Tempo de Atendimento)
    | Feature | Descrição | Fórmula / Origem |
    | :--- | :--- | :--- |
    | `Tempo_AHT_Prev_Total` | TMA planejado para o intervalo. | Meta Planejamento |
    | `TME_Real_Avg_Lag_1` | Tempo Médio de Espera no intervalo anterior. | Realizado (Histórico) |
    | `Delta_TMA_Lag_1` | Desvio de TMA ocorrido no intervalo anterior. | `TMA_Real - TMA_Prev` |

    #### 4. Saúde Operacional (Indicadores de Pressão)
    | Feature | Descrição | Fórmula / Cálculo |
    | :--- | :--- | :--- |
    | `Pressao_Prev_Vol_HC` | Razão de volume por agente escalado. | `Vol_Previsto / HC_Previsto` |
    | `Indicador_Sufoco` | Proporção de carga de trabalho vs capacidade. | `AHT_Prev_Total / (HC_Prev * 1800)` |
    | `Margem_Capacidade` | Percentual de folga/falta de capacidade. | `(Capac_Teorica - Vol_Prev) / Capac_Teorica` |
    | `Ocupacao_Sintetica` | Estimativa de ocupação baseada no forecast. | `(Vol_Prev * AHT_Prev) / (HC_Prev * 1800)` |
    | `Vol_Por_Agente` | Quantidade de chamadas por operador. | `Vol_Previsto / HC_Previsto` |

    #### 5. Contexto (Temporal & Operacional)
    | Feature | Descrição | Tipo |
    | :--- | :--- | :--- |
    | `Hora / DiaSemana` | Sazonalidade horária e diária. | Categórica |
    | `Is_Inicio_Fim_Mes` | Período de pico sistêmico (Dias 1-5 e 26-31). | Binária (0/1) |
    | `Meta_Intervalo_SLA` | Objetivo de Nível de Serviço contratual. | Constante/Parâmetro |
    | `NS_Media_Movel_6` | Tendência do NS nas últimas 3 horas. | Média Móvel |
    """)

st.sidebar.image("images/logo_TP-transparente.png", width=200)
st.sidebar.markdown("### SmartCorr Benchmark")
st.sidebar.divider()
st.sidebar.markdown(f"**{len(runs_df)} execução(ões) no total**")
st.sidebar.caption(f"SmartCorr Benchmark Dashboard • v0.1")
st.sidebar.caption(f"Última atualização: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
