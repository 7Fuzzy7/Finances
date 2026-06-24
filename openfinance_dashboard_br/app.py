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
    TYPE_TRANSFER_RECEIVED,
    TYPE_TRANSFER_SENT,
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
    detect_csv_source_type,
)
from src.styles import APP_CSS

st.set_page_config(
    page_title="Meu Plano Financeiro BR",
    page_icon="💸",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(APP_CSS, unsafe_allow_html=True)


# -----------------------------
# UI helpers
# -----------------------------
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


def insight_card(title: str, text: str, impact: str = "Plano"):
    st.markdown(
        f"""
        <div class="insight-card">
          <div class="impact">{impact}</div>
          <div class="insight-title">{title}</div>
          <div class="insight-text">{text}</div>
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


def pct(value: float) -> str:
    return f"{value:.1%}" if pd.notna(value) else "-"


def build_empty_df() -> pd.DataFrame:
    cols = [
        "data", "descricao", "descricao_norm", "valor", "arquivo", "tipo", "subtipo", "categoria",
        "valor_abs", "valor_impacto", "mes", "dia", "parcela_atual", "parcela_total", "eh_parcelado",
        "chave_parcela", "recorrente_suspeito", "ignorar_no_orcamento", "dedup_status",
    ]
    return pd.DataFrame(columns=cols)


def clamp(value: float, minimum: float = 0.0, maximum: float | None = None) -> float:
    out = max(float(value or 0), minimum)
    if maximum is not None:
        out = min(out, maximum)
    return out


def plan_financeiro(
    *,
    profissao: str,
    salario_liquido: float,
    adiantamento: float,
    renda_extra: float,
    beneficios: float,
    incluir_beneficios: bool,
    saldo_conta: float,
    gastos_analisados: float,
    gastos_fixos_fora_csv: float,
    reserva_atual: float,
    custo_essencial: float,
    meses_reserva_saudavel: int,
    aporte_reserva_manual: float,
    aporte_investimento_manual: float,
    buffer_seguranca: float,
) -> dict:
    renda_planejavel = float(salario_liquido or 0) + float(adiantamento or 0) + float(renda_extra or 0)
    if incluir_beneficios:
        renda_planejavel += float(beneficios or 0)

    gastos_mensais = float(gastos_analisados or 0) + float(gastos_fixos_fora_csv or 0)
    saldo_livre_pos_fatura = float(saldo_conta or 0) - float(gastos_analisados or 0)

    reserva_minima = float(custo_essencial or 0) * 3
    reserva_saudavel = float(custo_essencial or 0) * int(meses_reserva_saudavel or 6)
    falta_reserva_minima = max(reserva_minima - float(reserva_atual or 0), 0.0)
    falta_reserva_saudavel = max(reserva_saudavel - float(reserva_atual or 0), 0.0)

    sobra_antes_planejamento = renda_planejavel - gastos_mensais
    aporte_reserva = float(aporte_reserva_manual or 0)
    aporte_investimento = float(aporte_investimento_manual or 0)
    dinheiro_para_mim = renda_planejavel - gastos_mensais - aporte_reserva - aporte_investimento - float(buffer_seguranca or 0)

    if reserva_atual < reserva_minima:
        fase = "1. Montar reserva mínima"
        aporte_reserva_sugerido = min(max(renda_planejavel * 0.20, 300.0), max(sobra_antes_planejamento - buffer_seguranca, 0.0))
        aporte_investimento_sugerido = 0.0
    elif reserva_atual < reserva_saudavel:
        fase = "2. Acelerar reserva saudável"
        aporte_reserva_sugerido = min(max(renda_planejavel * 0.15, 250.0), max(sobra_antes_planejamento - buffer_seguranca, 0.0))
        aporte_investimento_sugerido = min(max(renda_planejavel * 0.05, 50.0), max(sobra_antes_planejamento - aporte_reserva_sugerido - buffer_seguranca, 0.0))
    else:
        fase = "3. Investir com consistência"
        aporte_reserva_sugerido = min(renda_planejavel * 0.05, max(sobra_antes_planejamento - buffer_seguranca, 0.0))
        aporte_investimento_sugerido = min(max(renda_planejavel * 0.10, 100.0), max(sobra_antes_planejamento - aporte_reserva_sugerido - buffer_seguranca, 0.0))

    gasto_pessoal_sugerido = max(sobra_antes_planejamento - aporte_reserva_sugerido - aporte_investimento_sugerido - buffer_seguranca, 0.0)

    comprometimento = (gastos_mensais / renda_planejavel) if renda_planejavel > 0 else 0.0
    reserva_pct_minima = (reserva_atual / reserva_minima) if reserva_minima > 0 else 0.0
    reserva_pct_saudavel = (reserva_atual / reserva_saudavel) if reserva_saudavel > 0 else 0.0

    return {
        "profissao": profissao.strip() or "Não informado",
        "renda_planejavel": renda_planejavel,
        "beneficios": float(beneficios or 0),
        "saldo_conta": float(saldo_conta or 0),
        "gastos_analisados": float(gastos_analisados or 0),
        "gastos_fixos_fora_csv": float(gastos_fixos_fora_csv or 0),
        "gastos_mensais": gastos_mensais,
        "saldo_livre_pos_fatura": saldo_livre_pos_fatura,
        "reserva_atual": float(reserva_atual or 0),
        "custo_essencial": float(custo_essencial or 0),
        "reserva_minima": reserva_minima,
        "reserva_saudavel": reserva_saudavel,
        "falta_reserva_minima": falta_reserva_minima,
        "falta_reserva_saudavel": falta_reserva_saudavel,
        "sobra_antes_planejamento": sobra_antes_planejamento,
        "aporte_reserva": aporte_reserva,
        "aporte_investimento": aporte_investimento,
        "buffer_seguranca": float(buffer_seguranca or 0),
        "dinheiro_para_mim": dinheiro_para_mim,
        "fase": fase,
        "aporte_reserva_sugerido": aporte_reserva_sugerido,
        "aporte_investimento_sugerido": aporte_investimento_sugerido,
        "gasto_pessoal_sugerido": gasto_pessoal_sugerido,
        "comprometimento": comprometimento,
        "reserva_pct_minima": reserva_pct_minima,
        "reserva_pct_saudavel": reserva_pct_saudavel,
    }


def build_cut_table(cat: pd.DataFrame, renda: float) -> pd.DataFrame:
    if cat.empty:
        return pd.DataFrame(columns=["categoria", "gasto_atual", "teto_sugerido", "economia_sugerida", "acao"])

    actions = {
        "Seguro/Proteção": "Revisar apólices, proteções e parcelas. Não contratar nova proteção até fechar reserva.",
        "Parcelas": "Congelar novas parcelas e priorizar compras à vista pequenas.",
        "Compras": "Criar teto semanal e aguardar 48h antes de comprar.",
        "Assinaturas": "Cancelar o que não usa toda semana.",
        "Combustível": "Definir teto por semana e juntar deslocamentos.",
        "Alimentação": "Separar lazer/alimentação por semana.",
        "Transporte": "Separar saldo fixo de transporte e acompanhar recargas.",
        "Saúde/Farmácia": "Manter essencial, mas verificar duplicidades e compras por impulso.",
    }
    factors = {
        "Seguro/Proteção": 0.15,
        "Parcelas": 0.30,
        "Compras": 0.30,
        "Assinaturas": 0.50,
        "Combustível": 0.15,
        "Alimentação": 0.15,
        "Transporte": 0.10,
        "Saúde/Farmácia": 0.05,
    }
    rows = []
    for _, row in cat.head(10).iterrows():
        categoria = str(row["categoria"])
        valor = float(row["valor"])
        factor = factors.get(categoria, 0.10)
        economia = round(valor * factor, 2)
        if valor < 30 and categoria not in {"Assinaturas"}:
            economia = 0.0
        teto = max(valor - economia, 0.0)
        rows.append({
            "categoria": categoria,
            "gasto_atual": valor,
            "teto_sugerido": teto,
            "economia_sugerida": economia,
            "acao": actions.get(categoria, "Definir teto mensal e acompanhar semanalmente."),
        })

    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values("economia_sugerida", ascending=False).reset_index(drop=True)
    return out


DEDUPE_LABELS = {
    "Conciliação segura: cancela compra/estorno duplicados": "reconcile",
    "Remover duplicatas idênticas": "exact",
    "Não deduplicar": "none",
}

# -----------------------------
# Sidebar
# -----------------------------
with st.sidebar:
    st.title("💸 Finance BR")
    st.caption("Agora com primeira página de plano financeiro: saldo, reserva, limite pessoal e próximos passos.")

    st.info("💡 Suba a **fatura do cartão** ou o **extrato da conta**. O app identifica automaticamente e evita dupla contagem.", icon=None)
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
    st.subheader("Perfil e renda")
    profissao = st.text_input("Profissão", value="Analista de Suporte de TI")
    salario_liquido = st.number_input("Salário líquido que cai no mês", min_value=0.0, value=1118.00, step=50.0, format="%.2f")
    adiantamento = st.number_input("Adiantamento / vale em dinheiro", min_value=0.0, value=1002.99, step=50.0, format="%.2f")
    renda_extra = st.number_input("Renda extra recorrente", min_value=0.0, value=0.0, step=50.0, format="%.2f")
    beneficios = st.number_input("Benefícios separados, ex.: Flash/VT/VR", min_value=0.0, value=600.00, step=50.0, format="%.2f")
    incluir_beneficios = st.toggle("Contar benefícios como renda livre?", value=False)
    meta_economia = st.slider("Meta de economia mensal", min_value=0, max_value=50, value=20, step=5) / 100

    st.divider()
    st.subheader("Conta, reserva e limites")
    saldo_conta = st.number_input("Saldo atual da conta", min_value=0.0, value=4734.24, step=100.0, format="%.2f")
    reserva_atual = st.number_input("Reserva já separada", min_value=0.0, value=2000.00, step=100.0, format="%.2f")
    custo_essencial = st.number_input("Custo essencial mensal estimado", min_value=0.0, value=1500.00, step=100.0, format="%.2f")
    meses_reserva_saudavel = st.slider("Meses para reserva saudável", min_value=3, max_value=12, value=6, step=1)
    gastos_fixos_fora_csv = st.number_input("Gastos fixos fora do CSV", min_value=0.0, value=0.0, step=50.0, format="%.2f")

    st.divider()
    st.subheader("Plano do mês")
    aporte_reserva_manual = st.number_input("Quanto separar para reserva este mês", min_value=0.0, value=500.00, step=50.0, format="%.2f")
    aporte_investimento_manual = st.number_input("Quanto investir este mês", min_value=0.0, value=0.0, step=50.0, format="%.2f")
    buffer_seguranca = st.number_input("Sobra de segurança / imprevistos", min_value=0.0, value=200.00, step=50.0, format="%.2f")

    st.divider()
    show_raw = st.toggle("Mostrar tabela completa", value=False)

# -----------------------------
# Load files
# -----------------------------
st.markdown(
    """
    <div class="hero">
      <div class="hero-badge">Versão 3 • plano financeiro pessoal</div>
      <h1>Meu Plano Financeiro BR</h1>
      <p>Veja, na primeira página, quanto você tem, quanto está comprometido, quanto guardar em reserva, quanto investir e quanto pode gastar consigo sem bagunçar as contas.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

load_error = None
if uploaded_files:
    try:
        raw_df = load_many(uploaded_files, dedupe_mode=dedupe_mode)
    except Exception as exc:
        raw_df = build_empty_df()
        load_error = str(exc)
else:
    raw_df = build_empty_df()

if load_error:
    st.error(load_error)

csv_source_type = detect_csv_source_type(raw_df) if not raw_df.empty else "desconhecido"
quality = data_quality_report(raw_df) if not raw_df.empty else {
    "original_rows": 0, "final_rows": 0, "removed_rows": 0, "groups_adjusted": 0,
    "ignored_count": 0, "payment_count": 0, "installment_count": 0,
}

# Sidebar filters after loading
with st.sidebar:
    if not raw_df.empty:
        st.subheader("Filtros do dashboard")
        min_date, max_date = raw_df["data"].min().date(), raw_df["data"].max().date()
        date_range = st.date_input("Período", value=(min_date, max_date), min_value=min_date, max_value=max_date)

        all_categories = sorted(raw_df["categoria"].dropna().unique().tolist())
        selected_categories = st.multiselect("Categorias", all_categories, default=all_categories)

        all_types = ordered_types(raw_df["tipo"].dropna().unique().tolist())
        # Correção: transferências ficam FORA por padrão. Elas podem ser incluídas manualmente.
        default_types = [t for t in all_types if t in IMPACT_TYPES]
        selected_types = st.multiselect(
            "Tipos incluídos nos totais",
            all_types,
            default=default_types,
            help=(
                "Por padrão entram apenas Gasto, Entrada e Estorno/Crédito. "
                "Pagamentos de fatura e transferências ficam fora para evitar duplicidade."
            ),
        )
    else:
        date_range = None
        selected_categories = []
        selected_types = []
        st.info("Suba um CSV para liberar filtros, categorias, parcelas e diagnóstico automático.")

filtered_df = raw_df.copy()
if not filtered_df.empty:
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start = pd.to_datetime(date_range[0])
        end = pd.to_datetime(date_range[1]) + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)
        filtered_df = filtered_df[(filtered_df["data"] >= start) & (filtered_df["data"] <= end)]
    if selected_categories:
        filtered_df = filtered_df[filtered_df["categoria"].isin(selected_categories)]

analysis_df = filtered_df[filtered_df["tipo"].isin(selected_types)].copy() if selected_types else filtered_df.iloc[0:0].copy()
metrics = aggregate_metrics(analysis_df, renda_mensal=salario_liquido + adiantamento + renda_extra + (beneficios if incluir_beneficios else 0), meta_economia=meta_economia)

cat = category_table(analysis_df)
parcelas = installment_table(analysis_df)
recorrentes = recurring_table(analysis_df)
cortes = build_cut_table(cat, metrics.get("renda_base", 0.0))

plano = plan_financeiro(
    profissao=profissao,
    salario_liquido=salario_liquido,
    adiantamento=adiantamento,
    renda_extra=renda_extra,
    beneficios=beneficios,
    incluir_beneficios=incluir_beneficios,
    saldo_conta=saldo_conta,
    gastos_analisados=metrics["gasto_liquido"],
    gastos_fixos_fora_csv=gastos_fixos_fora_csv,
    reserva_atual=reserva_atual,
    custo_essencial=custo_essencial,
    meses_reserva_saudavel=meses_reserva_saudavel,
    aporte_reserva_manual=aporte_reserva_manual,
    aporte_investimento_manual=aporte_investimento_manual,
    buffer_seguranca=buffer_seguranca,
)

# Data quality strip
if quality.get("removed_rows", 0) > 0 or quality.get("payment_count", 0) > 0:
    csv_type_label = {
        "fatura":        "📄 Fatura de cartão detectada",
        "extrato_conta": "🏦 Extrato de conta corrente detectado",
        "desconhecido":  "❓ Tipo não identificado",
    }.get(csv_source_type, "❓")
    st.markdown(
        f"""
        <div class="quality-strip">
          <b>Qualidade dos dados:</b> {quality.get('removed_rows', 0)} linha(s) duplicada(s)/conciliada(s) removida(s) •
          {quality.get('payment_count', 0)} pagamento(s) de fatura ignorado(s) •
          {quality.get('installment_count', 0)} parcela(s) detectada(s) •
          {csv_type_label}
        </div>
        """,
        unsafe_allow_html=True,
    )

# -----------------------------
# First page KPIs
# -----------------------------
k1, k2, k3, k4, k5 = st.columns(5)
with k1:
    metric_card("Profissão", plano["profissao"], "Use este campo para contextualizar sua renda")
with k2:
    metric_card("Renda planejável", format_brl(plano["renda_planejavel"]), "Salário + adiantamento + renda recorrente")
with k3:
    metric_card("Saldo da conta", format_brl(plano["saldo_conta"]), "Valor informado manualmente")
with k4:
    metric_card("Gastos/fatura analisados", format_brl(plano["gastos_analisados"]), "CSV tratado, sem pagamento de fatura")
with k5:
    tone = "positive" if plano["saldo_livre_pos_fatura"] >= 0 else "negative"
    help_pf = "Saldo - gastos do cartão (fatura ainda a pagar)" if csv_source_type == "fatura" else "Saldo - gastos identificados no extrato"
    metric_card("Saldo pós-gastos", format_brl(plano["saldo_livre_pos_fatura"]), help_pf, tone)

st.write("")
tab0, tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
    "🧭 Plano do mês",
    "📊 Visão geral",
    "🏷️ Categorias",
    "🧾 Gastos",
    "✂️ O que diminuir",
    "🔁 Parcelas",
    "🧠 Diagnóstico",
    "🧪 Qualidade",
    "📄 Dados",
])

with tab0:
    st.markdown('<div class="section-title">Seu mapa do mês</div>', unsafe_allow_html=True)
    a, b, c, d = st.columns(4)
    with a:
        metric_card("Gasto mensal identificado", format_brl(plano["gastos_mensais"]), "CSV + gastos fixos fora do CSV")
    with b:
        metric_card("Reserva mínima", format_brl(plano["reserva_minima"]), "3 meses do custo essencial")
    with c:
        metric_card("Falta para reserva saudável", format_brl(plano["falta_reserva_saudavel"]), f"Meta: {format_brl(plano['reserva_saudavel'])}")
    with d:
        tone = "positive" if plano["dinheiro_para_mim"] >= 0 else "negative"
        metric_card("Pode gastar consigo", format_brl(max(plano["dinheiro_para_mim"], 0)), "Depois de contas, reserva, investimento e buffer", tone)

    st.markdown('<div class="section-title">Plano recomendado</div>', unsafe_allow_html=True)
    p1, p2, p3 = st.columns(3)
    with p1:
        metric_card("Fase atual", plano["fase"], "A estratégia muda conforme sua reserva cresce")
    with p2:
        metric_card("Reserva sugerida", format_brl(plano["aporte_reserva_sugerido"]), "Valor automático recomendado para este mês")
    with p3:
        metric_card("Investimento sugerido", format_brl(plano["aporte_investimento_sugerido"]), "Antes da reserva mínima, fica zerado")

    st.progress(clamp(plano["reserva_pct_saudavel"], 0.0, 1.0), text=f"Reserva saudável: {pct(min(plano['reserva_pct_saudavel'], 1.0))}")

    left, right = st.columns([1.05, .95])
    with left:
        st.subheader("O que fazer em ordem")
        steps = pd.DataFrame([
            {"ordem": 1, "ação": "Confirmar saldo real da conta", "valor": plano["saldo_conta"], "observação": "Atualize no menu lateral sempre que abrir o app."},
            {"ordem": 2, "ação": "Considerar fatura/gastos do CSV", "valor": plano["gastos_analisados"], "observação": "Pagamentos de fatura ficam fora para não duplicar."},
            {"ordem": 3, "ação": "Separar reserva do mês", "valor": plano["aporte_reserva"], "observação": "Prioridade até bater a reserva mínima."},
            {"ordem": 4, "ação": "Investir somente o planejado", "valor": plano["aporte_investimento"], "observação": "Antes da reserva mínima, prefira R$ 0 ou valor simbólico."},
            {"ordem": 5, "ação": "Limite para gastar consigo", "valor": max(plano["dinheiro_para_mim"], 0), "observação": "Este é o teto para lazer, compras e vontade do mês."},
        ])
        show_steps = steps.copy()
        show_steps["valor"] = show_steps["valor"].map(format_brl)
        st.dataframe(show_steps, use_container_width=True, hide_index=True)

        plano_csv = steps.copy()
        plano_csv["valor"] = plano_csv["valor"].round(2)
        st.download_button(
            "Baixar plano do mês em CSV",
            data=plano_csv.to_csv(index=False).encode("utf-8-sig"),
            file_name="plano_financeiro_do_mes.csv",
            mime="text/csv",
        )

    with right:
        if plano["dinheiro_para_mim"] < 0:
            insight_card(
                "Atenção: plano negativo",
                f"Do jeito que está, faltam {format_brl(abs(plano['dinheiro_para_mim']))} para fechar o mês com reserva, investimento e buffer. Reduza gastos ou diminua temporariamente o aporte planejado.",
                "Crítico",
            )
        elif plano["reserva_atual"] < plano["reserva_minima"]:
            insight_card(
                "Prioridade: reserva mínima",
                f"Você ainda precisa de {format_brl(plano['falta_reserva_minima'])} para chegar na reserva mínima. Evite novas parcelas até concluir essa etapa.",
                "Alto",
            )
        else:
            insight_card(
                "Você já passou da reserva mínima",
                "Agora o foco é caminhar para a reserva saudável e começar investimentos simples, sem comprometer o caixa.",
                "Positivo",
            )

        insight_card(
            "Regra prática do mês",
            f"Use até {format_brl(max(plano['dinheiro_para_mim'], 0))} consigo. Separe {format_brl(plano['aporte_reserva'])} para reserva e {format_brl(plano['aporte_investimento'])} para investimentos.",
            "Limite",
        )
        if not uploaded_files:
            insight_card(
                "Falta o CSV para o app ficar completo",
                "Sem CSV, o plano usa apenas os valores manuais. Suba a fatura ou extrato para o app apontar categorias, parcelas e cortes específicos.",
                "Dados",
            )

with tab1:
    left, right = st.columns([1.1, .9])
    month = monthly_table(analysis_df)

    with left:
        st.markdown('<div class="section-title">Gastos líquidos por categoria</div>', unsafe_allow_html=True)
        if not cat.empty:
            fig = px.pie(cat, names="categoria", values="valor", hole=.54)
            st.plotly_chart(plot_layout(fig), use_container_width=True)
        else:
            st.info("Sem gastos para exibir. Suba um CSV ou ajuste os filtros.")

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
    st.markdown('<div class="section-title">O que diminuir primeiro</div>', unsafe_allow_html=True)
    if not cortes.empty:
        total_economia = cortes["economia_sugerida"].sum()
        metric_card("Economia mensal possível", format_brl(total_economia), "Estimativa conservadora baseada nas maiores categorias")
        st.write("")
        view = format_table_money(cortes, ["gasto_atual", "teto_sugerido", "economia_sugerida"])
        st.dataframe(view, use_container_width=True, hide_index=True)
        fig = px.bar(cortes.sort_values("economia_sugerida"), x="economia_sugerida", y="categoria", orientation="h")
        st.plotly_chart(plot_layout(fig), use_container_width=True)
    else:
        st.info("Suba um CSV para eu apontar quais gastos diminuir primeiro.")

with tab5:
    st.markdown('<div class="section-title">Parcelas em aberto e recorrências suspeitas</div>', unsafe_allow_html=True)
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

with tab6:
    st.markdown('<div class="section-title">Diagnóstico automático</div>', unsafe_allow_html=True)
    suggestions = make_suggestions(analysis_df, metrics, renda_mensal=plano["renda_planejavel"])
    if suggestions:
        for item in suggestions:
            insight_card(item["titulo"], f"<b>Ação:</b> {item['acao']}<br><b>Por quê:</b> {item['motivo']}", item["impacto"])
    else:
        st.info("Sem sugestões com os filtros atuais.")

    st.warning("As sugestões são educativas. Para investimentos específicos, avalie seu perfil de risco e consulte fontes/profissionais adequados.")

with tab7:
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
    else:
        st.info("Sem dados técnicos ainda.")

    if not filtered_df.empty:
        transfers = filtered_df[filtered_df["tipo"].isin([TYPE_TRANSFER_SENT, TYPE_TRANSFER_RECEIVED])].copy()
        if not transfers.empty:
            st.subheader("Transferências fora do total por padrão")
            tmp = transfers[["data", "descricao", "tipo", "valor", "arquivo"]].copy()
            tmp["data"] = tmp["data"].dt.strftime("%Y-%m-%d")
            tmp["valor"] = tmp["valor"].map(format_brl)
            st.dataframe(tmp, use_container_width=True, hide_index=True)

        ignored = filtered_df[filtered_df["tipo"].eq("Ignorado")].copy()
        if not ignored.empty:
            st.subheader("Lançamentos ignorados")
            tmp = ignored[["data", "descricao", "subtipo", "valor", "arquivo"]].copy()
            tmp["data"] = tmp["data"].dt.strftime("%Y-%m-%d")
            tmp["valor"] = tmp["valor"].map(format_brl)
            st.dataframe(tmp, use_container_width=True, hide_index=True)

with tab8:
    st.markdown('<div class="section-title">Dados tratados</div>', unsafe_allow_html=True)
    if not filtered_df.empty:
        export_df = filtered_df.copy()
        export_df["data"] = export_df["data"].dt.strftime("%Y-%m-%d")
        hide_cols = ["descricao_norm", "chave_parcela"]
        export_view = export_df.drop(columns=[c for c in hide_cols if c in export_df.columns], errors="ignore")
        if show_raw:
            st.dataframe(export_view, use_container_width=True, hide_index=True)
        else:
            st.caption("Ative 'Mostrar tabela completa' no menu lateral para visualizar tudo aqui.")
        csv = export_view.to_csv(index=False).encode("utf-8-sig")
        st.download_button("Baixar CSV tratado", data=csv, file_name="financas_tratadas_v3.csv", mime="text/csv")
    else:
        st.info("Suba um CSV para visualizar e exportar os dados tratados.")
