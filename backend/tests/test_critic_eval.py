from sqlalchemy import select

from tollgate.db import session_scope
from tollgate.models import CriticReview


def _model(monkeypatch, verdict):
    from tollgate import llm

    monkeypatch.setattr(llm, "chat_json", lambda model, messages, **kw: {"verdict": verdict, "independent_amount": None, "summary": "", "points": []})


def _by_case(rows):
    return {r["case"]: r for r in rows}


def test_the_floor_catches_every_planted_error_a_model_waves_through(db, monkeypatch):
    from tollgate.evals import critic_cases

    _model(monkeypatch, "agree")
    rows = _by_case(critic_cases(2))
    planted = [r for k, r in rows.items() if k.startswith("planted")]
    assert len(planted) == 4
    for r in planted:
        assert r["model_passed"] == 0 and r["model_verdicts"] == {"agree": 2}
        assert r["passed"] == 2 and r["verdicts"] == {"disagree": 2}, r["case"]
    for k in ("correct: SLA credit", "correct: volume price", "correct: price cap with tax"):
        assert rows[k]["passed"] == rows[k]["model_passed"] == 2, k


def test_the_floor_does_not_overturn_a_model_that_doubts_a_correct_proposal(db, monkeypatch):
    from tollgate.evals import critic_cases

    _model(monkeypatch, "concerns")
    rows = _by_case(critic_cases(1))
    assert rows["correct: volume price"]["passed"] == 0 and rows["correct: volume price"]["verdicts"] == {"concerns": 1}
    assert all(r["passed"] == 1 for k, r in rows.items() if k.startswith("planted"))


def test_eval_runs_leave_no_reviews_behind(db, monkeypatch):
    from tollgate.evals import critic_cases

    _model(monkeypatch, "agree")
    critic_cases(1)
    with session_scope() as s:
        assert s.execute(select(CriticReview)).first() is None
