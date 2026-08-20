"""In-memory telemetry state machine.

Keeps the *current* telemetry view separate from incident/audit state so that
historical incidents never make the live dashboard look permanently broken.

State machine:
  NORMAL      - no scenario active, healthy baseline
  DEGRADED    - a scenario has been injected, degraded readings
  RECOVERING  - a playbook executed; anomalies decay back to baseline
"""

import time
from threading import RLock

from app.config import RECOVERY_DURATION_SECONDS
from app.simulation.generator import build_telemetry
from app.simulation.scenarios import SCENARIOS

_lock = RLock()
_active_scenario = None   # {"scenario_id", "injected_at", "missing", "stale"}
_recovery_started_at = None


def _now() -> float:
    return time.time()


def inject(scenario_id: str, missing: list, stale: list) -> None:
    global _active_scenario, _recovery_started_at
    with _lock:
        _recovery_started_at = None
        _active_scenario = {
            "scenario_id": scenario_id,
            "injected_at": _now(),
            "missing": missing or [],
            "stale": stale or [],
        }


def clear() -> None:
    """Manually stop a scenario (used when an operator rejects/clears)."""
    global _active_scenario
    with _lock:
        _active_scenario = None


def begin_recovery() -> None:
    """Start the recovery window after a playbook executes."""
    global _recovery_started_at
    with _lock:
        _recovery_started_at = _now()


def get_state() -> str:
    with _lock:
        if not _active_scenario:
            return "NORMAL"
        if _recovery_started_at is not None:
            elapsed = _now() - _recovery_started_at
            if elapsed >= RECOVERY_DURATION_SECONDS:
                return "NORMAL"
            return "RECOVERING"
        return "DEGRADED"


def _reap_finished_recovery():
    """Once recovery finishes, the active scenario is retired so the live
    telemetry returns to a clean NORMAL state (history is preserved in DB)."""
    global _active_scenario, _recovery_started_at
    if _active_scenario and _recovery_started_at is not None:
        if _now() - _recovery_started_at >= RECOVERY_DURATION_SECONDS:
            _active_scenario = None
            _recovery_started_at = None


def get_current_telemetry() -> dict:
    """Full telemetry payload with state + scenario metadata attached."""
    with _lock:
        _reap_finished_recovery()
        state = get_state()
        scenario_id = _active_scenario["scenario_id"] if _active_scenario else None
        scenario = SCENARIOS.get(scenario_id) if scenario_id else None

        factor = 1.0
        if scenario_id and _recovery_started_at is not None:
            elapsed = _now() - _recovery_started_at
            progress = max(0.0, min(1.0, elapsed / RECOVERY_DURATION_SECONDS))
            factor = 1.0 - progress

        payload = build_telemetry(
            scenario_id,
            factor=factor,
            missing=_active_scenario["missing"] if _active_scenario else [],
            stale=_active_scenario["stale"] if _active_scenario else [],
        )

    from datetime import datetime, timezone

    return {
        "state": state,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "active_scenario": (
            {
                "id": scenario["id"],
                "name": scenario["name"],
                "severity": scenario["severity"],
            }
            if scenario
            else None
        ),
        **payload,
    }
