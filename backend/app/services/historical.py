"""Retrieval of similar historical incidents.

Used as supporting context for the AI. The current telemetry always has
priority; history only adds colour. Matching is a simple structured query on
scenario/root cause and recent time window - no vector DB required.
"""

from app.models.entities import Diagnosis, Incident, PlaybookDecision


def find_similar(db, incident, limit: int = 5) -> list:
    """Return the most relevant recent resolved incidents (excluding current)."""
    rows = (
        db.query(Incident)
        .filter(Incident.id != incident.id)
        .order_by(Incident.detected_at.desc())
        .limit(40)
        .all()
    )

    def score(other: Incident) -> int:
        s = 0
        if other.scenario_id == incident.scenario_id:
            s += 3
        if other.zone and incident.zone and other.zone == incident.zone:
            s += 1
        return s

    scored = sorted(rows, key=score, reverse=True)
    results = []
    for other in scored[:limit]:
        diag = (
            db.query(Diagnosis)
            .filter(Diagnosis.incident_id == other.id)
            .order_by(Diagnosis.id.desc())
            .first()
        )
        decision = (
            db.query(PlaybookDecision)
            .filter(PlaybookDecision.incident_id == other.id)
            .order_by(PlaybookDecision.id.desc())
            .first()
        )
        results.append(
            {
                "incident_id": other.id,
                "scenario_id": other.scenario_id,
                "scenario_name": other.scenario_name,
                "detected_at": other.detected_at.isoformat() + "Z",
                "root_cause": diag.likely_root_cause if diag else None,
                "confidence": round(diag.confidence, 2) if diag else None,
                "recommended_playbook_id": diag.recommended_playbook_id if diag else None,
                "risk_level": diag.risk_level if diag else None,
                "reasoning": diag.reasoning if diag else "",
                "decision_status": decision.status if decision else None,
                "outcome": ("resolved_ok" if other.status == "RESOLVED" else other.status),
            }
        )
    return results
