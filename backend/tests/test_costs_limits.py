from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import select

from tollgate import api as api_mod
from tollgate import llm
from tollgate.api import RateLimiter, app
from tollgate.db import session_scope
from tollgate.models import InferenceSpend, InvoiceCost
from tollgate.worker import drain


def usage(p, c):
    return SimpleNamespace(prompt_tokens=p, completion_tokens=c)


def test_limiter_weights_units_and_expires():
    lim = RateLimiter()
    assert lim.take([("a", 10)], 10, now=0)
    assert not lim.take([("a", 10)], 1, now=1)
    assert lim.take([("b", 10)], 1, now=1)  # keys are independent
    assert lim.take([("a", 10)], 1, now=3601)  # the first hit has left the window


def test_limiter_refusal_consumes_nothing():
    lim = RateLimiter()
    assert lim.take([("ip", 5), ("global", 100)], 4, now=0)
    assert not lim.take([("ip", 5), ("global", 100)], 3, now=1)
    assert lim.used("global", 1) == 4


def test_per_ip_limit_counts_documents(db, monkeypatch):
    monkeypatch.setattr(api_mod.settings, "intake_per_ip_per_hour", 12)
    c = TestClient(app)
    one = {"X-Forwarded-For": "203.0.113.5"}
    assert c.post("/api/demo/inbox", json=list(range(10)), headers=one).status_code == 200
    r = c.post("/api/demo/inbox", json=[0, 1, 2], headers=one)
    assert r.status_code == 429 and "per hour" in r.json()["detail"]
    assert c.post("/api/demo/inbox", json=[0], headers={"X-Forwarded-For": "198.51.100.7"}).status_code == 200


def test_resets_are_limited_per_visitor(db, monkeypatch):
    monkeypatch.setattr(api_mod.settings, "resets_per_ip_per_hour", 2)
    c = TestClient(app)
    h = {"X-Forwarded-For": "203.0.113.9"}
    assert [c.post("/api/demo/reset", headers=h).status_code for _ in range(3)] == [200, 200, 429]


def test_uploads_pause_near_the_budget_but_the_guided_demo_does_not(db, monkeypatch):
    monkeypatch.setattr(api_mod.settings, "inference_api_key", "set")
    monkeypatch.setattr(llm, "spent_usd", lambda: 22.5)
    c = TestClient(app)
    pdf = c.get("/api/demo/inbox/0/file").content
    r = c.post("/api/invoices", files={"file": ("a.pdf", pdf, "application/pdf")})
    assert r.status_code == 503
    assert c.post("/api/lab/attack", json={"template": "lookalike_vendor"}).status_code == 503
    assert c.post("/api/demo/inbox", json=[0]).status_code == 200


def test_model_usage_is_charged_to_the_invoice(db):
    c = TestClient(app)
    ids = c.post("/api/demo/inbox", json=[0, 2]).json()["ids"]
    drain()
    with llm.attribute(ids[0]):
        llm._record("qwen3.8-27b", usage(1000, 500))
        llm._record("glm-5.3-flash", usage(2000, 0))
    llm._record("qwen3.8-27b", usage(100, 0))  # outside any invoice: counts toward the cap only
    llm.flush_spend()
    with session_scope() as s:
        row = s.get(InvoiceCost, ids[0])
        assert row.calls == 2 and row.prompt_tokens == 3000
        assert abs(float(row.usd) - (1500 * 0.000001 + 2000 * 0.00000035)) < 1e-9
        assert s.get(InvoiceCost, ids[1]) is None
        assert s.execute(select(InferenceSpend).where(InferenceSpend.model == "qwen3.8-27b")).scalar_one().calls == 2
    d = c.get(f"/api/invoices/{ids[0]}").json()
    assert d["cost"]["calls"] == 2
    st = c.get("/api/stats").json()["cost"]
    assert st["invoices"] == 1 and abs(st["per_invoice_usd"] - 0.0022) < 1e-9
    assert st["benchmark_usd"] == 2.78
    assert c.get(f"/api/invoices/{ids[1]}").json()["cost"] is None


def test_attribution_is_scoped_to_the_block():
    with llm.attribute("abc"):
        assert llm._invoice.get() == "abc"
    assert llm._invoice.get() is None


def test_reset_cooldown_protects_a_visitor_mid_demo(db, monkeypatch):
    from fastapi.testclient import TestClient

    from tollgate.api import app
    from tollgate.config import get_settings

    c = TestClient(app)
    monkeypatch.setattr(get_settings(), "reset_cooldown_s", 600)
    r = c.post("/api/demo/reset")
    assert r.status_code == 429 and "already fresh" in r.json()["detail"]
    monkeypatch.setattr(get_settings(), "reset_cooldown_s", 0)
    assert c.post("/api/demo/reset").status_code == 200
