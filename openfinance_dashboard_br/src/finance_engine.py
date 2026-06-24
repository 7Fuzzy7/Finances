from __future__ import annotations

import re
import unicodedata
from io import BytesIO
from typing import Iterable, Optional, Literal

import pandas as pd

# ─── Tipos canônicos ──────────────────────────────────────────────────────────
TYPE_EXPENSE           = "Gasto"
TYPE_INCOME            = "Entrada"
TYPE_CREDIT            = "Estorno/Crédito"
TYPE_IGNORED           = "Ignorado"
TYPE_TRANSFER_SENT     = "Transferência enviada"
TYPE_TRANSFER_RECEIVED = "Transferência recebida"

IMPACT_TYPES   = [TYPE_EXPENSE, TYPE_INCOME, TYPE_CREDIT]
ALL_TYPES_ORDER = [
    TYPE_EXPENSE, TYPE_INCOME, TYPE_CREDIT,
    TYPE_TRANSFER_SENT, TYPE_TRANSFER_RECEIVED, TYPE_IGNORED,
]

DATE_COLUMNS   = ["date","data","Data","DATA","Date","transaction_date","posted_date"]
TITLE_COLUMNS  = ["title","descricao","descrição","Descrição","description",
                  "Description","histórico","historico","Historico","memo","nome"]
AMOUNT_COLUMNS = ["amount","valor","Valor","VALOR","value","Value","quantia"]

# ─── Regras de categoria ──────────────────────────────────────────────────────
# Ordem importa: mais específico primeiro.
CATEGORY_RULES: list[tuple[str, list[str]]] = [
    ("Alimentação", [
        r"\bifood\b", r"\brappi\b", r"\brestaur", r"\bcomer\b",
        r"\blanch", r"\bpadaria\b", r"\bburg", r"\bpizza\b",
        r"santo agostinho", r"\bsushi\b", r"\bhamburg",
    ]),
    ("Combustível", [
        r"\bauto posto\b", r"\bposto\b", r"\bshell\b",
        r"\bipiranga\b", r"\bpetrobras\b", r"\bgasolina\b", r"\betanol\b",
    ]),
    ("Saúde/Farmácia", [
        # Preciso: "drogaria sao paulo" antes de qualquer match genérico de cidade
        r"\bdrogaria\s+sao\s+paulo\b", r"\bdrog\s+sao\s+paulo\b",
        r"\bdrogaria\b", r"\bdrog\b", r"\bfarm", r"\braia\b",
        r"\bdrogasil\b", r"\bpacheco\b", r"\bpague menos\b",
        r"\bdermany", r"\bclinica\b", r"\bhospital\b",
    ]),
    ("Assinaturas", [
        r"\bspotify\b", r"\bnetflix\b", r"\bamazon\s+prime\b", r"\bprime\s+video\b",
        r"canva", r"\bebn\*canva\b", r"\bgoogle\b", r"\bapple\b",
        r"\bicloud\b", r"\bmicrosoft\b", r"\badobe\b", r"\bdisney\b",
        r"\bhbo\b", r"\bmax\b", r"\bdm\s+\*",
    ]),
    ("Seguro/Proteção", [
        r"\btokio\b", r"\bseguro\b", r"\bblinda\b",
        r"\bporto\s+seguro\b", r"\bmarine\b", r"\bprotec",
    ]),
    ("Compras", [
        r"\bmercado\s*livre\b", r"\bmercadolivre\b", r"\bamericanas\b",
        r"\bmagalu\b", r"\bshopee\b", r"\bshein\b", r"\bamazon\b",
        r"\bkalunga\b", r"\bcasas\s+bahia\b", r"\baliexpress\b",
    ]),
    ("Mercado", [
        r"\bsupermerc", r"\bmercado\b", r"\bcarrefour\b", r"\bextra\b",
        r"\batacad", r"\bassai\b", r"\bpao\s+de\s+acucar\b",
    ]),
    ("Transporte", [
        r"\buber\b", r"\b99\b", r"\btop\s+sp\b", r"\bbilhete\b",
        r"\bmetro\b", r"\btrem\b", r"\bestacion", r"\bpedagio\b",
        r"\bsem\s+parar\b", r"\bcabify\b",
    ]),
    ("Educação", [
        r"\bfiap\b", r"\bcurso\b", r"\budemy\b", r"\balura\b",
        r"\bfaculdade\b", r"\bescola\b", r"\blivro\b",
    ]),
    ("Serviços", [
        r"\bclaro\b", r"\bvivo\b", r"\btim\b", r"\boi\b",
        r"\binternet\b", r"\bservic", r"\bomny\b",
        r"\bconta\s+de\s+luz\b", r"\bsabesp\b", r"\benel\b",
        r"\bpagodedeuda\b",
    ]),
    ("Lazer", [
        r"\bcinema\b", r"\bteatro\b", r"\bshow\b", r"\bparque\b",
        r"\bbar\b", r"\bbalada\b", r"\bclub\b", r"\bjogo\b",
        r"\bgame\b", r"\bsteam\b",
    ]),
]

ESSENTIAL_CATEGORIES = {"Alimentação","Mercado","Transporte","Combustível","Saúde/Farmácia","Serviços"}
VARIABLE_CATEGORIES  = {"Alimentação","Compras","Lazer","Assinaturas","Combustível"}

DeduplicateMode = Literal["reconcile","exact","none"]


# ─── Utilidades de texto ──────────────────────────────────────────────────────
def strip_accents(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def normalize_text(text: object) -> str:
    value = "" if pd.isna(text) else str(text)
    value = strip_accents(value).lower().strip()
    return re.sub(r"\s+", " ", value)


def _clean_text(value: object) -> str:
    if pd.isna(value):
        return ""
    return re.sub(r"\s+", " ", str(value).strip())


def parse_brl_number(value: object) -> float:
    """
    Converte string monetária BR/US → float com sinal.
    Exemplos: '1.311,82', '- 49,00', '-49.00', '(21,02)'.
    """
    if pd.isna(value):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().replace("R$", "").replace("\xa0", " ")
    s = re.sub(r"\s+", "", s)
    if s in {"", "-", "--"}:
        return 0.0
    negative = s.startswith("-") or s.endswith("-") or (s.startswith("(") and s.endswith(")"))
    s = s.replace("-", "").replace("(", "").replace(")", "")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        number = float(s)
    except ValueError:
        s = re.sub(r"[^0-9.]", "", s)
        number = float(s) if s else 0.0
    return -number if negative else number


def format_brl(value: float) -> str:
    value = float(value or 0)
    sign  = "-" if value < 0 else ""
    value = abs(value)
    inteiro, centavos = divmod(round(value * 100), 100)
    inteiro_str = f"{inteiro:,}".replace(",", ".")
    return f"{sign}R$ {inteiro_str},{centavos:02d}"


def _find_column(columns: Iterable[str], options: list[str]) -> Optional[str]:
    lower_map = {normalize_text(c): c for c in columns}
    for opt in options:
        key = normalize_text(opt)
        if key in lower_map:
            return lower_map[key]
    for c in columns:
        cl = normalize_text(c)
        if any(normalize_text(opt) in cl for opt in options):
            return c
    return None


# ─── Classificação de tipo ────────────────────────────────────────────────────
def is_payment_settlement(desc_norm: str) -> bool:
    return bool(re.search(
        r"\bpagamento\s+(recebido|de\s+fatura|fatura|cartao|cartão)\b", desc_norm))


def is_refund_credit(desc_norm: str) -> bool:
    return bool(re.search(
        r"\b(estorno|credito|crédito|reembolso|chargeback|cancelamento)\b", desc_norm))


def is_transfer_received(desc_norm: str) -> bool:
    return bool(
        re.search(r"\b(transferencia|transferência)\s+recebida\b", desc_norm) or
        re.search(r"\bpix\s+recebido\b", desc_norm)
    )


def is_transfer_sent(desc_norm: str) -> bool:
    return bool(
        re.search(r"\b(transferencia|transferência)\s+enviada\b", desc_norm) or
        re.search(r"\bpix\s+enviado\b", desc_norm)
    )


# FIX: reconhecer aportes próprios entre contas como transferência, não gasto
def is_own_account_transfer(desc_norm: str) -> bool:
    return bool(re.search(
        r"\baporte\s+proprio\b|\baporte\s+proprio\b|\btransf\s+propria\b|"
        r"\bminha\s+conta\b|\bpropia\b", desc_norm))


def classify_transaction_full(row: pd.Series) -> tuple[str, str]:
    desc  = normalize_text(row.get("descricao", ""))
    value = float(row.get("valor", 0) or 0)

    if is_payment_settlement(desc):
        return TYPE_IGNORED, "Pagamento de fatura"

    if is_transfer_received(desc):
        return TYPE_TRANSFER_RECEIVED, "Pix/transferência recebida"

    if is_transfer_sent(desc):
        return TYPE_TRANSFER_SENT, "Pix/transferência enviada"

    if is_own_account_transfer(desc):
        return TYPE_TRANSFER_SENT, "Aporte entre contas próprias"

    if is_refund_credit(desc):
        return TYPE_CREDIT, "Estorno/Reembolso"

    if re.search(r"\b(compra\s+no\s+debito|compra\s+no\s+débito|debito|débito)\b", desc):
        return TYPE_EXPENSE, "Compra no débito"

    if re.search(
        r"\b(salario|salário|recebida|deposito|depósito|provento|rendimento|flash)\b", desc):
        return TYPE_INCOME, "Entrada identificada"

    # Fatura Nubank: valor negativo = crédito/estorno
    if value < 0:
        return TYPE_CREDIT, "Crédito na fatura"

    return TYPE_EXPENSE, "Compra"


def classify_transaction(row: pd.Series) -> str:
    """Wrapper de compatibilidade."""
    return classify_transaction_full(row)[0]


# ─── Categorização ────────────────────────────────────────────────────────────
def categorize(description: str, tipo: str | None = None, subtipo: str | None = None) -> str:
    if tipo == TYPE_IGNORED:
        return "Ignorados"
    if tipo in {TYPE_TRANSFER_SENT, TYPE_TRANSFER_RECEIVED}:
        return "Transferências"

    desc = normalize_text(description)
    for category, patterns in CATEGORY_RULES:
        if any(re.search(pat, desc) for pat in patterns):
            return category

    if extract_installment(description)[1]:
        return "Parcelas"
    if tipo == TYPE_CREDIT:
        return "Estornos/Créditos"
    if tipo == TYPE_INCOME:
        return "Entradas"
    return "Outros"


# ─── Parcelas ─────────────────────────────────────────────────────────────────
_INSTALLMENT_PATTERNS = [
    r"\bparcela\s*(\d{1,2})\s*/\s*(\d{1,2})\b",
    r"\bparc\.?\s*(\d{1,2})\s*/\s*(\d{1,2})\b",
    r"\b(\d{1,2})\s*/\s*(\d{1,2})\s*(?:parcelas?|parc\.?|x)\b",
    r"\bparcela\s*(\d{1,2})\s*(?:de|d)\s*(\d{1,2})\b",
    # Nubank compacto: "Auto08d12", "05d12" — sem prefixo de ano
    r"(?<!\d)(\d{1,2})d(\d{1,2})(?!\d)",
]


def extract_installment(description: str) -> tuple[Optional[int], Optional[int]]:
    desc = normalize_text(description)
    for pattern in _INSTALLMENT_PATTERNS:
        m = re.search(pattern, desc, flags=re.IGNORECASE)
        if not m:
            continue
        try:
            cur, tot = int(m.group(1)), int(m.group(2))
        except Exception:
            continue
        if 1 <= cur <= tot and 2 <= tot <= 60:
            return cur, tot
    return None, None


def installment_key(description: str) -> str:
    desc = normalize_text(description)
    for pat in [
        r"\bparcela\s*\d{1,2}\s*/\s*\d{1,2}\b",
        r"\bparc\.?\s*\d{1,2}\s*/\s*\d{1,2}\b",
        r"\b\d{1,2}\s*/\s*\d{1,2}\s*(?:parcelas?|parc\.?|x)\b",
        r"(?<!\d)\d{1,2}d\d{1,2}(?!\d)",
    ]:
        desc = re.sub(pat, " ", desc)
    return re.sub(r"[^a-z0-9]+", " ", desc).strip()[:90]


def is_recurring_like(description: str, category: str | None = None) -> bool:
    if category in {"Assinaturas", "Seguro/Proteção"}:
        return True
    desc = normalize_text(description)
    return bool(re.search(
        r"\b(spotify|netflix|canva|icloud|google|microsoft|adobe|"
        r"seguro|blinda|assinatura|prime|mensalidade)\b", desc))


# ─── Deduplicação ────────────────────────────────────────────────────────────
def apply_deduplication(df: pd.DataFrame, mode: DeduplicateMode = "reconcile") -> pd.DataFrame:
    if df.empty or mode == "none":
        out = df.copy()
        out.attrs["dedupe_report"] = {
            "mode": mode, "original_rows": int(len(df)), "final_rows": int(len(out)),
            "removed_rows": 0, "groups_adjusted": 0,
        }
        return out

    if mode == "exact":
        before = len(df)
        out = df.drop_duplicates(subset=["data","descricao_norm","valor"], keep="first").copy()
        out.attrs["dedupe_report"] = {
            "mode": mode, "original_rows": int(before), "final_rows": int(len(out)),
            "removed_rows": int(before - len(out)), "groups_adjusted": int(before - len(out)),
        }
        return out.sort_values(["data","descricao","valor"]).reset_index(drop=True)

    # reconcile: cancela pares positivo/negativo com mesmo valor abs no mesmo dia e descrição
    rows: list[pd.Series] = []
    adjusted_groups = 0
    removed_rows = 0
    temp = df.copy()
    temp["_dk"] = temp["valor_abs"].round(2)
    for _, group in temp.groupby(["data","descricao_norm","_dk"], sort=False, dropna=False):
        pos = group[group["valor"] > 0]
        neg = group[group["valor"] < 0]
        if not pos.empty and not neg.empty:
            cancel = min(len(pos), len(neg))
            adjusted_groups += 1
            removed_rows += cancel * 2
            rem_pos = len(pos) - cancel
            rem_neg = len(neg) - cancel
            if rem_pos:
                for _, r in pos.head(rem_pos).iterrows():
                    r = r.copy(); r["dedup_status"] = f"conciliado ({len(group)} → {rem_pos})"
                    rows.append(r)
            if rem_neg:
                for _, r in neg.head(rem_neg).iterrows():
                    r = r.copy(); r["dedup_status"] = f"conciliado ({len(group)} → {rem_neg})"
                    rows.append(r)
        else:
            for _, r in group.iterrows():
                rows.append(r)

    out = (pd.DataFrame(rows).drop(columns=["_dk"], errors="ignore")
             .sort_values(["data","descricao","valor"]).reset_index(drop=True)
           ) if rows else temp.iloc[0:0].drop(columns=["_dk"], errors="ignore")
    out.attrs["dedupe_report"] = {
        "mode": mode, "original_rows": int(len(df)), "final_rows": int(len(out)),
        "removed_rows": int(removed_rows), "groups_adjusted": int(adjusted_groups),
    }
    return out


# ─── Leitura & normalização ───────────────────────────────────────────────────
def read_csv_flexible(file_obj, source_name: str = "arquivo",
                      dedupe_mode: DeduplicateMode = "reconcile") -> pd.DataFrame:
    try:
        if hasattr(file_obj, "read"):
            raw = file_obj.read()
            if hasattr(file_obj, "seek"):
                file_obj.seek(0)
            data = raw.encode("utf-8") if isinstance(raw, str) else raw
            buf  = BytesIO(data)
            try:
                raw_df = pd.read_csv(buf, sep=None, engine="python", encoding="utf-8")
            except UnicodeDecodeError:
                buf.seek(0)
                raw_df = pd.read_csv(buf, sep=None, engine="python", encoding="latin-1")
        else:
            try:
                raw_df = pd.read_csv(file_obj, sep=None, engine="python", encoding="utf-8")
            except UnicodeDecodeError:
                raw_df = pd.read_csv(file_obj, sep=None, engine="python", encoding="latin-1")
    except Exception as exc:
        raise ValueError(
            f"Não consegui ler o CSV '{source_name}'. Verifique o formato. Erro: {exc}") from exc

    if raw_df.empty:
        raise ValueError(f"O CSV '{source_name}' está vazio.")

    out = normalize_transactions(raw_df, source_name=source_name)
    return apply_deduplication(out, mode=dedupe_mode)


def normalize_transactions(df: pd.DataFrame, source_name: str = "arquivo") -> pd.DataFrame:
    date_col   = _find_column(df.columns, DATE_COLUMNS)
    title_col  = _find_column(df.columns, TITLE_COLUMNS)
    amount_col = _find_column(df.columns, AMOUNT_COLUMNS)

    if not all([date_col, title_col, amount_col]):
        raise ValueError(
            f"Colunas não encontradas em '{source_name}'. "
            "Esperado: date,title,amount  ou  data,descricao,valor.")

    out = pd.DataFrame()
    out["data"]         = pd.to_datetime(df[date_col], errors="coerce", dayfirst=False)
    if out["data"].isna().mean() > 0.5:
        out["data"]     = pd.to_datetime(df[date_col], errors="coerce", dayfirst=True)
    out["descricao"]    = df[title_col].map(_clean_text)
    out["descricao_norm"] = out["descricao"].map(normalize_text)
    out["valor"]        = df[amount_col].map(parse_brl_number).astype(float)
    out["arquivo"]      = source_name

    out = out.dropna(subset=["data"])
    out = out[out["descricao"].str.len() > 0]
    out = out[out["valor"].notna()]

    classification = out.apply(classify_transaction_full, axis=1, result_type="expand")
    classification.columns = ["tipo", "subtipo"]
    out = pd.concat([out, classification], axis=1)

    out["categoria"] = out.apply(
        lambda r: categorize(r["descricao"], r.get("tipo"), r.get("subtipo")), axis=1)
    out["valor_abs"]    = out["valor"].abs()
    out["valor_impacto"] = out.apply(_impact_value, axis=1)
    out["mes"]          = out["data"].dt.to_period("M").astype(str)
    out["dia"]          = out["data"].dt.date

    inst = out["descricao"].map(extract_installment)
    out["parcela_atual"] = pd.to_numeric(inst.map(lambda x: x[0]), errors="coerce")
    out["parcela_total"] = pd.to_numeric(inst.map(lambda x: x[1]), errors="coerce")
    out["eh_parcelado"]  = out["parcela_total"].fillna(0).astype(int) > 1
    out["chave_parcela"] = out["descricao"].map(installment_key)
    out["recorrente_suspeito"] = out.apply(
        lambda r: is_recurring_like(r["descricao"], r.get("categoria")), axis=1)
    out["ignorar_no_orcamento"] = out["tipo"].eq(TYPE_IGNORED)
    out["dedup_status"] = "original"

    return out.sort_values(["data","descricao","valor"]).reset_index(drop=True)


def _impact_value(row: pd.Series) -> float:
    tipo = row.get("tipo")
    abs_val = abs(float(row.get("valor", 0) or 0))
    if tipo in {TYPE_EXPENSE, TYPE_TRANSFER_SENT}:
        return -abs_val
    if tipo in {TYPE_INCOME, TYPE_TRANSFER_RECEIVED, TYPE_CREDIT}:
        return abs_val
    return 0.0

# alias público
transaction_impact_value = _impact_value


# ─── Carga de múltiplos arquivos ──────────────────────────────────────────────
def load_many(files, dedupe_mode: DeduplicateMode = "reconcile") -> pd.DataFrame:
    frames = []
    totals = {"orig": 0, "final": 0, "removed": 0, "adjusted": 0}
    for file in files:
        name  = getattr(file, "name", str(file) if isinstance(file, (str, bytes)) else "arquivo.csv")
        frame = read_csv_flexible(file, name, dedupe_mode=dedupe_mode)
        rep   = frame.attrs.get("dedupe_report", {})
        totals["orig"]     += rep.get("original_rows", len(frame))
        totals["final"]    += rep.get("final_rows", len(frame))
        totals["removed"]  += rep.get("removed_rows", 0)
        totals["adjusted"] += rep.get("groups_adjusted", 0)
        frames.append(frame)

    if not frames:
        return pd.DataFrame()

    out = (pd.concat(frames, ignore_index=True)
             .sort_values(["data","descricao","valor"])
             .reset_index(drop=True))

    # Remover exatos duplicados entre arquivos (mesmo CSV enviado duas vezes)
    before = len(out)
    out = out.drop_duplicates(subset=["data","descricao_norm","valor"], keep="first").reset_index(drop=True)
    cross = before - len(out)
    out.attrs["dedupe_report"] = {
        "mode": dedupe_mode,
        "original_rows": int(totals["orig"]),
        "final_rows": int(len(out)),
        "removed_rows": int(totals["removed"] + cross),
        "groups_adjusted": int(totals["adjusted"] + cross),
        "cross_file_removed": int(cross),
    }
    return out


# ─── Métricas ─────────────────────────────────────────────────────────────────
def aggregate_metrics(df: pd.DataFrame, renda_mensal: float = 0.0,
                      meta_economia: float = 0.20) -> dict:
    _empty = {
        "total_gastos_bruto": 0.0, "total_entradas": 0.0, "total_estornos": 0.0,
        "gasto_liquido": 0.0, "pagamentos_fatura": 0.0, "total_ignorado": 0.0,
        "transferencias_enviadas": 0.0, "transferencias_recebidas": 0.0,
        "saldo_estimado": 0.0, "taxa_economia": 0.0, "top_category": "-",
        "qtd_transacoes": 0, "ticket_medio": 0.0, "parcelas_futuras": 0.0,
        "score": 0, "renda_base": 0.0, "meta_economia_valor": 0.0,
        "gastos_essenciais": 0.0, "gastos_variaveis": 0.0,
    }
    if df.empty:
        return _empty

    expenses_df = df[df["tipo"].isin([TYPE_EXPENSE])].copy()   # apenas gastos reais
    income_df   = df[df["tipo"] == TYPE_INCOME].copy()
    credits_df  = df[df["tipo"] == TYPE_CREDIT].copy()
    ignored_df  = df[df["tipo"] == TYPE_IGNORED].copy()
    tsent_df    = df[df["tipo"] == TYPE_TRANSFER_SENT].copy()
    trecv_df    = df[df["tipo"] == TYPE_TRANSFER_RECEIVED].copy()

    total_gastos_bruto = expenses_df["valor_abs"].sum()
    total_entradas     = income_df["valor_abs"].sum()
    total_estornos     = credits_df["valor_abs"].sum()
    total_ignorado     = ignored_df["valor_abs"].sum()
    pagamentos_fatura  = ignored_df.loc[
        ignored_df["subtipo"].eq("Pagamento de fatura"), "valor_abs"].sum()

    gasto_liquido  = max(total_gastos_bruto - total_estornos, 0.0)
    renda_base     = float(renda_mensal or 0.0) if renda_mensal and renda_mensal > 0 else total_entradas
    saldo_estimado = renda_base - gasto_liquido
    taxa_economia  = saldo_estimado / renda_base if renda_base > 0 else 0.0

    cat        = category_table(df)
    top_cat    = cat.iloc[0]["categoria"] if not cat.empty else "-"

    parcelado        = expenses_df[expenses_df["eh_parcelado"]]
    parcelas_futuras = estimate_future_installments(parcelado)
    score            = calculate_score(gasto_liquido, renda_base, pagamentos_fatura, parcelas_futuras, expenses_df)

    essenciais = expenses_df[expenses_df["categoria"].isin(ESSENTIAL_CATEGORIES)]["valor_abs"].sum()
    variaveis  = expenses_df[expenses_df["categoria"].isin(VARIABLE_CATEGORIES)]["valor_abs"].sum()

    return {
        "total_gastos_bruto":        float(total_gastos_bruto),
        "total_entradas":            float(total_entradas),
        "total_estornos":            float(total_estornos),
        "gasto_liquido":             float(gasto_liquido),
        "pagamentos_fatura":         float(pagamentos_fatura),
        "total_ignorado":            float(total_ignorado),
        "transferencias_enviadas":   float(tsent_df["valor_abs"].sum()),
        "transferencias_recebidas":  float(trecv_df["valor_abs"].sum()),
        "saldo_estimado":            float(saldo_estimado),
        "taxa_economia":             float(taxa_economia),
        "top_category":              top_cat,
        "qtd_transacoes":            int(len(df)),
        "qtd_gastos":                int(len(expenses_df)),
        "ticket_medio":              float(gasto_liquido / max(len(expenses_df), 1)),
        "parcelas_futuras":          float(parcelas_futuras),
        "score":                     score,
        "renda_base":                float(renda_base),
        "meta_economia_valor":       float(renda_base * meta_economia if renda_base > 0 else 0.0),
        "gastos_essenciais":         float(essenciais),
        "gastos_variaveis":          float(variaveis),
    }


# ─── Parcelas futuras ─────────────────────────────────────────────────────────
def estimate_future_installments(parcelado: pd.DataFrame) -> float:
    if parcelado.empty:
        return 0.0
    temp = parcelado.dropna(subset=["parcela_atual","parcela_total"]).copy()
    if temp.empty:
        return 0.0
    future = 0.0
    for _, group in temp.groupby("chave_parcela", dropna=False):
        row = group.sort_values(
            ["parcela_total","parcela_atual","data"], ascending=[False,False,False]).iloc[0]
        cur  = int(row["parcela_atual"])
        tot  = int(row["parcela_total"])
        future += abs(float(row["valor"])) * max(tot - cur, 0)
    return float(future)


# ─── Score ────────────────────────────────────────────────────────────────────
def calculate_score(gasto_liquido: float, renda_base: float, pagamentos: float,
                    parcelas_futuras: float, gastos_df: pd.DataFrame) -> int:
    score = 100
    if renda_base > 0:
        ratio = gasto_liquido / renda_base
        if ratio > 1.0:    score -= 35
        elif ratio > 0.85: score -= 25
        elif ratio > 0.70: score -= 15
        elif ratio < 0.55: score += 5
    else:
        score -= 20

    if parcelas_futuras > 0 and renda_base > 0:
        pf = parcelas_futuras / renda_base
        if pf > 1.5:   score -= 20
        elif pf > 0.8: score -= 12
        elif pf > 0.3: score -= 6

    if not gastos_df.empty:
        cat = gastos_df.groupby("categoria")["valor_abs"].sum()
        total = cat.sum()
        if total > 0:
            var = cat[cat.index.isin(VARIABLE_CATEGORIES)].sum() / total
            if var > 0.55: score -= 10

    return max(0, min(100, int(round(score))))


# ─── Tabelas derivadas ────────────────────────────────────────────────────────
def category_table(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["categoria","valor","participacao"])
    # Apenas gastos reais (sem TYPE_TRANSFER_SENT para não distorcer o orçamento)
    temp = df[df["tipo"] == TYPE_EXPENSE].copy()
    if temp.empty:
        return pd.DataFrame(columns=["categoria","valor","participacao"])
    # Subtrair créditos da mesma categoria para mostrar impacto líquido
    credits = df[df["tipo"] == TYPE_CREDIT].copy()
    agg_exp = temp.groupby("categoria")["valor_abs"].sum()
    agg_cred = credits.groupby("categoria")["valor_abs"].sum() if not credits.empty else pd.Series(dtype=float)
    net = (agg_exp - agg_cred.reindex(agg_exp.index, fill_value=0)).clip(lower=0)
    out = net.reset_index().rename(columns={"valor_abs": "valor"})
    out = out[out["valor"] > 0.005].sort_values("valor", ascending=False).reset_index(drop=True)
    total = out["valor"].sum()
    out["participacao"] = out["valor"] / total if total else 0
    return out


def merchant_table(df: pd.DataFrame, limit: int = 15) -> pd.DataFrame:
    gastos = df[df["tipo"] == TYPE_EXPENSE].copy()
    if gastos.empty:
        return pd.DataFrame(columns=["descricao","categoria","valor","qtd"])
    out = gastos.groupby(["descricao","categoria"], as_index=False).agg(
        valor=("valor_abs","sum"), qtd=("valor_abs","count"))
    return out.sort_values("valor", ascending=False).head(limit)


def installment_table(df: pd.DataFrame) -> pd.DataFrame:
    parcelas = df[(df["tipo"] == TYPE_EXPENSE) & df["eh_parcelado"]].copy()
    if parcelas.empty:
        return pd.DataFrame(columns=["descricao","categoria","parcela_atual",
                                     "parcela_total","valor_parcela","valor_futuro"])
    rows = []
    for _, group in parcelas.groupby("chave_parcela", dropna=False):
        row = group.sort_values(["parcela_total","parcela_atual","data"],
                                ascending=[False,False,False]).iloc[0].copy()
        row["valor_parcela"] = abs(float(row["valor"]))
        row["valor_futuro"]  = row["valor_parcela"] * max(
            int(row["parcela_total"]) - int(row["parcela_atual"]), 0)
        rows.append(row)
    out = pd.DataFrame(rows)
    cols = ["descricao","categoria","parcela_atual","parcela_total","valor_parcela","valor_futuro"]
    return out[cols].sort_values("valor_futuro", ascending=False).reset_index(drop=True)


def recurring_table(df: pd.DataFrame) -> pd.DataFrame:
    rec = df[(df["tipo"] == TYPE_EXPENSE) & df["recorrente_suspeito"]].copy()
    if rec.empty:
        return pd.DataFrame(columns=["descricao","categoria","valor","qtd","meses"])
    out = rec.groupby(["descricao","categoria"], as_index=False).agg(
        valor=("valor_abs","sum"),
        qtd=("valor_abs","count"),
        meses=("mes", lambda s: ", ".join(sorted(set(map(str, s)))))
    )
    return out.sort_values("valor", ascending=False).reset_index(drop=True)


def monthly_table(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["mes","gastos","entradas","estornos","ignorado","saldo"])
    temp = df.copy()
    temp["gastos"]   = temp.apply(lambda r: r["valor_abs"] if r["tipo"] == TYPE_EXPENSE else 0.0, axis=1)
    temp["entradas"] = temp.apply(lambda r: r["valor_abs"] if r["tipo"] == TYPE_INCOME  else 0.0, axis=1)
    temp["estornos"] = temp.apply(lambda r: r["valor_abs"] if r["tipo"] == TYPE_CREDIT  else 0.0, axis=1)
    temp["ignorado"] = temp.apply(lambda r: r["valor_abs"] if r["tipo"] == TYPE_IGNORED else 0.0, axis=1)
    out = temp.groupby("mes", as_index=False).agg(
        gastos=("gastos","sum"), entradas=("entradas","sum"),
        estornos=("estornos","sum"), ignorado=("ignorado","sum"))
    out["saldo"] = out["entradas"] - (out["gastos"] - out["estornos"])
    return out


def daily_cashflow(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["data","movimento","saldo_acumulado"])
    out = df.groupby("dia", as_index=False)["valor_impacto"].sum().rename(
        columns={"dia":"data","valor_impacto":"movimento"})
    out = out.sort_values("data")
    out["saldo_acumulado"] = out["movimento"].cumsum()
    return out


def type_summary_table(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["tipo","qtd","valor_abs"])
    out = df.groupby("tipo", as_index=False).agg(qtd=("tipo","count"), valor_abs=("valor_abs","sum"))
    order = {n: i for i, n in enumerate(ALL_TYPES_ORDER)}
    out["_o"] = out["tipo"].map(order).fillna(99)
    return out.sort_values("_o").drop(columns=["_o"]).reset_index(drop=True)


def data_quality_report(df: pd.DataFrame) -> dict:
    rep = df.attrs.get("dedupe_report", {}).copy()
    rep.setdefault("original_rows", len(df))
    rep.setdefault("final_rows", len(df))
    rep.setdefault("removed_rows", 0)
    rep.setdefault("groups_adjusted", 0)
    rep["ignored_count"]   = int(df["tipo"].eq(TYPE_IGNORED).sum()) if not df.empty else 0
    rep["payment_count"]   = int(((df["tipo"] == TYPE_IGNORED) &
                                  (df["subtipo"] == "Pagamento de fatura")).sum()) if not df.empty else 0
    rep["installment_count"] = int(df["eh_parcelado"].sum()) if not df.empty else 0
    return rep


# ─── Sugestões inteligentes ──────────────────────────────────────────────────
def make_suggestions(df: pd.DataFrame, metrics: dict, renda_mensal: float = 0.0) -> list[dict]:
    sug: list[dict] = []
    if not metrics:
        return sug

    renda    = metrics.get("renda_base", 0.0)
    gasto    = metrics.get("gasto_liquido", 0.0)
    saldo    = metrics.get("saldo_estimado", 0.0)
    taxa     = metrics.get("taxa_economia", 0.0)
    parcelas = metrics.get("parcelas_futuras", 0.0)
    score    = metrics.get("score", 0)
    pag      = metrics.get("pagamentos_fatura", 0.0)
    variaveis = metrics.get("gastos_variaveis", 0.0)

    if pag > 0:
        sug.append({
            "titulo": "Pagamentos de fatura ignorados corretamente",
            "impacto": "Dados",
            "acao": f"O app encontrou {format_brl(pag)} em quitação de fatura e deixou fora dos gastos.",
            "motivo": "Contar o pagamento da fatura duplicaria as compras que já aparecem no extrato do cartão."
        })

    if renda <= 0:
        sug.append({
            "titulo": "Informe sua renda mensal para diagnóstico mais preciso",
            "impacto": "Alto",
            "acao": "Digite salário líquido, adiantamento e renda extra no menu lateral.",
            "motivo": "Sem renda base, não é possível medir margem, reserva e comprometimento."
        })
    elif gasto > renda:
        sug.append({
            "titulo": "Gastos acima da renda — situação crítica",
            "impacto": "Crítico",
            "acao": f"Corte ao menos {format_brl(gasto - renda)} de gastos variáveis este mês.",
            "motivo": "Gastar mais do que entra gera dívida e compromete os meses seguintes."
        })
    elif taxa < 0.10:
        sug.append({
            "titulo": "Margem muito pequena — abaixo de 10%",
            "impacto": "Alto",
            "acao": f"Tente separar pelo menos {format_brl(renda * 0.10)} por mês para começar.",
            "motivo": "Margem abaixo de 10% deixa qualquer imprevisto virar dívida."
        })
    elif taxa >= 0.20:
        sug.append({
            "titulo": "Ótima margem — hora de acelerar a reserva",
            "impacto": "Positivo",
            "acao": f"Direcione {format_brl(renda * 0.20)} para reserva em Tesouro Selic ou CDB com liquidez diária.",
            "motivo": "Com margem acima de 20%, o próximo passo é ter 6 meses de despesas guardados."
        })

    cat = category_table(df)
    if not cat.empty:
        top = cat.iloc[0]
        if top["participacao"] > 0.30:
            sug.append({
                "titulo": f"{top['categoria']} consome {top['participacao']:.0%} dos gastos",
                "impacto": "Médio",
                "acao": f"Defina um teto mensal para {top['categoria']} e revise os maiores lançamentos.",
                "motivo": "Uma categoria com mais de 30% pode ser otimizada com pequenos ajustes."
            })

    rec = recurring_table(df)
    if not rec.empty:
        total_rec = rec["valor"].sum()
        names = ", ".join(rec["descricao"].unique()[:3])
        sug.append({
            "titulo": "Assinaturas e recorrentes — revise o que usa",
            "impacto": "Médio",
            "acao": f"Você tem {format_brl(total_rec)} em recorrentes: {names}. Cancele o que não usa.",
            "motivo": "Cobranças mensais pequenas somam valores significativos ao longo do ano."
        })

    if parcelas > 0:
        impacto = "Alto" if renda > 0 and parcelas / renda > 0.5 else "Médio"
        sug.append({
            "titulo": "Parcelas futuras comprometem meses seguintes",
            "impacto": impacto,
            "acao": f"Há {format_brl(parcelas)} ainda a vencer. Evite novas parcelas até quitar.",
            "motivo": "Parcelamento reduz liberdade financeira e impede investimento nos próximos meses."
        })

    if renda > 0 and variaveis > 0 and variaveis / renda > 0.40:
        sug.append({
            "titulo": "Gastos variáveis acima de 40% da renda",
            "impacto": "Médio",
            "acao": f"Reduza {format_brl(variaveis - renda * 0.30)} nos variáveis para chegar a 30% da renda.",
            "motivo": "Gastos variáveis (compras, lazer, alimentação fora) são os mais fáceis de cortar."
        })

    if saldo > 0 and renda > 0:
        sug.append({
            "titulo": "Caminho recomendado para o dinheiro guardado",
            "impacto": "Educativo",
            "acao": ("① Reserva de emergência (6× despesas essenciais) em Tesouro Selic ou CDB diário "
                     "② Metas de curto prazo em renda fixa "
                     "③ Investimentos de maior prazo apenas depois."),
            "motivo": "A ordem importa: liquidez e segurança antes de rentabilidade."
        })

    if score < 60:
        sug.append({
            "titulo": "Score baixo — foque em controle, não em rentabilidade",
            "impacto": "Alto",
            "acao": "Congele parcelas, reduza variáveis e acompanhe o dashboard semanalmente.",
            "motivo": "Com score abaixo de 60, o maior ganho vem de organizar, não de aplicar melhor."
        })

    return sug[:9]


# ─── Detecção de tipo de CSV ──────────────────────────────────────────────────
def detect_csv_source_type(df: pd.DataFrame) -> str:
    """
    Heurística para identificar se o CSV é de fatura do cartão ou extrato de conta corrente.
    Retorna: 'fatura', 'extrato_conta' ou 'desconhecido'.
    """
    if df.empty:
        return "desconhecido"
    ignored = df[df["tipo"] == TYPE_IGNORED]
    # Fatura Nubank: tem "Pagamento recebido" (crédito com valor negativo)
    if not ignored.empty and ignored["subtipo"].eq("Pagamento de fatura").any():
        return "fatura"
    # Extrato de conta: tem transferências recebidas e enviadas
    has_trecv = (df["tipo"] == TYPE_TRANSFER_RECEIVED).any()
    has_tsent = (df["tipo"] == TYPE_TRANSFER_SENT).any()
    if has_trecv or has_tsent:
        return "extrato_conta"
    return "desconhecido"
