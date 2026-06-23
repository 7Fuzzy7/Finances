from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from src.finance_engine import (
    aggregate_metrics,
    category_table,
    daily_cashflow,
    format_brl,
    load_many,
    make_suggestions,
    merchant_table,
    monthly_table,
)
from src.styles import APP_CSS

st.set_page_config(
    page_title="OpenFinance Dashboard BR",
    page_icon="💸",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(APP_CSS, unsafe_allow_html=True)


def metric_card(label: str, value: str, help_text: str = ""):
    st.markdown(
        f"""
        <div class="metric-card">
          <div class="metric-label">{label}</div>
          <div class="metric-value">{value}</div>
          <div class="metric-help">{help_text}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def plot_layout(fig):
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#EEF3FF"),
        margin=dict(l=20, r=20, t=45, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=-0.25, xanchor="center", x=0.5),
    )
    return fig


with st.sidebar:
    st.title("💸 Finance BR")
    st.caption("Dashboard financeiro pessoal a partir de CSV. Nada é enviado para banco de dados por padrão.")
    uploaded_files = st.file_uploader(
        "Suba um ou mais CSVs",
        type=["csv"],
        accept_multiple_files=True,
        help="Compatível com CSVs no padrão: date,title,amount ou data,descricao,valor.",
    )
    st.divider()
    st.subheader("Configuração pessoal")
    renda_mensal = st.number_input("Renda mensal líquida", min_value=0.0, value=0.0, step=100.0, format="%.2f")
    meta_economia = st.slider("Meta de economia mensal", min_value=0, max_value=50, value=20, step=5) / 100
    st.caption("Dica: informe renda líquida real para o diagnóstico ficar melhor.")
    st.divider()
    st.subheader("Filtros")
    show_raw = st.toggle("Mostrar dados tratados", value=False)

st.markdown(
    """
    <div class="hero">
      <h1>OpenFinance Dashboard BR</h1>
      <p>Suba o CSV do banco/cartão e receba um painel visual, simples e autoexplicativo com diagnóstico, categorias, parcelas, alertas e próximos passos.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

if not uploaded_files:
    c1, c2 = st.columns([1.2, .8])
    with c1:
        st.subheader("Como usar")
        st.markdown(
            """
            1. Exporte o CSV da sua conta ou fatura no app do banco.
            2. Suba o arquivo no menu lateral.
            3. Informe sua renda mensal líquida.
            4. Veja o diagnóstico e siga o plano de ação.
            """
        )
        st.info("Este app é educativo. Ele não substitui consultoria financeira, contábil ou de investimentos.")
    with c2:
        st.markdown(
            """
            <div class="insight-card">
              <div class="insight-title">Privacidade primeiro</div>
              <div class="insight-text">Na versão local, o arquivo é processado na sua máquina. Não há login, nuvem ou banco de dados obrigatório.</div>
            </div>
            <div class="insight-card">
              <div class="insight-title">Compatível com leigos</div>
              <div class="insight-text">O painel evita termos difíceis e transforma CSV em decisões práticas.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    st.stop()

try:
    df = load_many(uploaded_files)
except Exception as exc:
    st.error(str(exc))
    st.stop()

if df.empty:
    st.warning("Não encontrei transações válidas nos arquivos enviados.")
    st.stop()

# Filters after load
min_date, max_date = df["data"].min().date(), df["data"].max().date()
with st.sidebar:
    date_range = st.date_input("Período", value=(min_date, max_date), min_value=min_date, max_value=max_date)
    categories = sorted(df["categoria"].dropna().unique().tolist())
    selected_categories = st.multiselect("Categorias", categories, default=categories)

if isinstance(date_range, tuple) and len(date_range) == 2:
    start, end = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
    df = df[(df["data"] >= start) & (df["data"] <= end)]
if selected_categories:
    df = df[df["categoria"].isin(selected_categories)]

metrics = aggregate_metrics(df, renda_mensal=renda_mensal, meta_economia=meta_economia)

k1, k2, k3, k4, k5 = st.columns(5)
with k1:
    metric_card("Gastos líquidos", format_brl(metrics["gasto_liquido"]), "Compras menos estornos")
with k2:
    metric_card("Saldo estimado", format_brl(metrics["saldo_estimado"]), "Renda informada - gastos")
with k3:
    metric_card("Score financeiro", f"{metrics['score']}/100", "Quanto maior, melhor")
with k4:
    metric_card("Maior categoria", metrics["top_category"], "Onde o dinheiro mais saiu")
with k5:
    metric_card("Parcelas futuras", format_brl(metrics["parcelas_futuras"]), "Compromisso aproximado")

st.write("")
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📊 Visão geral", "🏷️ Categorias", "🧾 Gastos", "🔁 Parcelas e recorrentes", "🧠 Diagnóstico", "📄 Dados"
])

with tab1:
    left, right = st.columns([1.1, .9])
    cat = category_table(df)
    month = monthly_table(df)
    with left:
        st.markdown('<div class="section-title">Gastos por categoria</div>', unsafe_allow_html=True)
        if not cat.empty:
            fig = px.pie(cat, names="categoria", values="valor", hole=.52)
            st.plotly_chart(plot_layout(fig), use_container_width=True)
        else:
            st.info("Sem gastos para exibir.")
    with right:
        st.markdown('<div class="section-title">Resumo por mês</div>', unsafe_allow_html=True)
        if not month.empty:
            fig = px.bar(month, x="mes", y=["gastos", "entradas", "estornos"], barmode="group")
            st.plotly_chart(plot_layout(fig), use_container_width=True)
        else:
            st.info("Sem meses para exibir.")

    st.markdown('<div class="section-title">Fluxo acumulado no período</div>', unsafe_allow_html=True)
    cash = daily_cashflow(df)
    if not cash.empty:
        fig = px.line(cash, x="data", y="saldo_acumulado", markers=True)
        st.plotly_chart(plot_layout(fig), use_container_width=True)

with tab2:
    cat = category_table(df)
    st.markdown('<div class="section-title">Ranking de categorias</div>', unsafe_allow_html=True)
    if not cat.empty:
        display = cat.copy()
        display["valor"] = display["valor"].map(format_brl)
        display["participacao"] = display["participacao"].map(lambda x: f"{x:.1%}")
        st.dataframe(display, use_container_width=True, hide_index=True)
        fig = px.treemap(cat, path=["categoria"], values="valor")
        st.plotly_chart(plot_layout(fig), use_container_width=True)
    else:
        st.info("Sem categorias no período.")

with tab3:
    st.markdown('<div class="section-title">Maiores gastos identificados</div>', unsafe_allow_html=True)
    merchants = merchant_table(df, limit=20)
    if not merchants.empty:
        table = merchants.copy()
        table["valor"] = table["valor"].map(format_brl)
        st.dataframe(table, use_container_width=True, hide_index=True)
        fig = px.bar(merchants.sort_values("valor"), x="valor", y="descricao", orientation="h", color="categoria")
        st.plotly_chart(plot_layout(fig), use_container_width=True)
    else:
        st.info("Sem gastos no período.")

with tab4:
    st.markdown('<div class="section-title">Parcelas em aberto e recorrências suspeitas</div>', unsafe_allow_html=True)
    parcelas = df[(df["tipo"] == "Gasto") & (df["eh_parcelado"])].copy()
    recorrentes = df[(df["tipo"] == "Gasto") & (df["recorrente_suspeito"])].copy()
    a, b = st.columns(2)
    with a:
        st.subheader("Parcelados")
        if not parcelas.empty:
            tmp = parcelas[["data", "descricao", "categoria", "valor", "parcela_atual", "parcela_total"]].copy()
            tmp["valor"] = tmp["valor"].map(format_brl)
            st.dataframe(tmp, use_container_width=True, hide_index=True)
        else:
            st.success("Nenhuma compra parcelada detectada no período filtrado.")
    with b:
        st.subheader("Recorrentes")
        if not recorrentes.empty:
            tmp = recorrentes[["data", "descricao", "categoria", "valor"]].copy()
            tmp["valor"] = tmp["valor"].map(format_brl)
            st.dataframe(tmp, use_container_width=True, hide_index=True)
        else:
            st.success("Nenhuma recorrência suspeita detectada.")

with tab5:
    st.markdown('<div class="section-title">Diagnóstico automático</div>', unsafe_allow_html=True)
    suggestions = make_suggestions(df, metrics, renda_mensal=renda_mensal)
    if suggestions:
        for item in suggestions:
            st.markdown(
                f"""
                <div class="insight-card">
                  <div class="impact">Impacto: {item['impacto']}</div>
                  <div class="insight-title">{item['titulo']}</div>
                  <div class="insight-text"><b>Ação:</b> {item['acao']}</div>
                  <div class="insight-text"><b>Por quê:</b> {item['motivo']}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    st.warning("As sugestões são educativas e baseadas nos dados enviados. Para investimentos específicos, consulte fontes oficiais e avalie seu perfil de risco.")

with tab6:
    st.markdown('<div class="section-title">Dados tratados</div>', unsafe_allow_html=True)
    export_df = df.copy()
    export_df["data"] = export_df["data"].dt.strftime("%Y-%m-%d")
    if show_raw:
        st.dataframe(export_df, use_container_width=True, hide_index=True)
    csv = export_df.to_csv(index=False).encode("utf-8-sig")
    st.download_button("Baixar CSV tratado", data=csv, file_name="financas_tratadas.csv", mime="text/csv")
