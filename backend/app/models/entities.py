"""SQLAlchemy ORM entities.

Stores: telemetry snapshots, incidents, diagnoses, playbook decisions
(approvals + execution notes/results) and an audit trail.
"""

from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)

from app.database.db import Base


def utcnow() -> datetime:
    return datetime.utcnow()


class TelemetrySnapshot(Base):
    """Point-in-time copy of the full telemetry payload (bad readings preserved)."""

    __tablename__ = "telemetry_snapshots"

    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=utcnow, nullable=False, index=True)
    state = Column(String(32), default="NORMAL", nullable=False)
    scenario_id = Column(String(64), nullable=True, index=True)
    payload_json = Column(Text, nullable=False)


class Incident(Base):
    __tablename__ = "incidents"

    id = Column(Integer, primary_key=True)
    scenario_id = Column(String(64), nullable=False, index=True)
    scenario_name = Column(String(200), nullable=False)
    severity = Column(String(32), default="major", nullable=False)
    status = Column(String(32), default="DETECTED", nullable=False, index=True)
    affected_services = Column(Text, default="[]")
    affected_devices = Column(Text, default="[]")
    zone = Column(String(100), default="")
    missing_sources = Column(Text, default="[]")
    stale_sources = Column(Text, default="[]")
    snapshot_id = Column(Integer, ForeignKey("telemetry_snapshots.id"), nullable=True)
    detected_at = Column(DateTime, default=utcnow, nullable=False, index=True)
    resolved_at = Column(DateTime, nullable=True)


class Diagnosis(Base):
    __tablename__ = "diagnoses"

    id = Column(Integer, primary_key=True)
    incident_id = Column(Integer, ForeignKey("incidents.id"), nullable=False, index=True)
    likely_root_cause = Column(String(64), nullable=False)
    confidence = Column(Float, default=0.0, nullable=False)
    reasoning = Column(Text, default="")
    recommended_playbook_id = Column(String(64), nullable=False)
    risk_level = Column(String(16), nullable=False)
    missing_data_sources = Column(Text, default="[]")
    ai_engine = Column(String(32), default="fallback", nullable=False)
    ai_note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)


class PlaybookDecision(Base):
    """One playbook recommendation per incident, with approval + execution info."""

    __tablename__ = "playbook_decisions"

    id = Column(Integer, primary_key=True)
    incident_id = Column(Integer, ForeignKey("incidents.id"), nullable=False, index=True)
    playbook_id = Column(String(64), nullable=False)
    playbook_title = Column(String(200), default="")
    risk_level = Column(String(16), nullable=False)
    status = Column(String(32), default="AWAITING_APPROVAL", nullable=False)
    note = Column(Text, nullable=True)
    approved_by = Column(String(64), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    executed_at = Column(DateTime, nullable=True)
    result_json = Column(Text, nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=utcnow, nullable=False, index=True)
    actor = Column(String(64), nullable=False)
    action = Column(String(64), nullable=False)
    detail = Column(Text, default="")
    incident_id = Column(Integer, ForeignKey("incidents.id"), nullable=True, index=True)
