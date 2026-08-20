# AIOps Simulation Platform

A human-governed AIOps platform that correlates **simulated network telemetry, application telemetry, facility alarms, and IoT sensor streams** to identify likely root causes of service degradation and recommend **safe recovery playbooks**.

The platform ranks recovery actions by **risk**, applies **human approval controls** to higher-risk actions, maintains an **audit trail**, and continues to provide diagnostics when some telemetry sources are missing or stale.

> **Important:** This is a simulation/demo platform. It does **not** control real infrastructure, execute real remediation commands, or collect real production telemetry. All scenarios, telemetry, and playbook executions are simulated.

---

## Architecture

```text
Railway
└── FastAPI + Uvicorn
    ├── Frontend
    │   ├── Dashboard
    │   └── Admin / Operations
    ├── REST API
    ├── Simulation Engine
    ├── Groq LLM (optional)
    └── SQLite
        └── Persistent database on Railway Volume


Local Development

Browser
   │
   ▼
FastAPI + Uvicorn
   ├── HTML / CSS / JavaScript frontend
   ├── REST API
   ├── Simulation engine
   ├── Groq LLM (optional)
   └── SQLite
```

### Technology Stack

* **Frontend:** HTML, CSS, vanilla JavaScript
* **Backend:** Python, FastAPI, Uvicorn
* **Database:** SQLite
* **ORM:** SQLAlchemy
* **AI:** Groq API with `openai/gpt-oss-120b`
* **Validation:** Pydantic
* **Deployment:** Railway
* **Persistent storage:** Railway Volume
* **Telemetry:** Simulated telemetry and correlated scenarios

The frontend communicates with the FastAPI backend using REST endpoints and JavaScript `fetch()` calls. The application does not require a separate frontend deployment.

### Database architecture

SQLite is the actual database used by the application, while **SQLAlchemy provides the ORM layer** used by the backend to work with the database.

This keeps database operations separated from the application logic and allows the same ORM-based code to manage incidents, telemetry history, diagnoses, and audit records.

For local development, the SQLite database is stored under the backend data directory.

For Railway deployment, the SQLite database should be placed on a **Railway Volume** so that database data persists across application restarts and redeployments.

---

## Telemetry and Incident State

Telemetry state and incident state are intentionally kept separate.

```text
Telemetry:
NORMAL ──► DEGRADED ──► RECOVERING ──► NORMAL

Incident:
DETECTED ──► ANALYZED ──►
AWAITING_APPROVAL ──► EXECUTED ──► RESOLVED
```

An old incident does not permanently make the live dashboard appear unhealthy. Current telemetry is controlled by the active simulation scenario, while incidents, telemetry snapshots, diagnoses, and audit records remain available in history.

---

## AI Diagnosis

The platform uses Groq for AI-assisted root-cause analysis.

The AI receives correlated evidence from:

* Network telemetry
* Application telemetry
* Facility alarms
* IoT sensor readings

The AI produces a structured diagnosis containing:

* Likely root cause
* Confidence score
* Evidence-based reasoning
* Recommended playbook
* Risk level
* Missing or stale data sources

The AI is constrained to the application's predefined root-cause labels and playbooks rather than being allowed to invent arbitrary remediation actions.

If Groq is unavailable or produces invalid output, the platform safely falls back to a deterministic rule-based diagnosis.

This ensures that the application remains functional even without an LLM API key.

---

## Risk Governance

Risk is determined by the application's predefined playbook policy rather than being freely chosen by the AI.

| Risk   | Execution Policy                                                                             | Example Playbooks                                              |
| ------ | -------------------------------------------------------------------------------------------- | -------------------------------------------------------------- |
| LOW    | Can be automatically executed because the simulated action is considered safe and reversible | `pb_hvac_recovery`, `pb_queue_scale_up`                        |
| MEDIUM | Human approval required                                                                      | `pb_network_failover`, `pb_app_rollback`, `pb_client_throttle` |
| HIGH   | Explicit human approval required                                                             | `pb_power_switchover`                                          |

The AI can recommend a playbook, but it cannot bypass the platform's risk governance rules.

All simulated executions are recorded in the audit trail.

---

## Project Layout

```text
project/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   │
│   │   ├── ai/
│   │   │   ├── diagnosis.py
│   │   │   ├── fallback.py
│   │   │   ├── prompts.py
│   │   │   └── validation.py
│   │   │
│   │   ├── database/
│   │   │   └── db.py
│   │   │
│   │   ├── models/
│   │   │   ├── entities.py
│   │   │   └── schemas.py
│   │   │
│   │   ├── routes/
│   │   │   └── api.py
│   │   │
│   │   ├── services/
│   │   │   ├── audit.py
│   │   │   ├── historical.py
│   │   │   ├── incidents.py
│   │   │   └── telemetry.py
│   │   │
│   │   ├── simulation/
│   │   │   ├── generator.py
│   │   │   └── scenarios.py
│   │   │
│   │   └── playbooks.py
│   │
│   ├── data/
│   │   ├── .gitkeep
│   │   └── aiops.db        # generated locally
│   │
│   ├── .env.example
│   ├── pyproject.toml
│   └── uv.lock
│
├── frontend/
│   ├── config.js
│   ├── dashboard/
│   │   ├── index.html
│   │   ├── style.css
│   │   └── app.js
│   └── admin/
│       ├── index.html
│       ├── style.css
│       └── app.js
│
├── .gitignore
└── README.md
```

---

## Local Setup

### Prerequisites

* Python 3.11+
* `uv`

From the project root:

```bash
cd backend
uv sync
```

Create your environment file if required:

```bash
cp .env.example .env
```

Start the application:

```bash
uv run uvicorn app.main:app --reload
```

The application will be available at:

```text
http://localhost:8000
```

### Dashboard

```text
http://localhost:8000/dashboard/
```

### Admin / Operations

```text
http://localhost:8000/admin/
```

The application can run without a Groq API key. In that case, it uses the deterministic rule-based fallback diagnosis.

To enable AI-assisted diagnosis, add your Groq API key to:

```text
backend/.env
```

```env
GROQ_API_KEY=your_api_key_here
```

---

## Environment Variables

Example configuration:

```env
# --- AI ---
GROQ_API_KEY=
GROQ_MODEL=openai/gpt-oss-120b
AI_TIMEOUT=45

# --- CORS ---
CORS_ORIGINS=
```

The `.env` file is intentionally excluded from Git.

Only `.env.example` is committed.

---

## Core Demo Flow

1. The dashboard starts in a **NORMAL** state with healthy simulated telemetry.
2. Open **Admin / Operations**.
3. Select and inject a simulation scenario.
4. The simulation engine generates correlated degraded telemetry.
5. An incident is created.
6. The AI analyzes the available evidence.
7. The platform produces:

   * Root cause
   * Confidence
   * Reasoning
   * Recommended playbook
   * Risk level
   * Missing/stale sources
8. LOW-risk actions can be automatically executed.
9. MEDIUM/HIGH-risk actions enter `AWAITING_APPROVAL`.
10. A human can approve or reject the proposed action.
11. The simulated infrastructure enters `RECOVERING`.
12. Telemetry returns to `NORMAL`.
13. The incident becomes `RESOLVED`.
14. Incident history and audit records remain stored.

---

## Simulation Scenarios

The platform includes correlated multi-source scenarios.

### `cooling_failure`

Simulates:

* HVAC fault
* Facility temperature increase
* Fan RPM changes
* Application latency degradation

### `network_device_fault`

Simulates:

* Network latency increase
* Packet loss
* Throughput degradation
* Application errors

### `application_deployment_issue`

Simulates:

* Application service degradation
* Increased error rate
* Response-time spikes

### `power_ups_issue`

Simulates:

* UPS switching to battery
* Battery drain
* Increased load
* IoT instability

### `message_queue_worker_backlog`

Simulates:

* Queue depth increase
* Message lag
* Slow downstream services

### `noisy_client_traffic_spike`

Simulates:

* Traffic spike
* Edge latency/loss
* Application errors

---

## Missing and Stale Telemetry

The platform can simulate unavailable or stale telemetry sources.

When a source is missing:

* The application continues operating.
* The missing source is reported to the diagnosis system.
* AI confidence can decrease.
* The diagnosis explicitly identifies incomplete evidence.
* The application does not crash because of the missing source.

This demonstrates the platform's ability to perform degraded-mode diagnosis instead of depending on every telemetry source being continuously available.

---

## API Overview

| Method | Endpoint                      | Purpose                              |
| ------ | ----------------------------- | ------------------------------------ |
| GET    | `/api/health`                 | Application health and status        |
| GET    | `/api/config`                 | Scenarios and playbook configuration |
| GET    | `/api/telemetry/current`      | Current simulated telemetry          |
| GET    | `/api/telemetry/history`      | Historical telemetry snapshots       |
| POST   | `/api/scenarios/inject`       | Inject a simulation scenario         |
| POST   | `/api/scenarios/clear`        | Clear the active scenario            |
| GET    | `/api/incidents`              | List incidents                       |
| GET    | `/api/incidents/{id}`         | Incident details                     |
| GET    | `/api/incidents/{id}/similar` | Similar historical incidents         |
| POST   | `/api/incidents/{id}/approve` | Approve and execute a playbook       |
| POST   | `/api/incidents/{id}/reject`  | Reject the proposed action           |
| GET    | `/api/audit`                  | View the audit trail                 |

---

## Audit Trail

The platform maintains an audit trail of important operational events, including:

* Scenario injection
* Telemetry changes
* AI diagnosis
* Playbook recommendation
* Approval decisions
* Rejections
* Simulated execution
* Incident resolution

This provides traceability for the human-governed decision-making process.

---

## Railway Deployment

The application is designed to run as a **single Railway service**.

The backend serves the API and the frontend, so a separate frontend deployment such as Vercel is not required.

### 1. Create a Railway service

Deploy the project repository to Railway.

Set the service's root directory to:

```text
backend
```

### 2. Build / install

Railway can use the project's Python dependency configuration from:

```text
backend/pyproject.toml
```

### 3. Start command

Use:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

### 4. Configure the Railway Volume

Because SQLite is a file-based database, attach a **Railway Volume** to the service.

Mount the volume at a persistent path such as:

```text
/data
```

The production SQLite database should then be configured to use a file on that persistent volume, for example:

```text
/data/aiops.db
```

This prevents the database from being lost when the application container is restarted or redeployed.

### 5. Environment variables

Add the required production environment variables in Railway:

```text
GROQ_API_KEY=your_key
GROQ_MODEL=openai/gpt-oss-120b
```

Configure the SQLite database path according to the application's production configuration.

### 6. Access the application

After deployment, Railway provides a public HTTPS URL.

The same application provides:

```text
https://your-railway-domain/dashboard/
https://your-railway-domain/admin/
```

No separate Vercel frontend is required.

---

## Production Storage

The production architecture intentionally uses **SQLite + Railway Volume**.

```text
Railway Service
      │
      ├── FastAPI
      │
      ├── Frontend
      │
      └── SQLite
           │
           ▼
      Railway Volume
           │
           └── aiops.db
```

The database stores application state such as:

* Incidents
* Telemetry history
* Diagnoses
* Audit events
* Historical incident information

The SQLite database file itself is not committed to Git.

---

## Security

* `.env` files are excluded from Git.
* API keys are kept server-side.
* The Groq API key is never exposed to the frontend.
* The project does not execute real infrastructure commands.
* Playbook execution is simulated.
* Risk governance is enforced by the application rather than delegated entirely to the LLM.
* Higher-risk actions require human approval.

---

## Test Checklist

* Dashboard opens with NORMAL telemetry.
* All four telemetry source cards display correctly.
* Scenario injection changes correlated telemetry.
* LOW-risk scenarios can complete the simulated recovery flow.
* MEDIUM/HIGH-risk scenarios require approval.
* Approval and rejection work correctly.
* Execution notes are preserved during polling.
* Telemetry transitions through RECOVERING and returns to NORMAL.
* Incidents remain available in history after resolution.
* Audit events are recorded.
* Similar historical incidents can be retrieved.
* Missing/stale telemetry is handled without crashing.
* AI diagnosis returns structured results when Groq is available.
* Rule-based fallback works when Groq is unavailable.
* SQLite persists application records.
* Frontend communicates with FastAPI through `fetch()`.
* The application can run as a single Railway service.

---

## Important Limitations

This project is a **working AIOps simulation/demo**, not a production infrastructure controller.

It currently uses:

* Simulated telemetry
* Simulated incidents
* Simulated remediation
* SQLite storage
* Optional Groq AI diagnosis

It does **not** currently connect directly to:

* Prometheus
* Real server telemetry
* Real network devices
* Real facility systems
* Real IoT hardware
* Real remediation infrastructure

The architecture is designed so these integrations can be added later without changing the core human-governed incident and risk-management concept.

---

## Project Goal

The goal of the platform is to demonstrate a **human-governed AIOps workflow** in which multiple telemetry sources are correlated, AI assists with root-cause analysis, recovery actions are governed by risk, consequential actions require human approval, and every operational decision is auditable.

The platform prioritizes **safe, explainable, and traceable automation** rather than unrestricted autonomous infrastructure control.
