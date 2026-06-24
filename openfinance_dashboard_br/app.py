from __future__ import annotations

from pathlib import Path
import sys

# Streamlit Cloud executa o app a partir da raiz do repositório.
# Como este app fica dentro da pasta openfinance_dashboard_br/, garantimos
# que os módulos locais em openfinance_dashboard_br/src sejam encontrados.
APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import pandas as pd
import plotly.express as px
import streamlit as st

from src.finance_engine import (
    ALL_TYPES_ORDER,
    IMPACT_TYPES,
    aggregate_metrics,
    category_table,
    daily_cashflow,
    data_quality_report,
    format_brl,
    installment_table,
    load_many,
    make_suggestions,
    merchant_table,
    monthly_table,
    recurring_table,
    type_summary_table,
)
from src.styles import APP_CSS

st.set_page_config(
    page_title="OpenFinance Dashboard BR",
    page_icon="💸",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(APP_CSS, unsafe_allow_html=True)


def metric_card(label: str, value: str, help_text: str = "", tone: str = ""):
    st.markdown(
        f"""
        <div class="metric-card {tone}">
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
        margin=dict(l=18, r=18, t=44, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=-0.22, xanchor="center", x=0.5),
    )
    return fig


def format_table_money(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    out = df.copy()
    for col in columns:
        if col in out.columns:
            out[col] = out[col].map(format_brl)
    return out


def ordered_types(types: list[str]) -> list[str]:
    order = {name: idx for idx, name in enumerate(ALL_TYPES_ORDER)}
    return sorted(types, key=lambda x: order.get(x, 99))


DEDUPE_LABELS = {
    "Conciliação segura: cancela compra/estorno duplicados": "reconcile",
    "Remover duplicatas idênticas": "exact",
    "Não deduplicar": "none",
}

with st.sidebar:
    st.title("💸 Finance BR")
    st.caption("Dashboard financeiro pessoal a partir de CSV. Privacidade primeiro: sem banco de dados obrigatório.")

    uploaded_files = st.file_uploader(
        "Suba um ou mais CSVs",
        type=["csv"],
        accept_multiple_files=True,
        help="Compatível com CSVs no padrão: date,title,amount ou data,descricao,valor.",
    )

    st.divider()
    st.subheader("Tratamento dos dados")
    dedupe_label = st.selectbox(
        "Deduplicação",
        list(DEDUPE_LABELS.keys()),
        index=0,
        help=(
            "A opção segura resolve casos como 3 cobranças e 2 estornos iguais, mantendo só o impacto líquido. "
            "Use 'Não deduplicar' para auditoria linha a linha."
        ),
    )
    dedupe_mode = DEDUPE_LABELS[dedupe_label]

    st.divider()
    st.subheader("Configuração pessoal")
    renda_mensal = st.number_input("Renda mensal líquida", min_value=0.0, value=0.0, step=100.0, format="%.2f")
    meta_economia = st.slider("Meta de economia mensal", min_value=0, max_value=50, value=20, step=5) / 100
    st.caption("Dica: informe renda líquida real para o diagnóstico ficar melhor.")

    st.divider()
    show_raw = st.toggle("Mostrar tabela completa", value=False)

st.markdown(
    """
    <div class="hero">
      <div class="hero-badge">Versão 2 • engine corrigido</div>
      <h1>OpenFinance Dashboard BR</h1>
      <p>Suba o CSV do banco ou cartão e receba um painel visual, simples e autoexplicativo com diagnóstico, categorias, parcelas, alertas e próximos passos.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

if not uploaded_files:
    c1, c2 = st.columns([1.15, .85])
    with c1:
        st.subheader("Como usar")
        st.markdown(
            """
            1. Exporte o CSV da fatura, cartão ou conta no app do banco.  
            2. Suba o arquivo no menu lateral.  
            3. Informe sua renda mensal líquida.  
            4. Veja o diagnóstico, parcelas, categorias e sugestões práticas.
            """
        )
        st.info("O app é educativo. Ele não substitui consultoria financeira, contábil ou recomendação profissional de investimentos.")
    with c2:
        st.markdown(
            """
            <div class="insight-card">
              <div class="insight-title">Correções importantes da v2</div>
              <div class="insight-text">Pagamentos de fatura ficam ignorados, duplicidades compra/estorno são conciliadas e PIX só vira transferência quando a descrição indica transferência real.</div>
            </div>
            <div class="insight-card">
              <div class="insight-title">Para pessoa leiga</div>
              <div class="insight-text">O painel traduz o CSV em cartões, gráficos, avisos e próximos passos sem exigir conhecimento financeiro ou Excel.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    st.stop()

try:
    raw_df = load_many(uploaded_files, dedupe_mode=dedupe_mode)
except Exception as exc:
    st.error(str(exc))
    st.stop()

if raw_df.empty:
    st.warning("Não encontrei transações válidas nos arquivos enviados.")
    st.stop()

quality = data_quality_report(raw_df)

# Sidebar filters after loading
min_date, max_date = raw_df["data"].min().date(), raw_df["data"].max().date()
with st.sidebar:
    st.subheader("Filtros do dashboard")
    date_range = st.date_input("Período", value=(min_date, max_date), min_value=min_date, max_value=max_date)

    all_categories = sorted(raw_df["categoria"].dropna().unique().tolist())
    selected_categories = st.multiselect("Categorias", all_categories, default=all_categories)

    all_types = ordered_types(raw_df["tipo"].dropna().unique().tolist())
    default_types = [t for t in all_types if t != "Ignorado"]
    selected_types = st.multiselect(
        "Tipos incluídos nos totais",
        all_types,
        default=default_types,
        help="Por padrão, pagamentos de fatura e transferências ficam fora para evitar duplicidade e distorção.",
    )

filtered_df = raw_df.copy()
if isinstance(date_range, tuple) and len(date_range) == 2:
    start, end = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1]) + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)
    filtered_df = filtered_df[(filtered_df["data"] >= start) & (filtered_df["data"] <= end)]
if selected_categories:
    filtered_df = filtered_df[filtered_df["categoria"].isin(selected_categories)]

analysis_df = filtered_df[filtered_df["tipo"].isin(selected_types)].copy() if selected_types else filtered_df.iloc[0:0].copy()
metrics = aggregate_metrics(analysis_df, renda_mensal=renda_mensal, meta_economia=meta_economia)

# Data quality strip
if quality.get("removed_rows", 0) > 0 or quality.get("payment_count", 0) > 0:
    st.markdown(
        f"""
        <div class="quality-strip">
          <b>Qualidade dos dados:</b> {quality.get('removed_rows', 0)} linha(s) duplicada(s)/conciliada(s) removida(s) •
          {quality.get('payment_count', 0)} pagamento(s) de fatura ignorado(s) •
          {quality.get('installment_count', 0)} parcela(s) detectada(s).
        </div>
        """,
        unsafe_allow_html=True,
    )

k1, k2, k3, k4, k5 = st.columns(5)
with k1:
    metric_card("Gastos líquidos", format_brl(metrics["gasto_liquido"]), "Compras menos estornos")
with k2:
    metric_card("Saldo estimado", format_brl(metrics["saldo_estimado"]), "Renda informada - gastos", "positive" if metrics["saldo_estimado"] >= 0 else "negative")
with k3:
    metric_card("Score financeiro", f"{metrics['score']}/100", "Quanto maior, melhor")
with k4:
    metric_card("Maior categoria", metrics["top_category"], "Onde o dinheiro mais saiu")
with k5:
    metric_card("Parcelas futuras", format_brl(metrics["parcelas_futuras"]), "Compromisso aproximado")

st.write("")
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "📊 Visão geral", "🏷️ Categorias", "🧾 Gastos", "🔁 Parcelas", "🧠 Diagnóstico", "🧪 Qualidade", "📄 Dados"
])

with tab1:
    left, right = st.columns([1.1, .9])
    cat = category_table(analysis_df)
    month = monthly_table(analysis_df)

    with left:
        st.markdown('<div class="section-title">Gastos líquidos por categoria</div>', unsafe_allow_html=True)
        if not cat.empty:
            fig = px.pie(cat, names="categoria", values="valor", hole=.54)
            st.plotly_chart(plot_layout(fig), use_container_width=True)
        else:
            st.info("Sem gastos para exibir com os filtros atuais.")

    with right:
        st.markdown('<div class="section-title">Resumo mensal</div>', unsafe_allow_html=True)
        if not month.empty:
            fig = px.bar(month, x="mes", y=["gastos", "entradas", "estornos"], barmode="group")
            st.plotly_chart(plot_layout(fig), use_container_width=True)
        else:
            st.info("Sem meses para exibir.")

    st.markdown('<div class="section-title">Fluxo de impacto no orçamento</div>', unsafe_allow_html=True)
    cash = daily_cashflow(analysis_df)
    if not cash.empty:
        fig = px.line(cash, x="data", y="saldo_acumulado", markers=True)
        st.plotly_chart(plot_layout(fig), use_container_width=True)

with tab2:
    cat = category_table(analysis_df)
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
    merchants = merchant_table(analysis_df, limit=25)
    if not merchants.empty:
        table = format_table_money(merchants, ["valor"])
        st.dataframe(table, use_container_width=True, hide_index=True)
        fig = px.bar(merchants.sort_values("valor"), x="valor", y="descricao", orientation="h", color="categoria")
        st.plotly_chart(plot_layout(fig), use_container_width=True)
    else:
        st.info("Sem gastos no período.")

with tab4:
    st.markdown('<div class="section-title">Parcelas em aberto e recorrências suspeitas</div>', unsafe_allow_html=True)
    parcelas = installment_table(analysis_df)
    recorrentes = recurring_table(analysis_df)
    a, b = st.columns(2)
    with a:
        st.subheader("Parcelados")
        if not parcelas.empty:
            tmp = format_table_money(parcelas, ["valor_parcela", "valor_futuro"])
            st.dataframe(tmp, use_container_width=True, hide_index=True)
        else:
            st.success("Nenhuma compra parcelada detectada no período filtrado.")
    with b:
        st.subheader("Recorrentes")
        if not recorrentes.empty:
            tmp = format_table_money(recorrentes, ["valor"])
            st.dataframe(tmp, use_container_width=True, hide_index=True)
        else:
            st.success("Nenhuma recorrência suspeita detectada.")

with tab5:
    st.markdown('<div class="section-title">Diagnóstico automático</div>', unsafe_allow_html=True)
    suggestions = make_suggestions(analysis_df, metrics, renda_mensal=renda_mensal)
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
    else:
        st.info("Sem sugestões com os filtros atuais.")
    st.warning("As sugestões são educativas. Para investimentos específicos, avalie seu perfil de risco e consulte fontes/profissionais adequados.")

with tab6:
    st.markdown('<div class="section-title">Diagnóstico técnico dos dados</div>', unsafe_allow_html=True)
    q1, q2, q3, q4 = st.columns(4)
    with q1:
        metric_card("Linhas originais", str(quality.get("original_rows", len(raw_df))), "Antes do tratamento")
    with q2:
        metric_card("Linhas finais", str(quality.get("final_rows", len(raw_df))), "Após tratamento")
    with q3:
        metric_card("Ajustes", str(quality.get("groups_adjusted", 0)), "Grupos corrigidos")
    with q4:
        metric_card("Ignorados", str(quality.get("ignored_count", 0)), "Fatura/itens não orçamentários")

    st.subheader("Resumo por tipo")
    type_table = type_summary_table(filtered_df)
    if not type_table.empty:
        type_table = format_table_money(type_table, ["valor_abs"])
        st.dataframe(type_table, use_container_width=True, hide_index=True)

    ignored = filtered_df[filtered_df["tipo"].eq("Ignorado")].copy()
    if not ignored.empty:
        st.subheader("Lançamentos ignorados")
        tmp = ignored[["data", "descricao", "subtipo", "valor", "arquivo"]].copy()
        tmp["data"] = tmp["data"].dt.strftime("%Y-%m-%d")
        tmp["valor"] = tmp["valor"].map(format_brl)
        st.dataframe(tmp, use_container_width=True, hide_index=True)

with tab7:
    st.markdown('<div class="section-title">Dados tratados</div>', unsafe_allow_html=True)
    export_df = filtered_df.copy()
    export_df["data"] = export_df["data"].dt.strftime("%Y-%m-%d")
    hide_cols = ["descricao_norm", "chave_parcela"]
    export_view = export_df.drop(columns=[c for c in hide_cols if c in export_df.columns], errors="ignore")
    if show_raw:
        st.dataframe(export_view, use_container_width=True, hide_index=True)
    else:
        st.caption("Ative 'Mostrar tabela completa' no menu lateral para visualizar tudo aqui.")
    csv = export_view.to_csv(index=False).encode("utf-8-sig")
    st.download_button("Baixar CSV tratado", data=csv, file_name="financas_tratadas_v2.csv", mime="text/csv")
