from datetime import date
from decimal import Decimal as D

import pytest

from tollgate.checks import (
    CheckContext,
    InvoiceData,
    LineData,
    POData,
    POLineData,
    PriorInvoice,
    VendorData,
    match_vendor,
    normalize_number,
    run_checks,
)

ACME = VendorData("v1", "Acme Industrial Supply", "12-3456789", "000123456789", "021000021")
OTHER = VendorData("v2", "Northwind Logistics", "98-7654321", "555000111", "026009593")


def po(**kw):
    base = dict(
        number="PO-1001",
        vendor_id="v1",
        currency="USD",
        status="open",
        lines=[
            POLineData("BOLT-M8", "M8 hex bolts, box of 100", D(10), D("45.00")),
            POLineData("GLOVE-L", "Nitrile gloves, large", D(20), D("12.50")),
        ],
        received={"BOLT-M8": D(10), "GLOVE-L": D(20)},
    )
    base.update(kw)
    return POData(**base)


def inv(**kw):
    base = dict(
        id="i1",
        number="INV-2041",
        vendor_name="Acme Industrial Supply",
        vendor_tax_id="12-3456789",
        po_number="PO-1001",
        invoice_date=date(2026, 10, 1),
        due_date=date(2026, 10, 31),
        currency="USD",
        subtotal=D("700.00"),
        tax=D("56.00"),
        total=D("756.00"),
        remit_account="000123456789",
        remit_routing="021000021",
        file_sha256="aaa",
        lines=[
            LineData("M8 hex bolts, box of 100", D(10), D("45.00"), D("450.00"), "BOLT-M8"),
            LineData("Nitrile gloves, large", D(20), D("12.50"), D("250.00"), "GLOVE-L"),
        ],
    )
    base.update(kw)
    return InvoiceData(**base)


def ctx(prior=None, pos=None):
    return CheckContext(vendors=[ACME, OTHER], pos=pos or {"PO-1001": po()}, prior=prior or [])


def codes(result):
    return sorted(f.code for f in result.findings)


def test_clean_invoice_has_no_findings():
    r = run_checks(inv(), ctx())
    assert r.findings == []
    assert r.vendor.id == "v1"
    assert len(r.line_matches) == 2


def test_bank_mismatch_blocks_full_amount():
    r = run_checks(inv(remit_account="9999-8888-7777"), ctx())
    assert codes(r) == ["BANK_MISMATCH"]
    assert r.findings[0].amount_at_risk == D("756.00")
    assert "7777" in r.findings[0].detail


def test_account_formatting_differences_are_not_a_mismatch():
    r = run_checks(inv(remit_account="0001 2345 6789"), ctx())
    assert r.findings == []


def test_exact_duplicate_number_with_formatting_noise():
    prior = PriorInvoice("i0", "inv 002041", "v1", D("756.00"), date(2026, 9, 1), "bbb", "PO-1001")
    r = run_checks(inv(po_number="PO-1001"), ctx(prior=[prior]))
    assert "DUPLICATE_NUMBER" in codes(r)


def test_suspect_duplicate_same_total_altered_number():
    prior = PriorInvoice("i0", "INV-2041", "v1", D("756.00"), date(2026, 10, 1), "bbb", None)
    r = run_checks(inv(number="INV-2041-A"), ctx(prior=[prior]))
    assert "DUPLICATE_SUSPECT" in codes(r)


def test_duplicate_file_hash():
    prior = PriorInvoice("i0", "X-1", "v2", D("1"), None, "aaa", None)
    r = run_checks(inv(), ctx(prior=[prior]))
    assert "DUPLICATE_FILE" in codes(r)


def test_other_vendor_same_number_is_not_duplicate():
    prior = PriorInvoice("i0", "INV-2041", "v2", D("756.00"), date(2026, 10, 1), "bbb", None)
    r = run_checks(inv(), ctx(prior=[prior]))
    assert r.findings == []


def test_price_variance_beyond_tolerance_quantifies_overcharge():
    lines = [
        LineData("M8 hex bolts, box of 100", D(10), D("49.50"), D("495.00"), "BOLT-M8"),
        LineData("Nitrile gloves, large", D(20), D("12.50"), D("250.00"), "GLOVE-L"),
    ]
    r = run_checks(inv(lines=lines, subtotal=D("745.00"), tax=D("59.60"), total=D("804.60")), ctx())
    assert codes(r) == ["PRICE_VARIANCE"]
    assert r.findings[0].amount_at_risk == D("45.00")


def test_price_within_tolerance_passes():
    lines = [
        LineData("M8 hex bolts, box of 100", D(10), D("45.80"), D("458.00"), "BOLT-M8"),
        LineData("Nitrile gloves, large", D(20), D("12.50"), D("250.00"), "GLOVE-L"),
    ]
    r = run_checks(inv(lines=lines, subtotal=D("708.00"), tax=D("56.64"), total=D("764.64")), ctx())
    assert r.findings == []


def test_billing_for_unreceived_goods():
    p = po(received={"BOLT-M8": D(6), "GLOVE-L": D(20)})
    r = run_checks(inv(), ctx(pos={"PO-1001": p}))
    assert codes(r) == ["QTY_NOT_RECEIVED"]
    assert r.findings[0].amount_at_risk == D("180.00")


def test_cumulative_billing_across_invoices_over_order():
    prior = PriorInvoice("i0", "INV-2000", "v1", D("225"), date(2026, 9, 1), "ccc", "PO-1001", {"BOLT-M8": D(5)})
    r = run_checks(inv(), ctx(prior=[prior]))
    assert "QTY_OVER_ORDERED" in codes(r)


def test_line_and_total_math():
    lines = [
        LineData("M8 hex bolts, box of 100", D(10), D("45.00"), D("460.00"), "BOLT-M8"),
        LineData("Nitrile gloves, large", D(20), D("12.50"), D("250.00"), "GLOVE-L"),
    ]
    r = run_checks(inv(lines=lines, subtotal=D("710.00"), total=D("800.00")), ctx())
    assert {"LINE_MATH", "TOTAL_MATH"} <= set(codes(r))


def test_unordered_item_matched_by_description_fallback():
    lines = [
        LineData("M8 hex bolts box 100", D(10), D("45.00"), D("450.00")),
        LineData("Expedited shipping surcharge", D(1), D("250.00"), D("250.00")),
    ]
    r = run_checks(inv(lines=lines), ctx())
    assert codes(r) == ["UNORDERED_ITEM"]
    assert r.findings[0].amount_at_risk == D("250.00")


def test_unknown_vendor_and_missing_po():
    r = run_checks(inv(vendor_name="Totally Legit Consulting LLC", vendor_tax_id=None, po_number=None), ctx())
    assert {"UNKNOWN_VENDOR", "NO_PO"} <= set(codes(r))


def test_po_for_another_vendor():
    r = run_checks(inv(), ctx(pos={"PO-1001": po(vendor_id="v2")}))
    assert "PO_VENDOR_MISMATCH" in codes(r)


def test_prompt_injection_signal_blocks():
    r = run_checks(inv(injection_signals=[{"kind": "hidden text", "excerpt": "ignore previous instructions"}]), ctx())
    assert codes(r) == ["PROMPT_INJECTION"]


def test_shortened_terms_is_informational():
    r = run_checks(inv(due_date=date(2026, 10, 5)), ctx())
    assert codes(r) == ["TERMS_SHORTENED"]
    assert r.blocking == []


@pytest.mark.parametrize(
    "a,b",
    [("INV-0042", "42"), ("Invoice #42", "inv42"), ("no. 00042", "42")],
)
def test_normalize_number(a, b):
    assert normalize_number(a) == normalize_number(b)


def test_vendor_fuzzy_name_match_without_tax_id():
    v, score = match_vendor(inv(vendor_name="ACME Industrial Supply, Inc.", vendor_tax_id=None), [ACME, OTHER])
    assert v is ACME and score >= 88
