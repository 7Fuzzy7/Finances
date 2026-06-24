import io
import pandas as pd

from src.finance_engine import (
    TYPE_IGNORED,
    aggregate_metrics,
    categorize,
    extract_installment,
    load_many,
    normalize_transactions,
)


def _csv(text: str):
    f = io.StringIO(text)
    f.name = "teste.csv"
    return f


def test_pagamento_recebido_is_ignored():
    df = normalize_transactions(pd.DataFrame({
        "date": ["2026-06-03"],
        "title": ["Pagamento recebido"],
        "amount": ["- 1.311,82"],
    }))
    assert df.iloc[0]["tipo"] == TYPE_IGNORED
    assert df.iloc[0]["subtipo"] == "Pagamento de fatura"


def test_reconcile_drogaria_duplicates_keeps_net_charge():
    df = load_many([_csv("""date,title,amount
2026-06-22,Drogaria Sao Paulo - NuPay,"21,02"
2026-06-22,Drogaria Sao Paulo - NuPay,"21,02"
2026-06-22,Drogaria Sao Paulo - NuPay,"21,02"
2026-06-22,Drogaria Sao Paulo - NuPay,"- 21,02"
2026-06-22,Drogaria Sao Paulo - NuPay,"- 21,02"
""")], dedupe_mode="reconcile")
    assert len(df) == 1
    assert round(df.iloc[0]["valor_abs"], 2) == 21.02


def test_sao_paulo_alone_is_not_pharmacy():
    assert categorize("Sao Paulo Parafusos") != "Saúde/Farmácia"
    assert categorize("Drogaria Sao Paulo - NuPay") == "Saúde/Farmácia"
    assert categorize("Ebn*Canva04909") == "Assinaturas"


def test_pix_word_alone_is_not_transfer():
    df = normalize_transactions(pd.DataFrame({
        "date": ["2026-06-09"],
        "title": ["PIX Marketplace"],
        "amount": ["48,90"],
    }))
    assert df.iloc[0]["tipo"] == "Gasto"
    assert df.iloc[0]["categoria"] != "Transferências"


def test_installment_regex_does_not_capture_dates():
    assert extract_installment("compra em 08/12/2026") == (None, None)
    assert extract_installment("Dermanyluiz - Parcela 1/3") == (1, 3)
    assert extract_installment("Tokio Marine*Auto08d12") == (8, 12)


def test_july_nubank_net_metrics():
    df = load_many([_csv(open("data/exemplo_nubank.csv", encoding="utf-8").read())], dedupe_mode="reconcile")
    metrics = aggregate_metrics(df, renda_mensal=1118.00)
    assert round(metrics["pagamentos_fatura"], 2) == 1311.82
    assert round(metrics["gasto_liquido"], 2) == 986.40
