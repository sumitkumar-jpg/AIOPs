"""Audit trail helper. Every meaningful system/human action is recorded."""

from app.models.entities import AuditLog


def log(db, actor: str, action: str, detail: str, incident_id=None) -> AuditLog:
    entry = AuditLog(
        actor=actor,
        action=action,
        detail=detail,
        incident_id=incident_id,
    )
    db.add(entry)
    db.commit()
    return entry


def list_audit(db, limit: int = 200) -> list:
    return (
        db.query(AuditLog)
        .order_by(AuditLog.timestamp.desc(), AuditLog.id.desc())
        .limit(limit)
        .all()
    )
