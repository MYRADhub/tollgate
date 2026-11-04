from fastapi.testclient import TestClient

from tollgate.api import app
from tollgate.worker import drain


def test_api_flow(db):
    c = TestClient(app)
    assert c.get("/api/health").json()["ok"]
    r = c.post("/api/demo/inbox", json=[0, 5])
    assert r.status_code == 200
    drain()
    rows = c.get("/api/invoices").json()
    assert {r["status"] for r in rows} == {"scheduled", "awaiting_vendor"}
    held = next(r for r in rows if r["status"] == "awaiting_vendor")
    d = c.get(f"/api/invoices/{held['id']}").json()
    assert d["findings"][0]["code"] == "PRICE_VARIANCE"
    assert d["emails"] and d["po"]["number"] == "PO-24107"
    assert c.get(f"/api/invoices/{held['id']}/file").content.startswith(b"%PDF")

    assert c.post(f"/api/demo/vendor-reply/{held['id']}").status_code == 200
    drain()
    rows = c.get("/api/invoices").json()
    assert sorted(r["status"] for r in rows) == ["scheduled", "scheduled", "superseded"]
    st = c.get("/api/stats").json()
    assert st["prevented"] >= 110  # 200 x 0.55 overbilling corrected
    assert c.get("/api/audit/verify").json()["ok"]


def test_upload_rejects_non_pdf(db):
    c = TestClient(app)
    r = c.post("/api/invoices", files={"file": ("x.pdf", b"hello", "application/pdf")})
    assert r.status_code == 400


def test_approval_errors_are_400(db):
    c = TestClient(app)
    c.post("/api/demo/inbox", json=[3])
    drain()
    appr = c.get("/api/approvals").json()[0]
    r = c.post(f"/api/approvals/{appr['id']}/decide", json={"user": "Sam", "role": "clerk", "decision": "approved"})
    assert r.status_code == 400


def test_contracts_listing_and_term_review_permissions(db):
    c = TestClient(app)
    rows = c.get("/api/contracts").json()
    polaris = next(r for r in rows if r["vendor"] == "Polaris Network Services")
    assert polaris["terms"][0]["kind"] == "sla_credit" and polaris["terms"][0]["status"] == "approved"
    assert polaris["metrics"][-1]["value"] == 99.31
    tid = polaris["terms"][0]["id"]
    r = c.post(f"/api/terms/{tid}/decide", json={"user": "Sam", "role": "clerk", "decision": "rejected"})
    assert r.status_code == 400
    assert c.post("/api/contracts/1/extract", json={"user": "Rosa", "role": "controller"}).status_code == 503  # no inference in tests


def test_stats_report_recovered(db):
    c = TestClient(app)
    c.post("/api/demo/inbox", json=[2])  # Polaris
    drain()
    assert c.get("/api/stats").json()["recovered"] == 975.0
