"""Tollgate's own model: a per-vendor fingerprint of how its invoices are made."""

from dataclasses import replace

import pytest
from sqlalchemy import select

from tollgate import agent, fingerprint, pipeline
from tollgate.db import session_scope
from tollgate.invoicegen import render
from tollgate.lab import build
from tollgate.models import Invoice, VendorFingerprint
from tollgate.seed import demo_inbox
from tollgate.worker import drain


@pytest.mark.parametrize("slug", ["brightline", "ostara", "granite"])
def test_held_out_genuine_pass_and_every_forgery_kind_is_caught(slug):
    _, m = fingerprint.train_vendor(slug)
    assert m["trained_on"] == 40 and m["holdout_genuine"] == 10
    assert m["false_alarms"] == 0
    assert set(m["forgeries"]) == {"rebuilt in a word processor", "careful rebuild, fonts and metadata copied", "another company's template", "genuine invoice edited"}
    assert m["caught"] == m["forged_total"] == 16


def test_careful_forger_is_caught_on_layout_alone():
    model = fingerprint.fit(list(fingerprint.history_features("granite")))
    fingerprint.forgeries("granite", 1)  # registers the careful forger's style
    sp = fingerprint.history_specs("granite", 1, seed=5)[0]
    v = fingerprint.score(model, fingerprint.features(render(replace(sp, style="careful-granite"))), "Granite")
    assert v.anomalous
    assert not any("producer" in r.lower() or "fonts" in r.lower() for r in v.reasons)  # metadata and fonts were copied
    assert any("position" in r for r in v.reasons)


def test_edited_invoice_reasons_are_plain():
    model = fingerprint.fit(list(fingerprint.history_features("lumen")))
    sp = fingerprint.history_specs("lumen", 1, seed=3)[0]
    v = fingerprint.score(model, fingerprint.features(fingerprint.edit_bank(render(sp), "1111 2222 3333")), "Lumen")
    assert v.anomalous
    assert any("Adobe Acrobat" in r for r in v.reasons)
    assert any("text drawn after the footer" in r.lower() for r in v.reasons)


def test_unreadable_pdf_is_a_feature_not_a_crash():
    model = fingerprint.fit(list(fingerprint.history_features("polaris")))
    f = fingerprint.features(b"not a pdf")
    assert f["producer"] == "unreadable"
    assert fingerprint.score(model, f).anomalous


def test_reset_trains_one_model_per_vendor(db):
    with session_scope() as s:
        fps = list(s.execute(select(VendorFingerprint)).scalars())
        assert len(fps) == 7
        assert all(fp.metrics["false_alarms"] == 0 for fp in fps)


def test_genuine_inbox_passes_and_the_forged_invoice_is_flagged(db):
    ids = {}
    with session_scope() as s:
        for d in demo_inbox():
            ids[d.spec.number] = pipeline.ingest(s, d.pdf(), d.file_name).id
    drain()
    with session_scope() as s:
        for number, iid in ids.items():
            inv = s.get(Invoice, iid)
            fp = (inv.extraction or {}).get("fingerprint")
            if number == "ASA-0091":
                assert fp is None  # unknown vendor: no model to compare with
                continue
            flagged = any(f.code == "DOC_FINGERPRINT" for f in inv.findings)
            assert flagged == (number == "BIS-2090"), number
        bis = s.get(Invoice, ids["BIS-2090"])
        f = next(f for f in bis.findings if f.code == "DOC_FINGERPRINT")
        assert "Microsoft" in f.detail and "Sage Intacct" in f.detail


def test_lab_edit_inside_the_price_tolerance_is_held(db):
    with session_scope() as s:
        iid = [pipeline.ingest(s, pdf, name, source="lab").id for name, pdf, _ in build("pdf_edit")][0]
    drain()
    with session_scope() as s:
        inv = s.get(Invoice, iid)
        assert inv.status.value not in ("scheduled", "paid")
        assert "DOC_FINGERPRINT" in {f.code for f in inv.findings}


def test_fingerprint_only_invoice_asks_the_vendor_and_goes_to_a_person(db):
    sp = fingerprint.history_specs("polaris", 1, seed=11)[0]
    sp = replace(sp, style="forger", number="PNS-99001", po_number="PO-24108")
    with session_scope() as s:
        iid = pipeline.ingest(s, render(sp), "pns.pdf").id
    drain()
    with session_scope() as s:
        inv = s.get(Invoice, iid)
        codes = {f.code for f in agent.open_blocking(inv)}
        assert codes == {"DOC_FINGERPRINT"}
        assert inv.status.value == "on_hold" and inv.agent_state["waiting_for"] == "person"
        assert inv.agent_state["recommendation"].startswith("Call Polaris")
