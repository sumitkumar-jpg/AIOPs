"""Incident lifecycle orchestration.

Detected -> Analyzed -> AwaitingApproval | Executed -> Resolved.

A scenario injection creates an incident and a degraded telemetry snapshot,
then analysis runs (Groq with a safe rule-based fallback). LOW-risk playbooks
auto-execute; MEDIUM/HIGH require explicit human approval with an execution
note. Execution is always SIMULATED - this platform never touches real
infrastructure.
"""

import json
from datetime import datetime, timezone

from app.ai.diagnosis import diagnose
from app.config import AUTO_EXECUTE_LOW_RISK
from app.database.db import SessionLocal
from app.models.entities import (
    AuditLog,
    Diagnosis,
    Incident,
    PlaybookDecision,
    TelemetrySnapshot,
)
from app.playbooks import (
    PLAYBOOKS_BY_ID,
    risk_requires_approval,
)
from app.services import audit
from app.services import historical
from app.services import telemetry as telemetry_service
from app.simulation.generator import build_telemetry
from app.simulation.scenarios import SCENARIOS


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# Serializers
# --------------------------------------------------------------------------- #
def _incident_summary(inc: Incident, db) -> dict:
    diag = (
        db.query(Diagnosis)
        .filter(Diagnosis.incident_id == inc.id)
        .order_by(Diagnosis.id.desc())
        .first()
    )
    decision = (
        db.query(PlaybookDecision)
        .filter(PlaybookDecision.incident_id == inc.id)
        .order_by(PlaybookDecision.id.desc())
        .first()
    )
    return {
        "id": inc.id,
        "scenario_id": inc.scenario_id,
        "scenario_name": inc.scenario_name,
        "severity": inc.severity,
        "status": inc.status,
        "zone": inc.zone,
        "detected_at": _iso(inc.detected_at),
        "resolved_at": _iso(inc.resolved_at) if inc.resolved_at else None,
        "diagnosis": _diagnosis_dict(diag) if diag else None,
        "decision": _decision_dict(decision) if decision else None,
    }


def _diagnosis_dict(d: Diagnosis) -> dict:
    return {
        "id": d.id,
        "likely_root_cause": d.likely_root_cause,
        "confidence": round(d.confidence, 2),
        "reasoning": d.reasoning,
        "recommended_playbook_id": d.recommended_playbook_id,
        "risk_level": d.risk_level,
        "missing_data_sources": json.loads(d.missing_data_sources or "[]"),
        "ai_engine": d.ai_engine,
        "ai_note": d.ai_note,
        "created_at": _iso(d.created_at),
    }


def _decision_dict(d: PlaybookDecision) -> dict:
    return {
        "id": d.id,
        "playbook_id": d.playbook_id,
        "playbook_title": d.playbook_title,
        "risk_level": d.risk_level,
        "status": d.status,
        "note": d.note,
        "approved_by": d.approved_by,
        "approved_at": _iso(d.approved_at) if d.approved_at else None,
        "executed_at": _iso(d.executed_at) if d.executed_at else None,
        "result": json.loads(d.result_json) if d.result_json else None,
    }


def _iso(dt) -> str:
    return dt.replace(tzinfo=timezone.utc).isoformat() if dt else None


def _load_json(value, default):
    try:
        return json.loads(value) if value else default
    except Exception:
        return default


# --------------------------------------------------------------------------- #
# Creation
# --------------------------------------------------------------------------- #
def create_incident(db, scenario_id: str, missing: list, stale: list) -> Incident:
    scenario = SCENARIOS[scenario_id]

    telemetry = build_telemetry(scenario_id, factor=1.0, missing=missing, stale=stale)
    snapshot = TelemetrySnapshot(
        state="DEGRADED",
        scenario_id=scenario_id,
        payload_json=json.dumps(telemetry, default=str),
    )
    db.add(snapshot)
    db.flush()

    incident = Incident(
        scenario_id=scenario_id,
        scenario_name=scenario["name"],
        severity=scenario["severity"],
        status="DETECTED",
        affected_services=json.dumps(scenario.get("affected_services", [])),
        affected_devices=json.dumps(scenario.get("affected_devices", [])),
        zone=scenario.get("zone", ""),
        missing_sources=json.dumps(missing or []),
        stale_sources=json.dumps(stale or []),
        snapshot_id=snapshot.id,
        detected_at=utcnow(),
    )
    db.add(incident)
    db.commit()
    db.refresh(incident)

    audit.log(
        db,
        "system",
        "incident_detected",
        f"Scenario '{scenario['name']}' injected. Degraded telemetry written. "
        f"Missing sources: {missing or 'none'}; stale: {stale or 'none'}.",
        incident.id,
    )
    return incident


# --------------------------------------------------------------------------- #
# Diagnosis (runs in background after injection)
# --------------------------------------------------------------------------- #
def build_context(db, incident: Incident) -> dict:
    scenario = SCENARIOS[incident.scenario_id]
    snapshot = db.get(TelemetrySnapshot, incident.snapshot_id) if incident.snapshot_id else None
    telemetry = _load_json(snapshot.payload_json if snapshot else None, {})

    history = historical.find_similar(db, incident, limit=5)
    return {
        "scenario": {
            "id": scenario["id"],
            "name": scenario["name"],
            "description": scenario["description"],
        },
        "telemetry": telemetry,
        "missing_sources": _load_json(incident.missing_sources, []),
        "stale_sources": _load_json(incident.stale_sources, []),
        "historical_incidents": history,
    }


def run_diagnosis(incident_id: int) -> None:
    """Background analysis + decision routing. Uses its own DB session."""
    db = SessionLocal()
    try:
        incident = db.get(Incident, incident_id)
        if not incident or incident.status != "DETECTED":
            return

        context = build_context(db, incident)
        diagnosis_data, engine, note = diagnose(context)

        diagnosis = Diagnosis(
            incident_id=incident.id,
            likely_root_cause=diagnosis_data["likely_root_cause"],
            confidence=round(diagnosis_data["confidence"], 2),
            reasoning=diagnosis_data["reasoning"],
            recommended_playbook_id=diagnosis_data["recommended_playbook_id"],
            risk_level=diagnosis_data["risk_level"],
            missing_data_sources=json.dumps(diagnosis_data["missing_data_sources"]),
            ai_engine=engine,
            ai_note=note,
            created_at=utcnow(),
        )
        db.add(diagnosis)
        incident.status = "ANALYZED"
        db.commit()

        playbook = PLAYBOOKS_BY_ID[diagnosis_data["recommended_playbook_id"]]
        decision = PlaybookDecision(
            incident_id=incident.id,
            playbook_id=playbook["id"],
            playbook_title=playbook["title"],
            risk_level=playbook["risk_level"],
            status="AWAITING_APPROVAL",
        )
        db.add(decision)
        db.commit()

        requires_approval = risk_requires_approval(playbook["risk_level"])
        audit.log(
            db,
            "ai" if engine == "groq" else "fallback",
            "diagnosis_completed",
            f"Root cause '{diagnosis_data['likely_root_cause']}' "
            f"(confidence {diagnosis_data['confidence']:.0%}, engine={engine}). "
            f"Recommended '{playbook['id']}' ({playbook['risk_level']} risk). "
            f"Requires approval: {requires_approval}.",
            incident.id,
        )

        if requires_approval:
            incident.status = "AWAITING_APPROVAL"
            db.commit()
        elif AUTO_EXECUTE_LOW_RISK:
            db.refresh(decision)
            execute_decision(
                db,
                decision,
                note="Auto-executed (LOW risk, reversible simulated action).",
                approved_by="ai",
            )
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# Execution (always simulated)
# --------------------------------------------------------------------------- #
def _simulate_execution(playbook) -> dict:
    return {
        "playbook_id": playbook["id"],
        "title": playbook["title"],
        "risk_level": playbook["risk_level"],
        "result": "Simulated execution completed successfully. Infrastructure is returning to NORMAL.",
        "safe": True,
        "steps_executed": playbook["steps"],
        "affected_sources": playbook["affected_sources"],
    }


def execute_decision(db, decision: PlaybookDecision, note: str, approved_by: str = "operator") -> None:
    playbook = PLAYBOOKS_BY_ID[decision.playbook_id]
    incident = db.get(Incident, decision.incident_id)

    decision.status = "EXECUTED"
    decision.note = note
    decision.approved_by = approved_by
    decision.approved_at = decision.approved_at or utcnow()
    decision.executed_at = utcnow()
    decision.result_json = json.dumps(_simulate_execution(playbook), default=str)
    db.commit()

    if incident:
        incident.status = "EXECUTED"
        db.commit()

        telemetry_service.begin_recovery()
        recovering = build_telemetry(
            incident.scenario_id,
            factor=0.3,
            missing=_load_json(incident.missing_sources, []),
            stale=_load_json(incident.stale_sources, []),
        )
        db.add(TelemetrySnapshot(state="RECOVERING", scenario_id=incident.scenario_id,
                                 payload_json=json.dumps(recovering, default=str)))
        db.commit()

        incident.status = "RESOLVED"
        incident.resolved_at = utcnow()
        db.commit()

    audit.log(
        db,
        approved_by,
        "playbook_executed",
        f"Playbook '{playbook['id']}' ({playbook['risk_level']} risk) executed "
        f"(simulated). Incident #{decision.incident_id} resolved. Note: {note or 'none'}.",
        decision.incident_id,
    )


# --------------------------------------------------------------------------- #
# Human approval controls
# --------------------------------------------------------------------------- #
def approve(db, incident_id: int, note: str = "") -> dict:
    incident = db.get(Incident, incident_id)
    if not incident:
        raise ValueError("incident not found")
    if incident.status != "AWAITING_APPROVAL":
        raise ValueError(f"incident #{incident_id} is not awaiting approval (status={incident.status})")

    decision = (
        db.query(PlaybookDecision)
        .filter(PlaybookDecision.incident_id == incident_id, PlaybookDecision.status == "AWAITING_APPROVAL")
        .order_by(PlaybookDecision.id.desc())
        .first()
    )
    if not decision:
        raise ValueError("no decision awaiting approval")

    audit.log(
        db,
        "operator",
        "approval_granted",
        f"Approved '{decision.playbook_id}' for incident #{incident_id}. "
        f"Execution note: {note or 'none'}.",
        incident_id,
    )
    execute_decision(db, decision, note=note or "", approved_by="operator")
    return _incident_detail(db, incident_id)


def reject(db, incident_id: int, note: str = "") -> dict:
    incident = db.get(Incident, incident_id)
    if not incident:
        raise ValueError("incident not found")
    if incident.status != "AWAITING_APPROVAL":
        raise ValueError(f"incident #{incident_id} is not awaiting approval (status={incident.status})")

    decision = (
        db.query(PlaybookDecision)
        .filter(PlaybookDecision.incident_id == incident_id, PlaybookDecision.status == "AWAITING_APPROVAL")
        .order_by(PlaybookDecision.id.desc())
        .first()
    )
    if not decision:
        raise ValueError("no decision awaiting approval")

    decision.status = "REJECTED"
    decision.note = note or "Rejected by operator."
    db.commit()

    incident.status = "RESOLVED"
    incident.resolved_at = utcnow()
    db.commit()
    # Operator declined the automated playbook: manual ops intervene and the
    # scenario is cleared so the simulated infrastructure returns to normal.
    telemetry_service.clear()

    audit.log(
        db,
        "operator",
        "approval_rejected",
        f"Rejected '{decision.playbook_id}' for incident #{incident_id}. Note: {note or 'none'}.",
        incident_id,
    )
    return _incident_detail(db, incident_id)


def clear_active_scenario(db) -> None:
    """Manual 'clear scenario' button - stops simulation, keeps history."""
    telemetry_service.clear()
    normal = build_telemetry(None)
    db.add(TelemetrySnapshot(state="NORMAL", scenario_id=None, payload_json=json.dumps(normal, default=str)))
    db.commit()
    audit.log(db, "operator", "scenario_cleared", "Active scenario cleared manually. Telemetry returned to NORMAL.")


# --------------------------------------------------------------------------- #
# Detail / list
# --------------------------------------------------------------------------- #
def _incident_detail(db, incident_id: int) -> dict:
    inc = db.get(Incident, incident_id)
    snapshot = db.get(TelemetrySnapshot, inc.snapshot_id) if inc and inc.snapshot_id else None
    incidents_audit = (
        db.query(AuditLog)
        .filter(AuditLog.incident_id == incident_id)
        .order_by(AuditLog.timestamp.desc(), AuditLog.id.desc())
        .limit(100)
        .all()
    )
    return {
        **_incident_summary(inc, db),
        "telemetry": _load_json(snapshot.payload_json if snapshot else None, {}),
        "audit": [
            {
                "id": a.id,
                "timestamp": _iso(a.timestamp),
                "actor": a.actor,
                "action": a.action,
                "detail": a.detail,
            }
            for a in incidents_audit
        ],
    }


def list_incidents(db, active_only: bool = False) -> list:
    query = db.query(Incident).order_by(Incident.detected_at.desc())
    if active_only:
        query = query.filter(Incident.status.in_(["DETECTED", "ANALYZED", "AWAITING_APPROVAL", "EXECUTED"]))
    return [_incident_summary(inc, db) for inc in query.all()]


def get_incident(db, incident_id: int) -> dict:
    return _incident_detail(db, incident_id)
