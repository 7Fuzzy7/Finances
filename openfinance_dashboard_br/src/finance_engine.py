from __future__ import annotations

import re
from dataclasses import dataclass
from io import BytesIO, StringIO
from typing import Iterable, Optional

import pandas as pd

CATEGORY_RULES = {
    "Alimentação": [
        r"ifood", r"restaurante", r"comer", r"lanch", r"padaria", r"burg", r"pizza", r"santo agostinho"
    ],
    "Mercado": [r"mercado", r"super", r"carrefour", r"extra", r"atacad", r"assai", r"pao de acucar"],
    "Transporte": [r"uber", r"99", r"top sp", r"bilhete", r"metro", r"trem", r"estacion", r"pedagio"],
    "Combustível": [r"posto", r"auto posto", r"shell", r"ipiranga", r"petrobras", r"gasolina"],
    "Saúde/Farmácia": [r"drog", r"farm", r"raia", r"drogasil", r"pacheco", r"sao paulo"],
    "Assinaturas": [r"spotify", r"netflix", r"amazon prime", r"canva", r"google", r"apple", r"icloud", r"microsoft", r"adobe"],
    "Seguro/Proteção": [r"tokio", r"seguro", r"blinda", r"porto seguro", r"marine"],
    "Compras": [r"mercadolivre", r"mercado livre", r"americanas", r"magalu", r"shopee", r"shein", r"amazon", r"kalunga"],
    "Educação": [r"fiap", r"curso", r"udemy", r"alura", r"faculdade", r"escola"],
    "Serviços": [r"claro", r"vivo", r"tim", r"oi", r"internet", r"conta", r"serv", r"omny"],
    "Transferências": [r"pix", r"transfer", r"ted", r"doc"],
    "Pagamentos/Cartão": [r"pagamento recebido", r"pagamento de fatura", r"fatura"],
    "Entradas": [r"salario", r"salário", r"recebida", r"deposito", r"depósito", r"reembolso", r"flash"],
}

ESSENTIAL_CATEGORIES = {"Alimentação", "Mercado", "Transporte", "Combustível", "Saúde/Farmácia", "Serviços"}
VARIABLE_CATEGORIES = {"Alimentação", "Compras", "Lazer", "Assinaturas", "Combustível"}

DATE_COLUMNS = ["date", "data", "Data", "DATA", "Date"]
TITLE_COLUMNS = ["title", "descricao", "descrição", "Descrição", "description", "Description", "histórico", "Historico", "memo"]
AMOUNT_COLUMNS = ["amount", "valor", "Valor", "VALOR", "value", "Value"]


def _clean_text(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def parse_brl_number(value: object) -> float:
    """Parse Brazilian money formats such as '1.311,82', '- 49,00', and '-49.00'."""
    if pd.isna(value):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().replace("R$", "").replace("\xa0", " ")
    s = re.sub(r"\s+", "", s)
    if s in {"", "-", "--"}:
        return 0.0

    sign = -1 if s.startswith("-") or s.endswith("-") else 1
    s = s.replace("-", "")

    # BR format: 1.311,82
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return sign * float(s)
    except ValueError:
        s = re.sub(r"[^0-9.]", "", s)
        return sign * float(s) if s else 0.0


def _find_column(columns: Iterable[str], options: list[str]) -> Optional[str]:
    lower_map = {str(c).strip().lower(): c for c in columns}
    for opt in options:
        if opt.lower() in lower_map:
            return lower_map[opt.lower()]
    # fuzzy fallback
    for c in columns:
        cl = str(c).strip().lower()
        if any(opt.lower() in cl for opt in options):
            return c
    return None


def read_csv_flexible(file_obj, source_name: str = "arquivo") -> pd.DataFrame:
    """Read CSV from upload/path, detecting delimiter and Nubank-like columns."""
    try:
        if hasattr(file_obj, "read"):
            raw = file_obj.read()
            if hasattr(file_obj, "seek"):
                file_obj.seek(0)
            if isinstance(raw, str):
                data = raw.encode("utf-8")
            else:
                data = raw
            buffer = BytesIO(data)
            try:
                df = pd.read_csv(buffer, sep=None, engine="python", encoding="utf-8")
            except UnicodeDecodeError:
                buffer.seek(0)
                df = pd.read_csv(buffer, sep=None, engine="python", encoding="latin-1")
        else:
            df = pd.read_csv(file_obj, sep=None, engine="python", encoding="utf-8")
    except Exception as exc:
        raise ValueError(f"Não consegui ler o CSV '{source_name}'. Verifique se o arquivo está no formato correto. Erro: {exc}") from exc

    if df.empty:
        raise ValueError(f"O CSV '{source_name}' está vazio.")

    return normalize_transactions(df, source_name=source_name)


def normalize_transactions(df: pd.DataFrame, source_name: str = "arquivo") -> pd.DataFrame:
    date_col = _find_column(df.columns, DATE_COLUMNS)
    title_col = _find_column(df.columns, TITLE_COLUMNS)
    amount_col = _find_column(df.columns, AMOUNT_COLUMNS)

    if not all([date_col, title_col, amount_col]):
        raise ValueError(
            f"Não encontrei colunas esperadas no arquivo '{source_name}'. "
            "O app espera algo parecido com: date,title,amount ou data,descricao,valor."
        )

    out = pd.DataFrame()
    out["data"] = pd.to_datetime(df[date_col], errors="coerce", dayfirst=False)
    # Try dayfirst if too many NaT
    if out["data"].isna().mean() > 0.5:
        out["data"] = pd.to_datetime(df[date_col], errors="coerce", dayfirst=True)
    out["descricao"] = df[title_col].map(_clean_text)
    out["valor"] = df[amount_col].map(parse_brl_number).astype(float)
    out["arquivo"] = source_name

    out = out.dropna(subset=["data"])
    out = out[out["descricao"].astype(str).str.len() > 0]
    out["mes"] = out["data"].dt.to_period("M").astype(str)
    out["dia"] = out["data"].dt.date
    out["categoria"] = out["descricao"].map(categorize)
    out["tipo"] = out.apply(classify_transaction, axis=1)
    out["valor_abs"] = out["valor"].abs()
    out["parcela_atual"] = out["descricao"].map(lambda x: extract_installment(x)[0])
    out["parcela_total"] = out["descricao"].map(lambda x: extract_installment(x)[1])
    out["eh_parcelado"] = out["parcela_total"].fillna(0).astype(int) > 1
    out["recorrente_suspeito"] = out["descricao"].map(is_recurring_like)
    return out.sort_values("data").reset_index(drop=True)


def categorize(description: str) -> str:
    desc = (description or "").lower()
    for category, patterns in CATEGORY_RULES.items():
        if any(re.search(pattern, desc) for pattern in patterns):
            return category
    if "parcela" in desc:
        return "Parcelas"
    if "estorno" in desc:
        return "Estornos"
    return "Outros"


def classify_transaction(row: pd.Series) -> str:
    desc = str(row.get("descricao", "")).lower()
    value = float(row.get("valor", 0))
    if "pagamento recebido" in desc or "pagamento de fatura" in desc:
        return "Pagamento de fatura"
    if "estorno" in desc:
        return "Estorno/Crédito"
    if "recebida" in desc or "salario" in desc or "salário" in desc or "depósito" in desc or "deposito" in desc:
        return "Entrada"
    if "enviada" in desc or "compra no débito" in desc or "compra no debito" in desc:
        return "Gasto"
    # Em faturas Nubank, valores negativos costumam ser créditos/estornos.
    # Em extratos de conta, descrições como enviada/compra no débito já foram tratadas acima.
    if value < 0:
        return "Estorno/Crédito"
    return "Gasto"


def extract_installment(description: str) -> tuple[Optional[int], Optional[int]]:
    desc = description or ""
    patterns = [r"parcela\s*(\d+)\s*/\s*(\d+)", r"(\d+)d(\d+)", r"(\d+)\s*/\s*(\d+)"]
    for pattern in patterns:
        match = re.search(pattern, desc, flags=re.IGNORECASE)
        if match:
            try:
                current, total = int(match.group(1)), int(match.group(2))
                if 0 < current <= total <= 60:
                    return current, total
            except Exception:
                pass
    return None, None


def is_recurring_like(description: str) -> bool:
    desc = (description or "").lower()
    return bool(re.search(r"spotify|netflix|canva|icloud|google|microsoft|adobe|seguro|blinda|assinatura|prime", desc))


def aggregate_metrics(df: pd.DataFrame, renda_mensal: float = 0.0, meta_economia: float = 0.20) -> dict:
    if df.empty:
        return {}
    gastos_df = df[df["tipo"] == "Gasto"].copy()
    entradas_df = df[df["tipo"] == "Entrada"].copy()
    estornos_df = df[df["tipo"] == "Estorno/Crédito"].copy()
    pagamentos_df = df[df["tipo"] == "Pagamento de fatura"].copy()

    total_gastos = gastos_df["valor"].sum() if not gastos_df.empty else 0.0
    total_entradas = entradas_df["valor_abs"].sum() if not entradas_df.empty else 0.0
    total_estornos = estornos_df["valor_abs"].sum() if not estornos_df.empty else 0.0
    total_pagamentos = pagamentos_df["valor_abs"].sum() if not pagamentos_df.empty else 0.0
    gasto_liquido = max(total_gastos - total_estornos, 0.0)
    renda_base = renda_mensal if renda_mensal > 0 else total_entradas
    saldo_estimado = renda_base - gasto_liquido if renda_base > 0 else -gasto_liquido
    taxa_economia = (saldo_estimado / renda_base) if renda_base > 0 else 0.0

    top_category = "-"
    if not gastos_df.empty:
        cats = gastos_df.groupby("categoria")["valor"].sum().sort_values(ascending=False)
        top_category = cats.index[0] if len(cats) else "-"

    parcelado = gastos_df[gastos_df["eh_parcelado"]]
    parcelas_futuras = estimate_future_installments(parcelado)

    score = calculate_score(gasto_liquido, renda_base, total_pagamentos, parcelas_futuras, gastos_df)

    return {
        "total_gastos": total_gastos,
        "total_entradas": total_entradas,
        "total_estornos": total_estornos,
        "gasto_liquido": gasto_liquido,
        "pagamentos_fatura": total_pagamentos,
        "saldo_estimado": saldo_estimado,
        "taxa_economia": taxa_economia,
        "top_category": top_category,
        "qtd_transacoes": len(df),
        "ticket_medio": gasto_liquido / max(len(gastos_df), 1),
        "parcelas_futuras": parcelas_futuras,
        "score": score,
        "renda_base": renda_base,
        "meta_economia_valor": renda_base * meta_economia if renda_base > 0 else 0.0,
    }


def installment_key(description: str) -> str:
    """Normalize installment descriptions so different months of the same purchase are not double-counted."""
    desc = (description or "").lower()
    desc = re.sub(r"parcela\s*\d+\s*/\s*\d+", "", desc, flags=re.IGNORECASE)
    desc = re.sub(r"\d+d\d+", "", desc)
    desc = re.sub(r"\d+\s*/\s*\d+", "", desc)
    desc = re.sub(r"[^a-z0-9]+", " ", desc).strip()
    return desc[:80]


def estimate_future_installments(parcelado: pd.DataFrame) -> float:
    if parcelado.empty:
        return 0.0
    temp = parcelado.copy()
    temp = temp.dropna(subset=["parcela_atual", "parcela_total"])
    if temp.empty:
        return 0.0
    temp["_key"] = temp["descricao"].map(installment_key)
    future_total = 0.0
    for _, group in temp.groupby("_key"):
        group = group.sort_values(["parcela_total", "parcela_atual", "data"], ascending=[False, False, False])
        row = group.iloc[0]
        atual = int(row["parcela_atual"])
        total = int(row["parcela_total"])
        if total > atual:
            future_total += float(row["valor"]) * (total - atual)
    return float(future_total)


def calculate_score(gasto_liquido: float, renda_base: float, pagamentos: float, parcelas_futuras: float, gastos_df: pd.DataFrame) -> int:
    score = 100
    if renda_base > 0:
        ratio = gasto_liquido / renda_base
        if ratio > 1.0:
            score -= 35
        elif ratio > 0.85:
            score -= 25
        elif ratio > 0.70:
            score -= 15
        elif ratio < 0.55:
            score += 5
    else:
        score -= 20

    if parcelas_futuras > 0 and renda_base > 0:
        pf_ratio = parcelas_futuras / renda_base
        if pf_ratio > 1.5:
            score -= 20
        elif pf_ratio > 0.8:
            score -= 12
        elif pf_ratio > 0.3:
            score -= 6

    if not gastos_df.empty:
        cat = gastos_df.groupby("categoria")["valor"].sum()
        if cat.sum() > 0:
            variable = cat[cat.index.isin(VARIABLE_CATEGORIES)].sum() / cat.sum()
            if variable > 0.55:
                score -= 10
    return max(0, min(100, int(round(score))))


def category_table(df: pd.DataFrame) -> pd.DataFrame:
    gastos = df[df["tipo"] == "Gasto"]
    if gastos.empty:
        return pd.DataFrame(columns=["categoria", "valor", "participacao"])
    out = gastos.groupby("categoria", as_index=False)["valor"].sum().sort_values("valor", ascending=False)
    total = out["valor"].sum()
    out["participacao"] = out["valor"] / total if total else 0
    return out


def merchant_table(df: pd.DataFrame, limit: int = 15) -> pd.DataFrame:
    gastos = df[df["tipo"] == "Gasto"].copy()
    if gastos.empty:
        return pd.DataFrame(columns=["descricao", "categoria", "valor", "qtd"])
    out = gastos.groupby(["descricao", "categoria"], as_index=False).agg(valor=("valor", "sum"), qtd=("valor", "count"))
    return out.sort_values("valor", ascending=False).head(limit)


def monthly_table(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["mes", "gastos", "entradas", "estornos", "saldo"])
    temp = df.copy()
    temp["gastos"] = temp.apply(lambda r: r["valor"] if r["tipo"] == "Gasto" else 0.0, axis=1)
    temp["entradas"] = temp.apply(lambda r: r["valor_abs"] if r["tipo"] == "Entrada" else 0.0, axis=1)
    temp["estornos"] = temp.apply(lambda r: r["valor_abs"] if r["tipo"] == "Estorno/Crédito" else 0.0, axis=1)
    out = temp.groupby("mes", as_index=False).agg(gastos=("gastos", "sum"), entradas=("entradas", "sum"), estornos=("estornos", "sum"))
    out["saldo"] = out["entradas"] - (out["gastos"] - out["estornos"])
    return out


def daily_cashflow(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["data", "valor", "saldo_acumulado"])
    temp = df.copy()
    def signed(r):
        if r["tipo"] == "Gasto":
            return -float(r["valor"])
        if r["tipo"] in ["Entrada", "Estorno/Crédito"]:
            return float(r["valor_abs"])
        return 0.0
    temp["movimento"] = temp.apply(signed, axis=1)
    out = temp.groupby("data", as_index=False)["movimento"].sum().sort_values("data")
    out["saldo_acumulado"] = out["movimento"].cumsum()
    return out


def make_suggestions(df: pd.DataFrame, metrics: dict, renda_mensal: float = 0.0) -> list[dict]:
    suggestions: list[dict] = []
    if not metrics:
        return suggestions

    renda = metrics.get("renda_base", 0.0)
    gasto = metrics.get("gasto_liquido", 0.0)
    saldo = metrics.get("saldo_estimado", 0.0)
    taxa = metrics.get("taxa_economia", 0.0)
    parcelas = metrics.get("parcelas_futuras", 0.0)
    score = metrics.get("score", 0)

    if renda <= 0:
        suggestions.append({
            "titulo": "Cadastre sua renda mensal para o diagnóstico ficar mais preciso",
            "impacto": "Alto",
            "acao": "Informe salário líquido, benefícios e renda extra recorrente no menu lateral.",
            "motivo": "Sem renda base, o app não consegue medir se os gastos estão saudáveis."
        })
    elif gasto > renda:
        suggestions.append({
            "titulo": "Pare novas parcelas até o orçamento voltar para o positivo",
            "impacto": "Crítico",
            "acao": f"Reduza ao menos {format_brl(gasto - renda)} neste mês para não fechar no negativo.",
            "motivo": "Gastos acima da renda impedem reserva e investimento."
        })
    elif taxa < 0.10:
        suggestions.append({
            "titulo": "Aumente sua margem mensal antes de investir pesado",
            "impacto": "Alto",
            "acao": f"Tente separar pelo menos R$ {format_brl(renda * 0.10)} por mês inicialmente.",
            "motivo": "Uma margem menor que 10% deixa qualquer imprevisto virar dívida."
        })
    elif taxa >= 0.20:
        suggestions.append({
            "titulo": "Sua margem está boa para acelerar a reserva",
            "impacto": "Positivo",
            "acao": f"Direcione cerca de R$ {format_brl(renda * 0.20)} para uma reserva com liquidez e baixo risco.",
            "motivo": "Antes de buscar rentabilidade, o primeiro objetivo é segurança financeira."
        })

    cats = category_table(df)
    if not cats.empty:
        top = cats.iloc[0]
        if top["participacao"] > 0.35:
            suggestions.append({
                "titulo": f"Categoria dominante: {top['categoria']}",
                "impacto": "Médio",
                "acao": f"Defina um teto para {top['categoria']} e acompanhe semanalmente.",
                "motivo": f"Ela representa {top['participacao']:.0%} dos gastos analisados."
            })

    recurring = df[(df["tipo"] == "Gasto") & (df["recorrente_suspeito"])]
    if not recurring.empty:
        total_rec = recurring["valor"].sum()
        suggestions.append({
            "titulo": "Revise assinaturas e cobranças recorrentes",
            "impacto": "Médio",
            "acao": f"Revise {format_brl(total_rec)} em gastos recorrentes identificados.",
            "motivo": "Assinaturas pequenas somadas viram um gasto fixo invisível."
        })

    if parcelas > 0:
        suggestions.append({
            "titulo": "Parcelas futuras já comprometem renda dos próximos meses",
            "impacto": "Alto" if renda and parcelas / renda > 0.5 else "Médio",
            "acao": f"Você tem aproximadamente {format_brl(parcelas)} ainda a vencer em compras parceladas.",
            "motivo": "Parcelamento reduz sua liberdade de decisão nos próximos meses."
        })

    if saldo > 0 and renda > 0:
        suggestions.append({
            "titulo": "Caminho de investimento recomendado pelo app",
            "impacto": "Educativo",
            "acao": "1) reserva de emergência; 2) metas de curto prazo; 3) investimentos de prazo maior somente depois disso.",
            "motivo": "O app evita sugerir risco antes de haver estabilidade e liquidez."
        })

    if score < 65:
        suggestions.append({
            "titulo": "Prioridade do mês: controle, não rentabilidade",
            "impacto": "Alto",
            "acao": "Reduza gastos variáveis, congele parcelamentos e acompanhe o dashboard toda semana.",
            "motivo": "Com score baixo, o maior ganho vem de organização e redução de vazamentos."
        })

    return suggestions[:8]


def format_brl(value: float) -> str:
    value = float(value or 0)
    sign = "-" if value < 0 else ""
    value = abs(value)
    inteiro, centavos = divmod(round(value * 100), 100)
    inteiro_str = f"{inteiro:,}".replace(",", ".")
    return f"{sign}R$ {inteiro_str},{centavos:02d}"


def load_many(files) -> pd.DataFrame:
    frames = []
    for file in files:
        name = getattr(file, "name", "arquivo.csv")
        frames.append(read_csv_flexible(file, name))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).sort_values("data").reset_index(drop=True)
