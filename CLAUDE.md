# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Tollgate is an accounts-payable agent: a FastAPI backend and separate job worker (`backend/tollgate`), and a Next.js frontend (`frontend`). `README.md` covers the product, the demo script and the eval results.

## Commands

Requires Python 3.12 with uv, and Node 22.

Run locally (each from its own directory, API and worker as separate processes):

```bash
# backend/
uv sync
uv run uvicorn tollgate.api:app --port 8000
uv run python -m tollgate.worker

# frontend/
npm install
npm run dev -- --port 3100    # proxies /api to BACKEND_URL (default http://127.0.0.1:8000)
```

Run the worker too: without it, queued jobs (invoice processing, agent decisions) never execute.

Tests:

```bash
npm test                                      # repo root: pytest, then tsc --noEmit, then eslint
npm run test:e2e                              # repo root: Playwright; boots its own API, worker and web app

# backend/
uv run pytest tests/test_checks.py -q         # one file
uv run pytest tests/test_checks.py -k name    # by name

# frontend/
npx playwright test -g "test title"           # one browser test
npx playwright test --project=mobile          # tests tagged @mobile only
E2E_BASE_URL=https://host npx playwright test # against a running deployment
npm run lint
```

Evals call the real models, cost money, need `TOLLGATE_INFERENCE_API_KEY`, and overwrite `backend/tollgate/eval_results.json`, which the attack lab page displays:

```bash
# backend/
uv run python -m tollgate.evals --runs 3
uv run python -m tollgate.evals --runs 1 --suites critic   # attacks,inbox,contracts,critic,inquiries,statements,fingerprint
```

Deploy to the existing server: `HOST=root@<ip> ./deploy/update.sh` (pulls `main` on the server and rebuilds with Docker Compose).

## Architecture

### The model reads and writes, code decides

This is the central invariant. Models extract fields, plan and draft text; deterministic code determines every amount and whether every action is allowed. Keep new features on this side of the line.

- `pipeline.py` runs an invoice: read and ground it, screen for injection (`injection.py`), fingerprint it (`fingerprint.py`), then run controls (`checks.py`, pure functions) and apply approved contract terms (`contracts.py`).
- `agent.py` `decide()` plans the actions: clean invoices take a fixed path, exceptions go through the `resolver.py` investigation loop and then the planner. `critic_gate()` sends payments with deductions or above the auto-pay limit to a different model (`critic.py`), whose verdict code can override by recomputing the payment.
- `agent.py` `_execute()` is the policy guard. Every action passes through it, and a refusal raises `Denied`, which is logged and triggers a re-plan. A new action type needs its guard conditions here.
- Document content is untrusted input: it can contain instructions aimed at the model. Likewise, model output in vendor replies is checked against facts in `inquiry.py` before it is sent.

### Two processes share only the database

The API (`api.py`, with mutations in `api_actions.py`) and the worker (`worker.py`) communicate through Postgres alone.

- Work is queued with `pipeline.enqueue(s, kind, invoice_id, payload, delay_s)` and dispatched by `kind` in `worker._run_job`. A new job kind needs a branch there.
- SSE in the API polls the audit table, because the worker cannot reach the in-process bus in `events.py`. For the UI to update live after worker activity, write an audit event. The frontend's single `EventSource` in `lib/api.ts` bumps a tick on each one.
- State that both processes need, such as the demo clock, has to live in the database.

### Time comes from the demo clock

`clock.py` adds a database-stored offset to real time so the demo can fast-forward. Use `clock.now()`, `clock.today()` or `models.utcnow()` (which wraps it) for every timestamp and job due time, never `datetime.now()`. The exception is real elapsed-time logic such as `IdleReset`, which must ignore fast-forward. SQLite returns naive datetimes, so normalise with `clock.aware()` before comparing.

### The app must run without a model

`llm.py` wraps the OpenAI-compatible Vultr endpoint. With no API key, or once `inference_budget_usd` is spent, the agent uses the text-layer reader and the rule-based planner (`plan_rule_based`). Model-backed changes need a working no-key path, because pytest and Playwright run without a key (Playwright uses one only if `E2E_INFERENCE_API_KEY` is set). Spend is attributed per invoice via `llm.attribute()`.

### Configuration and persistence

- All settings are in `config.py`, read from `TOLLGATE_*` environment variables or `.env`. Defaults give a local setup: SQLite, filesystem storage, mail off.
- There are no migrations: `init_db()` runs `create_all`, which will not alter existing tables. A column change on an existing database needs a manual `ALTER` or a recreated database.
- Code must work on both SQLite (tests, local) and Postgres (production).
- `audit.py` is an append-only hash chain, so write entries through `audit.record` and never edit or delete rows outside a demo reset.
- `seed.py` `reset_and_seed` defines the demo company. Tests, e2e and the live demo all depend on its data, so changing it can move the expected amounts in tests, evals and the README.

### Testing

- `tests/conftest.py` sets the environment before importing `tollgate` (the engine is created at import), so those assignments must stay ahead of any `tollgate` import. The `db` fixture rebuilds and reseeds the database for each test.
- `worker.drain()` runs due jobs synchronously, so tests do not need a running worker.
- Playwright runs serially with one worker against shared state (`e2e/start-backend.sh`: fresh SQLite, no mail, relaxed rate limits, colleague replies after 3 seconds).

### Frontend

`frontend/AGENTS.md` applies: this Next.js version differs from what you may know, so read the relevant guide in `frontend/node_modules/next/dist/docs/` before writing frontend code. `next dev` re-adds that file's block if it is removed.

Pages are in `src/app`, and API calls and shared types are in `src/lib/api.ts`. The acting user and role come from a picker stored in `localStorage` and are sent in request bodies. There is no real authentication: this is a shared demo with rate limits and a reset cooldown.

Attack-lab invoices run through the real pipeline but must never send email, join a payment run, count on the dashboard, or train the fingerprint models.
