# AIOps Simulation Platform

A human-governed AIOps platform (simulation/demo) that correlates **network
telemetry, application telemetry, facility alarms and IoT sensor streams** to
identify likely root causes of service degradation and recommend **safe recovery
playbooks**.

It ranks actions by **risk**, requires **human approval** for medium/high-risk
actions, keeps a full **audit trail**, and remains useful when some data sources
are missing or stale.

> This is a simulation only. It NEVER controls real infrastructure. All playbook
> executions are simulated and safe.

---

## Architecture

```
Vercel (static frontend)
   └── HTTPS /api/*  ──►  Railway (FastAPI + Uvicorn)
                              └── Railway PostgreSQL (DATABASE_URL)
                              └── Groq LLM (openai/gpt-oss-120b)   [optional]

Local development
   Browser ──► FastAPI serves frontend + /api ──► SQLite (backend/data/aiops.db)
```

- **Frontend**: vanilla HTML/CSS/JS, no build step. Polls the API with `fetch()`
  and updates the DOM in place (never reloads the page).
- **Backend**: FastAPI + Uvicorn, SQLAlchemy ORM.
- **Database**: SQLite locally (zero config), PostgreSQL in production via
  `DATABASE_URL`. Tables are created idempotently on startup.
- **AI**: official `groq` Python SDK, model `openai/gpt-oss-120b`. Structured
  JSON diagnosis validated against a **closed set** of root causes and playbooks.
  If Groq is unavailable/invalid the platform safely falls back to a
  deterministic rule-based diagnosis and reports that AI was unavailable.

### Telemetry vs. incident state (kept separate)

```
Telemetry:   NORMAL ──► DEGRADED ──► RECOVERING ──► NORMAL
Incident:    DETECTED ──► ANALYZED ──► AWAITING_APPROVAL ──► EXECUTED ──► RESOLVED
```

Old incidents never make the live dashboard look broken: current telemetry is
governed by the active scenario, while every incident/reading stays in history
and the audit trail.

### Risk governance (never bypassed by the AI)

| Risk  | Execution policy                                   | Example playbooks                      |
|-------|----------------------------------------------------|----------------------------------------|
| LOW   | AI may auto-execute (safe, reversible)             | `pb_hvac_recovery`, `pb_queue_scale_up` |
| MEDIUM| Human approval mandatory                           | `pb_network_failover`, `pb_app_rollback`, `pb_client_throttle` |
| HIGH  | Explicit human approval mandatory                  | `pb_power_switchover`                  |

The risk level is a property of the playbook, not a free-form AI choice.

---

## Project layout

```
project/
  backend/
    app/
      main.py            # FastAPI app, CORS, static frontends, startup init
      config.py          # env-driven config (.env, DATABASE_URL, Groq, CORS)
      routes/api.py      # REST endpoints
      services/          # telemetry, incidents, historical, audit
      ai/                # diagnosis (Groq), fallback, validation, prompts
      database/db.py     # engine + session (SQLite / PostgreSQL)
      models/            # SQLAlchemy entities + Pydantic schemas
      simulation/        # scenario definitions + telemetry generator
      playbooks.py       # closed root-cause/playbook/risk sets
    pyproject.toml       # uv dependency manifest
    .env.example
  frontend/
    config.js            # API base override for Vercel
    dashboard/           # index.html, style.css, app.js
    admin/               # index.html, style.css, app.js
  .gitignore
  README.md
```

---

## Local setup (uv)

Prerequisites: Python 3.11+, [uv](https://docs.astral.sh/uv/).

```bash
cd backend
uv sync
cp .env.example .env        # optional; everything works without it (fallback AI)
uv run uvicorn app.main:app --reload
```

Open:

- Dashboard: <http://localhost:8000/dashboard/>
- Admin / Operations: <http://localhost:8000/admin/>

Without `GROQ_API_KEY` the platform uses its rule-based fallback and reports it
in the diagnosis. Set `GROQ_API_KEY` in `backend/.env` to enable the LLM.

### .env.example

```env
# --- LLM (Groq) ---
GROQ_API_KEY=
GROQ_MODEL=openai/gpt-oss-120b
AI_TIMEOUT=45

# --- Database ---
# Local: leave empty -> SQLite at backend/data/aiops.db
DATABASE_URL=

# --- CORS / Frontend ---
# Comma-separated extra origins (e.g. your Vercel app). localhost always allowed.
CORS_ORIGINS=
```

---

## Core flow (demo)

1. Dashboard starts **NORMAL** with healthy readings.
2. Open **Admin / Operations**, click **Inject Scenario** (optionally tick
   "simulate missing/stale sources").
3. Bad telemetry appears **immediately**; an incident is created and the AI
   analyzes it in the background.
4. AI returns root cause, confidence, evidence reasoning, recommended playbook,
   risk level and missing/stale sources.
5. **LOW** risk → auto-executed → telemetry RECOVERING → NORMAL → incident
   RESOLVED.
6. **MEDIUM/HIGH** risk → status `AWAITING_APPROVAL`. Type an **execution note**
   (safe during background polling) and **Approve & Execute**.
7. After execution the simulated infrastructure returns to NORMAL and the
   incident becomes RESOLVED. History + audit are preserved.

### Scenarios (all with correlated telemetry)

- `cooling_failure` — HVAC fault, rack/hall temp spike, fan RPM max, app latency drift
- `network_device_fault` — core/edge latency + loss, throughput drop, app errors
- `application_deployment_issue` — checkout-service CRITICAL, error/response spikes
- `power_ups_issue` — UPS on battery, battery drain, load spike, flaky IoT
- `message_queue_worker_backlog` — queue depth/lag explosion, slow services
- `noisy_client_traffic_spike` — throughput spike, edge latency/loss, app errors

---

## Production deployment

### 1. Railway backend

1. Push `backend/` (or the whole repo) to a Railway service. Railway auto-detects
   `pyproject.toml`; set the start command:

   ```
   uvicorn app.main:app --host 0.0.0.0 --port $PORT
   ```

   (Ensure the working directory is `backend/`. If you deploy the whole repo,
   set `root directory` to `backend` in the Railway service settings.)
2. Add a **PostgreSQL** plugin to the service.
3. Environment variables (all optional except the DB URL Railway injects):
   - `DATABASE_URL` — auto-provided by the Postgres plugin (`postgres://...` is
     handled automatically).
   - `GROQ_API_KEY` — for LLM diagnosis.
   - `CORS_ORIGINS` — comma-separated frontend origins, e.g. `https://your-app.vercel.app`.

The app creates its tables on startup; no migration step needed.

### 2. Vercel frontend

1. Create a Vercel project pointing at the repo. Set:
   - Build command: none (static)
   - Output directory: `frontend` (or use the Vercel "static" preset)
   - Install command: none
2. Set the backend URL. The frontend reads `window.AIOPS_API_BASE` from
   `frontend/config.js`. Either edit that file:

   ```js
   window.AIOPS_API_BASE = "https://your-app.up.railway.app";
   ```

   or add a Vercel environment variable and a small inline script in the HTML
   (do not hardcode it in versioned code if you prefer env-driven):

   ```html
   <script>window.AIOPS_API_BASE = "https://your-app.up.railway.app";</script>
   ```

   Place this before the `<script src="/config.js">` tag.

### 3. Production DB (Railway PostgreSQL)

- Provided automatically by the Railway Postgres plugin.
- Local development stays on SQLite; switch by setting `DATABASE_URL` to a
  `postgresql://...` URL. `postgres://` prefixes are converted automatically.
- The database file is never committed (see `.gitignore`).

### CORS

- `localhost` origins are always allowed. Add your Vercel domain via
  `CORS_ORIGINS`. With no `CORS_ORIGINS` set, all origins are allowed (demo,
  no credentials).

### Security

- `GROQ_API_KEY` is read server-side only and is never exposed to the frontend.
- No secrets are committed (`.env`, `*.db`, `backend/data/` ignored).

---

## API overview

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/health` | Health + AI/db status |
| GET | `/api/config` | Scenarios, playbooks, risk policy (public) |
| GET | `/api/telemetry/current` | Current telemetry (state + sources) |
| GET | `/api/telemetry/history` | Stored snapshots (incl. degraded ones) |
| POST | `/api/scenarios/inject` | Inject scenario (creates incident + analysis) |
| POST | `/api/scenarios/clear` | Manual clear (returns telemetry to NORMAL) |
| GET | `/api/incidents` | Incident list (summaries with diagnosis/decision) |
| GET | `/api/incidents/{id}` | Incident detail (+ snapshot + audit) |
| GET | `/api/incidents/{id}/similar` | Similar historical incidents |
| POST | `/api/incidents/{id}/approve` | Approve + execute (execution note) |
| POST | `/api/incidents/{id}/reject` | Reject + clear scenario |
| GET | `/api/audit` | Audit trail |

---

## Test checklist

- [ ] Dashboard opens with NORMAL, healthy readings on all four source cards.
- [ ] Inject a LOW-risk scenario (`cooling_failure`): degraded readings appear
      immediately, incident auto-resolves, telemetry returns to NORMAL.
- [ ] Inject a MEDIUM/HIGH scenario (`network_device_fault`, `power_ups_issue`):
      status becomes `AWAITING_APPROVAL`, approval panel appears.
- [ ] Typing in the execution note survives background polling (no page reload,
      no focus loss, no cleared textarea).
- [ ] Approve & Execute: incident → EXECUTED → RESOLVED, telemetry → RECOVERING → NORMAL.
- [ ] Reject works and clears the scenario.
- [ ] Correlated telemetry: each scenario moves multiple sources, not one value.
- [ ] Diagnosis shows root cause, confidence, reasoning, playbook, risk, missing sources.
- [ ] Missing/stale data: check a source box, inject → diagnosis reports it and
      confidence drops; app does not crash.
- [ ] Similar historical incidents are retrieved (`/api/incidents/{id}/similar`).
- [ ] Audit trail records injection, diagnosis, approval, execution, resolution.
- [ ] History preserved: resolved incidents and degraded snapshots remain.
- [ ] Groq unavailable → safe fallback diagnosis labelled "fallback".
- [ ] SQLite works locally (no PostgreSQL needed); DB file under `backend/data/`.
- [ ] `DATABASE_URL` switching to PostgreSQL works (same ORM code path).
- [ ] CORS: localhost + configured origins; headers present on `/api` responses.
- [ ] No page reloads anywhere (only `fetch()` + partial DOM updates).

---

## Notes

- Run from `backend/` (`uv run uvicorn app.main:app --reload`) so the venv and
  module paths stay consistent — avoid overlapping virtualenvs in parent dirs.
- SQLite default path is derived from the backend directory (not the shell CWD),
  so it works from any working directory.
