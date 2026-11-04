"""Evaluation suite, run against the real Vultr models.

  uv run python -m tollgate.evals --runs 3

Four suites, each case run on a fresh database:
  attacks    every attack-lab template must be stopped before payment
  inbox      every demo invoice must reach its expected outcome
  contracts  model-extracted contract terms must equal the reviewed terms
  critic     the critic must disagree with planted errors and agree with correct proposals
Writes tollgate/eval_results.json, which the attack lab page shows.
"""

from __future__ import annotations

import argparse
import json
import logging
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent / "eval_results.json"

INBOX_EXPECT = {
    "lumen-LOS-3391.pdf": {"scheduled"},
    "brightline-BIS-2041.pdf": {"scheduled"},
    "polaris-PNS-55120.pdf": {"scheduled"},
    "ostara-OC-7720.pdf": {"awaiting_approval"},
    "kestrel-KFL-88812-R.pdf": {"rejected", "awaiting_vendor", "on_hold"},
    "brightline-BIS-2077.pdf": {"awaiting_vendor"},
    "granite-GE-5561.pdf": {"on_hold", "awaiting_vendor"},
    "vantage-VCS-10488.pdf": {"on_hold"},
    "brightline-BIS-2090.pdf": {"on_hold"},
    "apex-ASA-0091.pdf": {"rejected", "on_hold"},
}
RECOVERY_EXPECT = {"polaris-PNS-55120.pdf": "975.00", "ostara-OC-7720.pdf": "1416.00", "granite-GE-5561.pdf": "43.20"}


def fresh_db():
    from . import db

    tmp = tempfile.mkdtemp(prefix="tollgate-eval-")
    db.configure(f"sqlite:///{tmp}/eval.db")
    db.Base.metadata.drop_all(db.engine)
    db.init_db()
    from .seed import reset_and_seed

    with db.session_scope() as s:
        reset_and_seed(s)


def suite_attacks(runs: int) -> list[dict]:
    from sqlalchemy import select

    from . import pipeline
    from .db import session_scope
    from .lab import TEMPLATES, build, outcome
    from .models import Invoice, Severity
    from .worker import drain

    results = []
    for t in TEMPLATES:
        passes, fired = 0, {}
        for r in range(runs):
            fresh_db()
            with session_scope() as s:
                ids = [pipeline.ingest(s, pdf, name, source="lab", source_ref=f"{t.key}-{r}").id for name, pdf, _ in build(t.key, None, r + 1)]
            drain()
            with session_scope() as s:
                invs = [s.get(Invoice, i) for i in ids]
                outs = [outcome(i.status.value, sum(1 for f in i.findings if f.severity == Severity.block and not f.resolved)) for i in invs]
                for i in invs:
                    for f in i.findings:
                        if f.severity == Severity.block:
                            fired[f.code] = fired.get(f.code, 0) + 1
            if "caught" in outs and "pending" not in outs:
                passes += 1
        results.append({"case": t.key, "name": t.name, "technique": t.technique, "runs": runs, "passed": passes, "controls_fired": fired})
        print(f"  attack {t.key:22} {passes}/{runs}  {sorted(fired)}")
    return results


def suite_inbox(runs: int) -> list[dict]:
    from sqlalchemy import select

    from . import pipeline
    from .db import session_scope
    from .models import Invoice, Severity
    from .seed import demo_inbox
    from .worker import drain

    tally = {k: 0 for k in INBOX_EXPECT}
    for _ in range(runs):
        fresh_db()
        with session_scope() as s:
            ids = {d.file_name: pipeline.ingest(s, d.pdf(), d.file_name).id for d in demo_inbox()}
        drain()
        with session_scope() as s:
            for name, iid in ids.items():
                inv = s.get(Invoice, iid)
                ok = inv.status.value in INBOX_EXPECT[name]
                if name in RECOVERY_EXPECT:
                    rec = sum((f.amount_at_risk for f in inv.findings if f.severity == Severity.recover), 0)
                    ok = ok and f"{rec:.2f}" == RECOVERY_EXPECT[name]
                tally[name] += int(ok)
    out = [{"case": k, "runs": runs, "passed": v} for k, v in tally.items()]
    for o in out:
        print(f"  inbox  {o['case']:28} {o['passed']}/{runs}")
    return out


def suite_contracts(runs: int) -> list[dict]:
    from .contracts import extract_terms
    from .seed_contracts import CONTRACTS

    out = []
    for slug, c in CONTRACTS.items():
        from .contracts import validate_params

        want = sorted((t["kind"], json.dumps(_round(validate_params(t["kind"], t["params"])), sort_keys=True)) for t in c["terms"])
        passes = 0
        for _ in range(runs):
            fresh_db()
            got, _rej = extract_terms(c["text"])
            have = sorted((t["kind"], json.dumps(_round(t["params"]), sort_keys=True)) for t in got)
            passes += int(have == want)
        out.append({"case": slug, "runs": runs, "passed": passes, "terms": len(c["terms"])})
        print(f"  terms  {slug:12} {passes}/{runs}")
    return out


def _round(p):
    from .contracts import validate_params

    if isinstance(p, dict) and "kind" in p:
        return p
    if isinstance(p, dict):
        return {k: _round(v) for k, v in p.items() if not (k == "metric")}
    if isinstance(p, list):
        return [_round(x) for x in p]
    if isinstance(p, (int, float)) and not isinstance(p, bool):
        return round(float(p), 4)
    return p


def suite_critic(runs: int) -> list[dict]:
    from decimal import Decimal

    from sqlalchemy import select

    from . import critic, pipeline
    from .config import get_settings
    from .db import session_scope
    from .llm import chat_json
    from .models import Invoice
    from .seed import demo_inbox

    def wrong_tier(p):
        p["deductions"][0]["amount"] = "650.00"
        p["deductions"][0]["detail"] = p["deductions"][0]["detail"].replace("15%", "10%").replace("975.00", "650.00")
        p["pay"] = "5850.00"

    def missed(p):
        p["deductions"], p["pay"] = [], "33360.00"

    def overclaim(p):
        p["deductions"][0]["amount"], p["pay"] = "2160.00", "31200.00"

    cases = [
        ("planted: wrong SLA tier", "PNS-55120", wrong_tier, {"disagree", "concerns"}),
        ("planted: volume price missed", "OC-7720", missed, {"disagree", "concerns"}),
        ("planted: deduction over-claimed", "OC-7720", overclaim, {"disagree", "concerns"}),
        ("correct: SLA credit", "PNS-55120", lambda p: None, {"agree"}),
        ("correct: volume price", "OC-7720", lambda p: None, {"agree"}),
        ("correct: price cap with tax", "GE-5561", lambda p: None, {"agree"}),
    ]
    fresh_db()
    with session_scope() as s:
        for d in demo_inbox():
            if d.spec.number in {c[1] for c in cases}:
                inv = pipeline.ingest(s, d.pdf(), d.file_name)
                pipeline.read_document(s, inv)
                if d.spec.number == "GE-5561":  # the critic reviews only once nothing blocks: goods have arrived
                    from .api_actions import record_receipt

                    record_receipt(s, inv.id, user="Receiving dock")
                pipeline.run_controls(s, inv)
        contexts = {}
        for name, number, mutate, _ in cases:
            inv = s.execute(select(Invoice).where(Invoice.number == number)).scalar_one()
            p = critic.proposal_for(inv)
            mutate(p)
            contexts[name] = critic._context(s, inv, p)
    out = []
    for name, _n, _m, want in cases:
        passes = 0
        for _ in range(runs):
            d = chat_json(get_settings().model_critic, [{"role": "system", "content": critic.SYSTEM}, {"role": "user", "content": contexts[name]}],
                          max_tokens=10000, temperature=0)
            passes += int(str(d.get("verdict")).lower() in want)
        out.append({"case": name, "runs": runs, "passed": passes})
        print(f"  critic {name:34} {passes}/{runs}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--suites", default="attacks,inbox,contracts,critic")
    a = ap.parse_args()
    logging.basicConfig(level=logging.WARNING)
    from .config import get_settings
    from .llm import spent_usd

    cfg = get_settings()
    if not cfg.inference_api_key:
        raise SystemExit("evals run against the real models: set TOLLGATE_INFERENCE_API_KEY")
    t0 = time.time()
    fresh_db()
    start_spend = spent_usd()
    suites = {}
    for name in a.suites.split(","):
        print(f"== {name}")
        suites[name] = {"attacks": suite_attacks, "inbox": suite_inbox, "contracts": suite_contracts, "critic": suite_critic}[name](a.runs)
    total = sum(c["runs"] for v in suites.values() for c in v)
    passed = sum(c["passed"] for v in suites.values() for c in v)
    result = {
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "runs_per_case": a.runs,
        "models": {"vision": cfg.model_vision, "reasoning": cfg.model_reasoning, "critic": cfg.model_critic, "safety": cfg.model_safety},
        "passed": passed,
        "total": total,
        "seconds": round(time.time() - t0, 1),
        "suites": suites,
    }
    if OUT.exists() and a.suites != "attacks,inbox,contracts,critic":
        prev = json.loads(OUT.read_text())
        prev["suites"].update(suites)
        prev["ran_at"] = result["ran_at"]
        prev["passed"] = sum(c["passed"] for v in prev["suites"].values() for c in v)
        prev["total"] = sum(c["runs"] for v in prev["suites"].values() for c in v)
        result = prev
    OUT.write_text(json.dumps(result, indent=1))
    print(f"wrote {OUT}: {result['passed']}/{result['total']}")
    print(f"{passed}/{total} passed in {result['seconds']}s")


if __name__ == "__main__":
    main()
