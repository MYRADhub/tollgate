from datetime import date
from decimal import Decimal as D

import pytest

from tollgate.contracts import LineIn, TermData, TermError, apply_terms, early_pay, quote_in_text, validate_params

SLA = TermData(1, "sla_credit", validate_params("sla_credit", {"commitment_pct": 99.95, "skus": ["NET"], "tiers": [
    {"below_pct": 99.95, "credit_pct": 10}, {"below_pct": 99.5, "credit_pct": 15}, {"below_pct": 99.0, "credit_pct": 25}]}), "q", "WAN")
LINE = [LineIn(1, "NET", "circuit", D(1), D("6500"), D("6500"))]


@pytest.mark.parametrize("measured,expected", [("99.99", None), ("99.90", "650.00"), ("99.31", "975.00"), ("98.10", "1625.00")])
def test_sla_tiers_pick_the_worst_band_crossed(measured, expected):
    r = apply_terms(LINE, date(2026, 11, 1), [SLA], {("2026-10", "uptime_pct"): D(measured)}, D(0))
    assert (str(r[0].amount) if r else None) == expected


def test_sla_uses_previous_month_and_ignores_other_skus():
    other = [LineIn(1, "OTHER", "x", D(1), D("100"), D("100"))]
    assert apply_terms(LINE, date(2026, 11, 1), [SLA], {("2026-11", "uptime_pct"): D("90")}, D(0)) == []
    assert apply_terms(other, date(2026, 11, 1), [SLA], {("2026-10", "uptime_pct"): D("90")}, D(0)) == []


def test_volume_price_needs_minimum_quantity_and_grosses_up_tax():
    t = TermData(2, "volume_price", validate_params("volume_price", {"sku": "M", "min_qty": 20, "unit_price": 1121}), "q", "Supply")
    small = [LineIn(1, "M", "m", D(19), D("1180"), D("22420"))]
    big = [LineIn(1, "M", "m", D(24), D("1180"), D("28320"))]
    assert apply_terms(small, None, [t], {}, D(0)) == []
    assert apply_terms(big, None, [t], {}, D("0.08"))[0].amount == D("1529.28")


def test_price_cap_allows_increase_within_cap():
    t = TermData(3, "price_cap", validate_params("price_cap", {"base_prices": {"B": 44}, "max_increase_pct": 3}), "q", "MSA")
    ok = [LineIn(1, "B", "b", D(40), D("45.00"), D("1800"))]
    over = [LineIn(1, "B", "b", D(40), D("46.00"), D("1840"))]
    assert apply_terms(ok, None, [t], {}, D(0)) == []
    assert apply_terms(over, None, [t], {}, D(0))[0].amount == D("27.20")  # (46.00 - 45.32) x 40


def test_early_pay_window():
    t = TermData(4, "early_pay_discount", validate_params("early_pay_discount", {"discount_pct": 2, "within_days": 10}), "q", "T")
    assert early_pay([t], date(2026, 11, 1)) == (D("2.0"), date(2026, 11, 11))


def test_validation_rejects_bad_terms():
    with pytest.raises(TermError):
        validate_params("refund_everything", {})
    with pytest.raises(TermError):
        validate_params("sla_credit", {"commitment_pct": 99.9, "tiers": []})
    with pytest.raises(TermError):
        validate_params("early_pay_discount", {"discount_pct": 90, "within_days": 10})


def test_quote_must_be_verbatim_modulo_whitespace_and_quotes():
    text = "4.2 Service Credits. If Monthly Availability falls below 99.95%, Provider shall credit Customer 10%."
    assert quote_in_text("If Monthly  Availability falls below\n99.95%, Provider shall credit Customer 10%.", text)
    assert not quote_in_text("If Monthly Availability falls below 99.95%, Provider shall credit Customer 50%.", text)
    assert not quote_in_text("10%", text)  # too short to count as a citation
