"""Validation of the structured AI diagnosis.

Enforces that the AI only picks predefined root causes and predefined playbooks
and that the risk level matches the playbook's fixed risk. Raises ValueError on
invalid output so the caller can fall back to the rule-based diagnosis.
"""

from app.playbooks import PLAYBOOKS_BY_ID, ROOT_CAUSES_BY_ID


def validate_diagnosis(data: dict, context: dict) -> dict:
    root_cause = (data or {}).get("likely_root_cause")
    playbook_id = (data or {}).get("recommended_playbook_id")

    if root_cause not in ROOT_CAUSES_BY_ID:
        raise ValueError(f"root cause '{root_cause}' is not in the allowed set")
    if playbook_id not in PLAYBOOKS_BY_ID:
        raise ValueError(f"playbook '{playbook_id}' is not in the allowed set")

    playbook = PLAYBOOKS_BY_ID[playbook_id]
    risk_level = (data.get("risk_level") or playbook["risk_level"]).upper()
    if risk_level not in ("LOW", "MEDIUM", "HIGH"):
        raise ValueError(f"invalid risk level '{risk_level}'")
    # Risk is governed by the playbook, not a free-form AI choice.
    if risk_level != playbook["risk_level"]:
        risk_level = playbook["risk_level"]

    confidence = float(data.get("confidence") or 0.0)
    confidence = max(0.0, min(1.0, round(confidence, 2)))

    reasoning = str(data.get("reasoning") or "").strip()
    if not reasoning:
        raise ValueError("reasoning is empty")

    missing = list(data.get("missing_data_sources") or [])
    actual_missing = list(
        dict.fromkeys((context.get("missing_sources") or []) + (context.get("stale_sources") or []))
    )
    missing = list(dict.fromkeys(missing + actual_missing))

    return {
        "likely_root_cause": root_cause,
        "confidence": confidence,
        "reasoning": reasoning,
        "recommended_playbook_id": playbook_id,
        "risk_level": risk_level,
        "missing_data_sources": missing,
    }
