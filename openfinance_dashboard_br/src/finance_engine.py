from __future__ import annotations

import re
import unicodedata
from io import BytesIO
from typing import Iterable, Optional, Literal

import pandas as pd

# Tipos principais usados pelo app.
TYPE_EXPENSE = "Gasto"
TYPE_INCOME = "Entrada"
TYPE_CREDIT = "Estorno/Crédito"
TYPE_IGNORED = "Ignorado"
TYPE_TRANSFER_SENT = "Transferência enviada"
TYPE_TRANSFER_RECEIVED = "Transferência recebida"

IMPACT_TYPES = [TYPE_EXPENSE, TYPE_INCOME, TYPE_CREDIT]
ALL_TYPES_ORDER = [
    TYPE_EXPENSE,
    TYPE_INCOME,
    TYPE_CREDIT,
    TYPE_TRANSFER_SENT,
    TYPE_TRANSFER_RECEIVED,
    TYPE_IGNORED,
]

DATE_COLUMNS = ["date", "data", "Data", "DATA", "Date", "transaction_date", "posted_date"]
TITLE_COLUMNS = [
    "title",
    "descricao",
    "descrição",
    "Descrição",
    "description",
    "Description",
    "histórico",
    "historico",
    "Historico",
    "memo",
    "nome",
]
AMOUNT_COLUMNS = ["amount", "valor", "Valor", "VALOR", "value", "Value", "quantia"]

# Regras em texto normalizado, sem acento e minúsculo.
# A ordem importa: regras mais específicas vêm antes de regras genéricas.
CATEGORY_RULES: list[tuple[str, list[str]]] = [
    ("Alimentação", [
        r"\bifood\b", r"\brestaur", r"\bcomer", r"\blanch", r"\bpadaria\b", r"\bburg", r"\bpizza\b", r"santo agostinho",
    ]),
    ("Combustível", [
        r"\bauto posto\b", r"\bposto\b", r"\bshell\b", r"\bipiranga\b", r"\bpetrobras\b", r"\bgasolina\b", r"\betanol\b",
    ]),
    ("Saúde/Farmácia", [
        # Não usar apenas "sao paulo": isso captura cidade, loja, universidade, etc.
        r"\bdrogaria sao paulo\b", r"\bdrog sao paulo\b", r"\bdrogaria\b", r"\bdrog\b", r"\bfarm", r"\braia\b", r"\bdrogasil\b", r"\bpacheco\b", r"\bpague menos\b",
    ]),
    ("Assinaturas", [
        r"spotify", r"netflix", r"amazon prime", r"prime video", r"canva", r"google", r"apple", r"icloud", r"microsoft", r"adobe", r"disney", r"hbo", r"\bmax\b",
    ]),
    ("Seguro/Proteção", [
        r"\btokio\b", r"\bseguro\b", r"\bblinda\b", r"\bporto seguro\b", r"\bmarine\b", r"\bprote[cç][aã]o\b",
    ]),
    ("Compras", [
        r"\bmercado\s*livre\b", r"\bmercadolivre\b", r"\bamericanas\b", r"\bmagalu\b", r"\bshopee\b", r"\bshein\b", r"\bamazon\b", r"\bkalunga\b", r"\bcasas bahia\b", r"\baliexpress\b",
    ]),
    ("Mercado", [
        r"\bsupermerc", r"\bmercado\b", r"\bcarrefour\b", r"\bextra\b", r"\batacad", r"\bassai\b", r"\bpao de acucar\b", r"\bpa[oã]o de a[cç]ucar\b",
    ]),
    ("Transporte", [
        r"\buber\b", r"\b99\b", r"\btop sp\b", r"\bbilhete\b", r"\bmetro\b", r"\btrem\b", r"\bestacion", r"\bpedagio\b", r"\bsem parar\b",
    ]),
    ("Educação", [
        r"\bfiap\b", r"\bcurso\b", r"\budemy\b", r"\balura\b", r"\bfaculdade\b", r"\bescola\b", r"\blivro\b",
    ]),
    ("Serviços", [
        r"\bclaro\b", r"\bvivo\b", r"\btim\b", r"\boi\b", r"\binternet\b", r"\bservic", r"\bomny\b", r"\bconta de luz\b", r"\bsabesp\b", r"\benel\b",
    ]),
]

ESSENTIAL_CATEGORIES = {"Alimentação", "Mercado", "Transporte", "Combustível", "Saúde/Farmácia", "Serviços"}
VARIABLE_CATEGORIES = {"Alimentação", "Compras", "Lazer", "Assinaturas", "Combustível"}

DeduplicateMode = Literal["reconcile", "exact", "none"]


def strip_accents(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def normalize_text(text: object) -> str:
    value = "" if pd.isna(text) else str(text)
    value = strip_accents(value).lower().strip()
    value = re.sub(r"\s+", " ", value)
    return value


def _clean_text(value: object) -> str:
    if pd.isna(value):
        return ""
    return re.sub(r"\s+", " ", str(value).strip())


def parse_brl_number(value: object) -> float:
    """Parse BR/US money formats: '1.311,82', '- 49,00', '-49.00', 49.0."""
    if pd.isna(value):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)

    s = str(value).strip().replace("R$", "").replace("\xa0", " ")
    s = re.sub(r"\s+", "", s)
    if s in {"", "-", "--"}:
        return 0.0

    negative = s.startswith("-") or s.endswith("-") or s.startswith("(") and s.endswith(")")
    s = s.replace("-", "").replace("(", "").replace(")", "")

    # BR decimal comma, e.g. 1.311,82
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
    sign = "-" if value < 0 else ""
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


def read_csv_flexible(file_obj, source_name: str = "arquivo", dedupe_mode: DeduplicateMode = "reconcile") -> pd.DataFrame:
    """Read CSV from upload/path, detecting delimiter and Nubank-like columns."""
    try:
        if hasattr(file_obj, "read"):
            raw = file_obj.read()
            if hasattr(file_obj, "seek"):
                file_obj.seek(0)
            data = raw.encode("utf-8") if isinstance(raw, str) else raw
            buffer = BytesIO(data)
            try:
                raw_df = pd.read_csv(buffer, sep=None, engine="python", encoding="utf-8")
            except UnicodeDecodeError:
                buffer.seek(0)
                raw_df = pd.read_csv(buffer, sep=None, engine="python", encoding="latin-1")
        else:
            try:
                raw_df = pd.read_csv(file_obj, sep=None, engine="python", encoding="utf-8")
            except UnicodeDecodeError:
                raw_df = pd.read_csv(file_obj, sep=None, engine="python", encoding="latin-1")
    except Exception as exc:
        raise ValueError(f"Não consegui ler o CSV '{source_name}'. Verifique se o arquivo está no formato correto. Erro: {exc}") from exc

    if raw_df.empty:
        raise ValueError(f"O CSV '{source_name}' está vazio.")

    out = normalize_transactions(raw_df, source_name=source_name)
    out = apply_deduplication(out, mode=dedupe_mode)
    return out


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
    if out["data"].isna().mean() > 0.5:
        out["data"] = pd.to_datetime(df[date_col], errors="coerce", dayfirst=True)

    out["descricao"] = df[title_col].map(_clean_text)
    out["descricao_norm"] = out["descricao"].map(normalize_text)
    out["valor"] = df[amount_col].map(parse_brl_number).astype(float)
    out["arquivo"] = source_name

    out = out.dropna(subset=["data"])
    out = out[out["descricao"].astype(str).str.len() > 0]
    out = out[out["valor"].notna()]

    classification = out.apply(classify_transaction_full, axis=1, result_type="expand")
    classification.columns = ["tipo", "subtipo"]
    out = pd.concat([out, classification], axis=1)

    out["categoria"] = out.apply(lambda row: categorize(row["descricao"], row.get("tipo"), row.get("subtipo")), axis=1)
    out["valor_abs"] = out["valor"].abs()
    out["valor_impacto"] = out.apply(transaction_impact_value, axis=1)
    out["mes"] = out["data"].dt.to_period("M").astype(str)
    out["dia"] = out["data"].dt.date

    installments = out["descricao"].map(extract_installment)
    out["parcela_atual"] = installments.map(lambda x: x[0])
    out["parcela_total"] = installments.map(lambda x: x[1])
    out["parcela_atual"] = pd.to_numeric(out["parcela_atual"], errors="coerce")
    out["parcela_total"] = pd.to_numeric(out["parcela_total"], errors="coerce")
    out["eh_parcelado"] = out["parcela_total"].fillna(0).astype(int) > 1
    out["chave_parcela"] = out["descricao"].map(installment_key)
    out["recorrente_suspeito"] = out.apply(lambda row: is_recurring_like(row["descricao"], row.get("categoria")), axis=1)
    out["ignorar_no_orcamento"] = out["tipo"].eq(TYPE_IGNORED)
    out["dedup_status"] = "original"

    return out.sort_values(["data", "descricao", "valor"]).reset_index(drop=True)


def is_payment_settlement(desc_norm: str) -> bool:
    return bool(re.search(r"\bpagamento\s+(recebido|de\s+fatura|fatura|cartao|cartão)\b", desc_norm))


def is_refund_credit(desc_norm: str) -> bool:
    return bool(re.search(r"\b(estorno|credito|crédito|reembolso|chargeback|cancelamento)\b", desc_norm))


def is_transfer_received(desc_norm: str) -> bool:
    return bool(re.search(r"\b(transferencia|transferência)\s+recebida\b", desc_norm) or re.search(r"\bpix\s+recebido\b", desc_norm))


def is_transfer_sent(desc_norm: str) -> bool:
    return bool(re.search(r"\b(transferencia|transferência)\s+enviada\b", desc_norm) or re.search(r"\bpix\s+enviado\b", desc_norm))


def classify_transaction_full(row: pd.Series) -> tuple[str, str]:
    desc = normalize_text(row.get("descricao", ""))
    value = float(row.get("valor", 0) or 0)

    # Fatura Nubank: "Pagamento recebido" é quitação da fatura, não gasto nem renda.
    # Extrato de conta: "Pagamento de fatura" é transferência interna para o cartão.
    if is_payment_settlement(desc):
        return TYPE_IGNORED, "Pagamento de fatura"

    if is_transfer_received(desc):
        return TYPE_TRANSFER_RECEIVED, "Pix/transferência recebida"

    if is_transfer_sent(desc):
        return TYPE_TRANSFER_SENT, "Pix/transferência enviada"

    if is_refund_credit(desc):
        return TYPE_CREDIT, "Estorno/Reembolso"

    if re.search(r"\b(compra no debito|compra no débito|debito|débito)\b", desc):
        return TYPE_EXPENSE, "Compra no débito"

    if re.search(r"\b(salario|salário|recebida|deposito|depósito|provento|rendimento|flash)\b", desc):
        return TYPE_INCOME, "Entrada identificada"

    # Em faturas Nubank, valores negativos geralmente são créditos/estornos.
    if value < 0:
        return TYPE_CREDIT, "Crédito na fatura"

    return TYPE_EXPENSE, "Compra"


def classify_transaction(row: pd.Series) -> str:
    """Compatibility wrapper: return only the main type."""
    return classify_transaction_full(row)[0]


def categorize(description: str, tipo: str | None = None, subtipo: str | None = None) -> str:
    desc = normalize_text(description)

    if tipo == TYPE_IGNORED:
        return "Ignorados"
    if tipo in {TYPE_TRANSFER_SENT, TYPE_TRANSFER_RECEIVED}:
        return "Transferências"

    for category, patterns in CATEGORY_RULES:
        if any(re.search(pattern, desc) for pattern in patterns):
            return category

    if extract_installment(description)[1]:
        return "Parcelas"
    if tipo == TYPE_CREDIT:
        return "Estornos/Créditos"
    if tipo == TYPE_INCOME:
        return "Entradas"
    return "Outros"


def transaction_impact_value(row: pd.Series) -> float:
    """Signed budget impact: expense negative, income/credit positive, ignored zero."""
    tipo = row.get("tipo")
    value_abs = abs(float(row.get("valor", 0) or 0))
    if tipo in {TYPE_EXPENSE, TYPE_TRANSFER_SENT}:
        return -value_abs
    if tipo in {TYPE_INCOME, TYPE_TRANSFER_RECEIVED, TYPE_CREDIT}:
        return value_abs
    return 0.0


def extract_installment(description: str) -> tuple[Optional[int], Optional[int]]:
    """Extract installments without confusing dates like 08/12 with parcels.

    Accepted examples:
    - 'Dermanyluiz - Parcela 1/3'
    - 'Mercado Livre - parc. 8/12'
    - 'Tokio Marine*Auto08d12' (Nubank compact format)

    Rejected examples:
    - 'vencimento 08/12'
    - 'compra em 08/12/2026'
    """
    desc = normalize_text(description)
    patterns = [
        r"\bparcela\s*(\d{1,2})\s*/\s*(\d{1,2})\b",
        r"\bparc\.?\s*(\d{1,2})\s*/\s*(\d{1,2})\b",
        r"\b(\d{1,2})\s*/\s*(\d{1,2})\s*(?:parcelas?|parc\.?|x)\b",
        r"\bparcela\s*(\d{1,2})\s*(?:de|d)\s*(\d{1,2})\b",
        # Nubank compact format: Auto08d12, 05d12 etc.
        r"(?<!\d)(\d{1,2})d(\d{1,2})(?!\d)",
    ]
    for pattern in patterns:
        match = re.search(pattern, desc, flags=re.IGNORECASE)
        if not match:
            continue
        try:
            current, total = int(match.group(1)), int(match.group(2))
        except Exception:
            continue
        if 1 <= current <= total <= 60:
            return current, total
    return None, None


def installment_key(description: str) -> str:
    desc = normalize_text(description)
    desc = re.sub(r"\bparcela\s*\d{1,2}\s*/\s*\d{1,2}\b", " ", desc)
    desc = re.sub(r"\bparc\.?\s*\d{1,2}\s*/\s*\d{1,2}\b", " ", desc)
    desc = re.sub(r"\b\d{1,2}\s*/\s*\d{1,2}\s*(?:parcelas?|parc\.?|x)\b", " ", desc)
    desc = re.sub(r"(?<!\d)\d{1,2}d\d{1,2}(?!\d)", " ", desc)
    desc = re.sub(r"[^a-z0-9]+", " ", desc).strip()
    return desc[:90]


def is_recurring_like(description: str, category: str | None = None) -> bool:
    desc = normalize_text(description)
    if category in {"Assinaturas", "Seguro/Proteção"}:
        return True
    return bool(re.search(r"\b(spotify|netflix|canva|icloud|google|microsoft|adobe|seguro|blinda|assinatura|prime|mensalidade)\b", desc))


def apply_deduplication(df: pd.DataFrame, mode: DeduplicateMode = "reconcile") -> pd.DataFrame:
    if df.empty or mode == "none":
        out = df.copy()
        out.attrs["dedupe_report"] = {
            "mode": mode,
            "original_rows": int(len(df)),
            "final_rows": int(len(out)),
            "removed_rows": 0,
            "groups_adjusted": 0,
        }
        return out

    if mode == "exact":
        before = len(df)
        out = df.drop_duplicates(subset=["data", "descricao_norm", "valor"], keep="first").copy()
        out.attrs["dedupe_report"] = {
            "mode": mode,
            "original_rows": int(before),
            "final_rows": int(len(out)),
            "removed_rows": int(before - len(out)),
            "groups_adjusted": int(before - len(out)),
        }
        return out.sort_values(["data", "descricao", "valor"]).reset_index(drop=True)

    # mode == "reconcile": cancel matching positive/negative repeated rows of same date, description and amount.
    # This solves cases like 3 charges + 2 reversals from the same store: final budget impact = 1 charge.
    rows: list[pd.Series] = []
    adjusted_groups = 0
    removed_rows = 0
    temp = df.copy()
    temp["_dedupe_amount_key"] = temp["valor_abs"].round(2)
    keys = ["data", "descricao_norm", "_dedupe_amount_key"]
    for _, group in temp.groupby(keys, sort=False, dropna=False):
        positives = group[group["valor"] > 0]
        negatives = group[group["valor"] < 0]
        if not positives.empty and not negatives.empty:
            cancel_count = min(len(positives), len(negatives))
            adjusted_groups += 1
            removed_rows += cancel_count * 2
            remaining_pos = len(positives) - cancel_count
            remaining_neg = len(negatives) - cancel_count
            if remaining_pos:
                for _, row in positives.head(remaining_pos).iterrows():
                    row = row.copy()
                    row["dedup_status"] = f"conciliado: {len(group)} lançamentos viraram {remaining_pos} cobrança(s)"
                    rows.append(row)
            if remaining_neg:
                for _, row in negatives.head(remaining_neg).iterrows():
                    row = row.copy()
                    row["dedup_status"] = f"conciliado: {len(group)} lançamentos viraram {remaining_neg} crédito(s)"
                    rows.append(row)
        else:
            for _, row in group.iterrows():
                rows.append(row)

    if rows:
        out = pd.DataFrame(rows).drop(columns=["_dedupe_amount_key"], errors="ignore")
    else:
        out = temp.iloc[0:0].drop(columns=["_dedupe_amount_key"], errors="ignore")

    out = out.sort_values(["data", "descricao", "valor"]).reset_index(drop=True)
    out.attrs["dedupe_report"] = {
        "mode": mode,
        "original_rows": int(len(df)),
        "final_rows": int(len(out)),
        "removed_rows": int(removed_rows),
        "groups_adjusted": int(adjusted_groups),
    }
    return out


def load_many(files, dedupe_mode: DeduplicateMode = "reconcile") -> pd.DataFrame:
    frames = []
    total_original = 0
    total_final = 0
    total_removed = 0
    adjusted = 0
    for file in files:
        name = getattr(file, "name", str(file) if isinstance(file, (str, bytes)) else "arquivo.csv")
        frame = read_csv_flexible(file, name, dedupe_mode=dedupe_mode)
        report = frame.attrs.get("dedupe_report", {})
        total_original += report.get("original_rows", len(frame))
        total_final += report.get("final_rows", len(frame))
        total_removed += report.get("removed_rows", 0)
        adjusted += report.get("groups_adjusted", 0)
        frames.append(frame)

    if not frames:
        return pd.DataFrame()

    out = pd.concat(frames, ignore_index=True).sort_values(["data", "descricao", "valor"]).reset_index(drop=True)
    # If the same CSV is uploaded twice, remove exact duplicates across files after individual treatment.
    before_cross = len(out)
    out = out.drop_duplicates(subset=["data", "descricao_norm", "valor"], keep="first").reset_index(drop=True)
    cross_removed = before_cross - len(out)
    out.attrs["dedupe_report"] = {
        "mode": dedupe_mode,
        "original_rows": int(total_original),
        "final_rows": int(len(out)),
        "removed_rows": int(total_removed + cross_removed),
        "groups_adjusted": int(adjusted + cross_removed),
        "cross_file_removed": int(cross_removed),
    }
    return out


def _included(df: pd.DataFrame, include_types: Optional[list[str]] = None) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    if include_types is None:
        include_types = IMPACT_TYPES
    return df[df["tipo"].isin(include_types)].copy()


def aggregate_metrics(df: pd.DataFrame, renda_mensal: float = 0.0, meta_economia: float = 0.20) -> dict:
    if df.empty:
        return {
            "total_gastos_bruto": 0.0, "total_entradas": 0.0, "total_estornos": 0.0, "gasto_liquido": 0.0,
            "pagamentos_fatura": 0.0, "saldo_estimado": 0.0, "taxa_economia": 0.0, "top_category": "-",
            "qtd_transacoes": 0, "ticket_medio": 0.0, "parcelas_futuras": 0.0, "score": 0, "renda_base": 0.0,
            "meta_economia_valor": 0.0, "total_ignorado": 0.0, "transferencias_enviadas": 0.0, "transferencias_recebidas": 0.0,
        }

    expenses_df = df[df["tipo"].isin([TYPE_EXPENSE, TYPE_TRANSFER_SENT])].copy()
    income_df = df[df["tipo"].isin([TYPE_INCOME, TYPE_TRANSFER_RECEIVED])].copy()
    credits_df = df[df["tipo"] == TYPE_CREDIT].copy()
    ignored_df = df[df["tipo"] == TYPE_IGNORED].copy()

    total_gastos_bruto = expenses_df["valor_abs"].sum() if not expenses_df.empty else 0.0
    total_entradas = income_df["valor_abs"].sum() if not income_df.empty else 0.0
    total_estornos = credits_df["valor_abs"].sum() if not credits_df.empty else 0.0
    total_ignorado = ignored_df["valor_abs"].sum() if not ignored_df.empty else 0.0
    pagamentos_fatura = ignored_df.loc[ignored_df["subtipo"].eq("Pagamento de fatura"), "valor_abs"].sum() if not ignored_df.empty else 0.0

    gasto_liquido = max(total_gastos_bruto - total_estornos, 0.0)
    renda_base = float(renda_mensal or 0.0) if renda_mensal and renda_mensal > 0 else total_entradas
    saldo_estimado = renda_base - gasto_liquido if renda_base > 0 else -gasto_liquido
    taxa_economia = (saldo_estimado / renda_base) if renda_base > 0 else 0.0

    cat = category_table(df)
    top_category = cat.iloc[0]["categoria"] if not cat.empty else "-"

    parcelado = expenses_df[expenses_df["eh_parcelado"]]
    parcelas_futuras = estimate_future_installments(parcelado)
    score = calculate_score(gasto_liquido, renda_base, pagamentos_fatura, parcelas_futuras, expenses_df)

    return {
        "total_gastos_bruto": float(total_gastos_bruto),
        "total_entradas": float(total_entradas),
        "total_estornos": float(total_estornos),
        "gasto_liquido": float(gasto_liquido),
        "pagamentos_fatura": float(pagamentos_fatura),
        "total_ignorado": float(total_ignorado),
        "transferencias_enviadas": float(df.loc[df["tipo"].eq(TYPE_TRANSFER_SENT), "valor_abs"].sum()),
        "transferencias_recebidas": float(df.loc[df["tipo"].eq(TYPE_TRANSFER_RECEIVED), "valor_abs"].sum()),
        "saldo_estimado": float(saldo_estimado),
        "taxa_economia": float(taxa_economia),
        "top_category": top_category,
        "qtd_transacoes": int(len(df)),
        "ticket_medio": float(gasto_liquido / max(len(expenses_df), 1)),
        "parcelas_futuras": float(parcelas_futuras),
        "score": score,
        "renda_base": float(renda_base),
        "meta_economia_valor": float(renda_base * meta_economia if renda_base > 0 else 0.0),
    }


def estimate_future_installments(parcelado: pd.DataFrame) -> float:
    if parcelado.empty:
        return 0.0
    temp = parcelado.dropna(subset=["parcela_atual", "parcela_total"]).copy()
    if temp.empty:
        return 0.0
    future_total = 0.0
    for _, group in temp.groupby("chave_parcela", dropna=False):
        group = group.sort_values(["parcela_total", "parcela_atual", "data"], ascending=[False, False, False])
        row = group.iloc[0]
        current = int(row["parcela_atual"])
        total = int(row["parcela_total"])
        remaining = max(total - current, 0)
        future_total += abs(float(row["valor"])) * remaining
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
        cat = gastos_df.groupby("categoria")["valor_abs"].sum()
        total = cat.sum()
        if total > 0:
            variable = cat[cat.index.isin(VARIABLE_CATEGORIES)].sum() / total
            if variable > 0.55:
                score -= 10
    return max(0, min(100, int(round(score))))


def category_table(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["categoria", "valor", "participacao"])
    temp = df[df["tipo"].isin([TYPE_EXPENSE, TYPE_TRANSFER_SENT, TYPE_CREDIT])].copy()
    if temp.empty:
        return pd.DataFrame(columns=["categoria", "valor", "participacao"])
    temp["impacto_categoria"] = temp.apply(
        lambda r: r["valor_abs"] if r["tipo"] in {TYPE_EXPENSE, TYPE_TRANSFER_SENT} else -r["valor_abs"], axis=1
    )
    out = temp.groupby("categoria", as_index=False)["impacto_categoria"].sum().rename(columns={"impacto_categoria": "valor"})
    out = out[out["valor"] > 0.005].sort_values("valor", ascending=False).reset_index(drop=True)
    total = out["valor"].sum()
    out["participacao"] = out["valor"] / total if total else 0
    return out


def merchant_table(df: pd.DataFrame, limit: int = 15) -> pd.DataFrame:
    gastos = df[df["tipo"].isin([TYPE_EXPENSE, TYPE_TRANSFER_SENT])].copy()
    if gastos.empty:
        return pd.DataFrame(columns=["descricao", "categoria", "valor", "qtd"])
    out = gastos.groupby(["descricao", "categoria"], as_index=False).agg(valor=("valor_abs", "sum"), qtd=("valor_abs", "count"))
    return out.sort_values("valor", ascending=False).head(limit)


def installment_table(df: pd.DataFrame) -> pd.DataFrame:
    parcelas = df[(df["tipo"].isin([TYPE_EXPENSE, TYPE_TRANSFER_SENT])) & (df["eh_parcelado"])].copy()
    if parcelas.empty:
        return pd.DataFrame(columns=["descricao", "categoria", "parcela_atual", "parcela_total", "valor_parcela", "valor_futuro"])
    latest_rows = []
    for _, group in parcelas.groupby("chave_parcela", dropna=False):
        row = group.sort_values(["parcela_total", "parcela_atual", "data"], ascending=[False, False, False]).iloc[0].copy()
        row["valor_parcela"] = abs(float(row["valor"]))
        row["valor_futuro"] = row["valor_parcela"] * max(int(row["parcela_total"]) - int(row["parcela_atual"]), 0)
        latest_rows.append(row)
    out = pd.DataFrame(latest_rows)
    cols = ["descricao", "categoria", "parcela_atual", "parcela_total", "valor_parcela", "valor_futuro"]
    return out[cols].sort_values("valor_futuro", ascending=False).reset_index(drop=True)


def recurring_table(df: pd.DataFrame) -> pd.DataFrame:
    rec = df[(df["tipo"].isin([TYPE_EXPENSE, TYPE_TRANSFER_SENT])) & (df["recorrente_suspeito"])].copy()
    if rec.empty:
        return pd.DataFrame(columns=["descricao", "categoria", "valor", "qtd", "meses"])
    out = rec.groupby(["descricao", "categoria"], as_index=False).agg(
        valor=("valor_abs", "sum"),
        qtd=("valor_abs", "count"),
        meses=("mes", lambda s: ", ".join(sorted(set(map(str, s)))))
    )
    return out.sort_values("valor", ascending=False).reset_index(drop=True)


def monthly_table(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["mes", "gastos", "entradas", "estornos", "ignorado", "saldo"])
    temp = df.copy()
    temp["gastos"] = temp.apply(lambda r: r["valor_abs"] if r["tipo"] in {TYPE_EXPENSE, TYPE_TRANSFER_SENT} else 0.0, axis=1)
    temp["entradas"] = temp.apply(lambda r: r["valor_abs"] if r["tipo"] in {TYPE_INCOME, TYPE_TRANSFER_RECEIVED} else 0.0, axis=1)
    temp["estornos"] = temp.apply(lambda r: r["valor_abs"] if r["tipo"] == TYPE_CREDIT else 0.0, axis=1)
    temp["ignorado"] = temp.apply(lambda r: r["valor_abs"] if r["tipo"] == TYPE_IGNORED else 0.0, axis=1)
    out = temp.groupby("mes", as_index=False).agg(gastos=("gastos", "sum"), entradas=("entradas", "sum"), estornos=("estornos", "sum"), ignorado=("ignorado", "sum"))
    out["saldo"] = out["entradas"] - (out["gastos"] - out["estornos"])
    return out


def daily_cashflow(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["data", "movimento", "saldo_acumulado"])
    temp = df.copy()
    out = temp.groupby("data", as_index=False)["valor_impacto"].sum().sort_values("data")
    out = out.rename(columns={"valor_impacto": "movimento"})
    out["saldo_acumulado"] = out["movimento"].cumsum()
    return out


def type_summary_table(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["tipo", "qtd", "valor_abs"])
    out = df.groupby("tipo", as_index=False).agg(qtd=("tipo", "count"), valor_abs=("valor_abs", "sum"))
    order = {name: idx for idx, name in enumerate(ALL_TYPES_ORDER)}
    out["_order"] = out["tipo"].map(order).fillna(99)
    return out.sort_values("_order").drop(columns=["_order"]).reset_index(drop=True)


def data_quality_report(df: pd.DataFrame) -> dict:
    report = df.attrs.get("dedupe_report", {}).copy()
    report.setdefault("original_rows", len(df))
    report.setdefault("final_rows", len(df))
    report.setdefault("removed_rows", 0)
    report.setdefault("groups_adjusted", 0)
    report["ignored_count"] = int(df["tipo"].eq(TYPE_IGNORED).sum()) if not df.empty else 0
    report["payment_count"] = int(((df["tipo"] == TYPE_IGNORED) & (df["subtipo"] == "Pagamento de fatura")).sum()) if not df.empty else 0
    report["installment_count"] = int(df["eh_parcelado"].sum()) if not df.empty else 0
    return report


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
    pagamentos = metrics.get("pagamentos_fatura", 0.0)

    if pagamentos > 0:
        suggestions.append({
            "titulo": "Pagamentos de fatura foram ignorados corretamente",
            "impacto": "Dados",
            "acao": f"O app encontrou {format_brl(pagamentos)} em quitação de fatura e deixou fora dos gastos.",
            "motivo": "Contar pagamento de fatura como gasto duplicaria compras que já aparecem no cartão."
        })

    if renda <= 0:
        suggestions.append({
            "titulo": "Informe sua renda mensal para melhorar o diagnóstico",
            "impacto": "Alto",
            "acao": "Coloque salário líquido, benefícios e renda extra recorrente no menu lateral.",
            "motivo": "Sem renda base, o app não mede margem, capacidade de reserva e comprometimento."
        })
    elif gasto > renda:
        suggestions.append({
            "titulo": "Pare novas parcelas até o orçamento voltar para o positivo",
            "impacto": "Crítico",
            "acao": f"Reduza ao menos {format_brl(gasto - renda)} neste mês para não fechar no negativo.",
            "motivo": "Gastos acima da renda impedem reserva, investimento e estabilidade."
        })
    elif taxa < 0.10:
        suggestions.append({
            "titulo": "Aumente a margem antes de pensar em investimentos de risco",
            "impacto": "Alto",
            "acao": f"Tente separar pelo menos {format_brl(renda * 0.10)} por mês como primeiro alvo.",
            "motivo": "Margem menor que 10% deixa qualquer imprevisto virar dívida."
        })
    elif taxa >= 0.20:
        suggestions.append({
            "titulo": "Sua margem está boa para acelerar a reserva",
            "impacto": "Positivo",
            "acao": f"Direcione cerca de {format_brl(renda * 0.20)} por mês para reserva com liquidez e baixo risco.",
            "motivo": "Antes de buscar rentabilidade, o primeiro objetivo é segurança financeira."
        })

    cats = category_table(df)
    if not cats.empty:
        top = cats.iloc[0]
        if top["participacao"] > 0.35:
            suggestions.append({
                "titulo": f"Categoria dominante: {top['categoria']}",
                "impacto": "Médio",
                "acao": f"Defina um teto mensal para {top['categoria']} e acompanhe semanalmente.",
                "motivo": f"Ela representa {top['participacao']:.0%} dos gastos analisados."
            })

    rec = recurring_table(df)
    if not rec.empty:
        total_rec = rec["valor"].sum()
        suggestions.append({
            "titulo": "Revise assinaturas e cobranças recorrentes",
            "impacto": "Médio",
            "acao": f"Revise {format_brl(total_rec)} em gastos recorrentes identificados.",
            "motivo": "Assinaturas pequenas somadas viram um gasto fixo invisível."
        })

    if parcelas > 0:
        suggestions.append({
            "titulo": "Parcelas futuras já comprometem próximos meses",
            "impacto": "Alto" if renda and parcelas / renda > 0.5 else "Médio",
            "acao": f"Há aproximadamente {format_brl(parcelas)} ainda a vencer em compras parceladas.",
            "motivo": "Parcelamento reduz sua liberdade de decisão nos próximos meses."
        })

    if saldo > 0 and renda > 0:
        suggestions.append({
            "titulo": "Caminho seguro antes de investir",
            "impacto": "Educativo",
            "acao": "1) quitar dívidas caras; 2) montar reserva; 3) metas de curto prazo; 4) investimentos de prazo maior depois disso.",
            "motivo": "O app prioriza estabilidade e liquidez antes de rentabilidade."
        })

    if score < 65:
        suggestions.append({
            "titulo": "Prioridade do mês: controle, não rentabilidade",
            "impacto": "Alto",
            "acao": "Reduza gastos variáveis, congele parcelamentos e acompanhe o dashboard semanalmente.",
            "motivo": "Com score baixo, o maior ganho vem de organização e redução de vazamentos."
        })

    return suggestions[:9]
