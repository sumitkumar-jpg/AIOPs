"""REST API for the AIOps platform."""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import AI_AVAILABLE, RECOVERY_DURATION_SECONDS
from app.database.db import get_db, ping_db
from app.models.schemas import InjectRequest, NoteRequest
from app.playbooks import PLAYBOOKS, RISK_POLICY, ROOT_CAUSES
from app.services import audit
from app.services import historical
from app.services import incidents as incidents_service
from app.services import telemetry as telemetry_service
from app.simulation.scenarios import SCENARIOS, TELEMETRY_SOURCES

router = APIRouter()


@router.get("/health")
def health():
    return {
        "status": "ok",
        "database": "ok" if ping_db() else "error",
        "ai": "available" if AI_AVAILABLE else "unavailable",
    }


@router.get("/config")
def public_config():
    """Public, non-secret config consumed by the frontends."""
    return {
        "scenarios": [
            {
                "id": s["id"],
                "name": s["name"],
                "description": s["description"],
                "severity": s["severity"],
                "root_cause_id": s["root_cause_id"],
                "playbook_id": s["playbook_id"],
            }
            for s in SCENARIOS.values()
        ],
        "playbooks": PLAYBOOKS,
        "root_causes": ROOT_CAUSES,
        "risk_policy": RISK_POLICY,
        "telemetry_sources": TELEMETRY_SOURCES,
        "recovery_duration_seconds": RECOVERY_DURATION_SECONDS,
    }


# --------------------------------------------------------------------------- #
# Telemetry
# --------------------------------------------------------------------------- #
@router.get("/telemetry/current")
def telemetry_current():
    return telemetry_service.get_current_telemetry()


@router.get("/telemetry/history")
def telemetry_history(limit: int = 50, db: Session = Depends(get_db)):
    from app.models.entities import TelemetrySnapshot

    rows = (
        db.query(TelemetrySnapshot)
        .order_by(TelemetrySnapshot.timestamp.desc(), TelemetrySnapshot.id.desc())
        .limit(min(limit, 200))
        .all()
    )
    return [
        {
            "id": r.id,
            "timestamp": r.timestamp.replace().isoformat() + "Z",
            "state": r.state,
            "scenario_id": r.scenario_id,
        }
        for r in rows
    ]


# --------------------------------------------------------------------------- #
# Scenario injection
# --------------------------------------------------------------------------- #
@router.post("/scenarios/inject")
def inject_scenario(body: InjectRequest, background: BackgroundTasks, db: Session = Depends(get_db)):
    if body.scenario_id not in SCENARIOS:
        raise HTTPException(status_code=404, detail=f"unknown scenario '{body.scenario_id}'")

    known_sources = set(TELEMETRY_SOURCES)
    missing = [s for s in body.missing_sources if s in known_sources]
    stale = [s for s in body.stale_sources if s in known_sources]

    telemetry_service.inject(body.scenario_id, missing, stale)
    incident = incidents_service.create_incident(db, body.scenario_id, missing, stale)

    # Analysis runs in the background so degraded telemetry appears immediately.
    background.add_task(incidents_service.run_diagnosis, incident.id)

    return {
        "incident": incidents_service._incident_summary(incident, db),
        "telemetry": telemetry_service.get_current_telemetry(),
    }


@router.post("/scenarios/clear")
def clear_scenario(db: Session = Depends(get_db)):
    incidents_service.clear_active_scenario(db)
    return telemetry_service.get_current_telemetry()


# --------------------------------------------------------------------------- #
# Incidents
# --------------------------------------------------------------------------- #
@router.get("/incidents")
def list_incidents(active_only: bool = False, db: Session = Depends(get_db)):
    return incidents_service.list_incidents(db, active_only=active_only)


@router.get("/incidents/{incident_id}")
def get_incident(incident_id: int, db: Session = Depends(get_db)):
    return incidents_service.get_incident(db, incident_id)


@router.get("/incidents/{incident_id}/similar")
def similar_incidents(incident_id: int, db: Session = Depends(get_db)):
    from app.models.entities import Incident

    incident = db.get(Incident, incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="incident not found")
    return {"similar_incidents": historical.find_similar(db, incident, limit=5)}


@router.post("/incidents/{incident_id}/approve")
def approve_incident(incident_id: int, body: NoteRequest = None, db: Session = Depends(get_db)):
    try:
        return incidents_service.approve(db, incident_id, note=(body.note if body else None) or "")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/incidents/{incident_id}/reject")
def reject_incident(incident_id: int, body: NoteRequest = None, db: Session = Depends(get_db)):
    try:
        return incidents_service.reject(db, incident_id, note=(body.note if body else None) or "")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


# --------------------------------------------------------------------------- #
# Audit
# --------------------------------------------------------------------------- #
@router.get("/audit")
def audit_log(limit: int = 200, db: Session = Depends(get_db)):
    return [
        {
            "id": a.id,
            "timestamp": a.timestamp.replace().isoformat() + "Z",
            "actor": a.actor,
            "action": a.action,
            "detail": a.detail,
            "incident_id": a.incident_id,
        }
        for a in audit.list_audit(db, limit=min(limit, 500))
    ]
