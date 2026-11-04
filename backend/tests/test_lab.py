import pytest
from fastapi.testclient import TestClient

from tollgate.api import app
from tollgate.lab import TEMPLATES
from tollgate.worker import drain


@pytest.mark.parametrize("key", [t.key for t in TEMPLATES])
def test_every_attack_is_caught_offline(db, key):
    c = TestClient(app)
    r = c.post("/api/lab/attack", json={"template": key})
    assert r.status_code == 200, r.text
    drain()
    attempts = c.get("/api/lab/attempts").json()
    a = next(x for x in attempts if x["group"] == r.json()["group"])
    assert a["outcome"] == "caught", a


def test_lab_is_isolated_from_the_real_queue(db):
    c = TestClient(app)
    c.post("/api/lab/attack", json={"template": "bank_change"})
    drain()
    assert c.get("/api/invoices").json() == []
    assert c.get("/api/stats").json()["invoices"] == 0
