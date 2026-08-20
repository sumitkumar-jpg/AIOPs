"""Deterministic rule-based diagnosis used when Groq is unavailable or invalid.

Purely evidence-based: it reads the actual telemetry payload and picks the
root cause whose correlated signals are strongest. Missing data lowers
confidence and can lead to 'insufficient_data'.
"""

from app.playbooks import ROOT_CAUSES_BY_ID


def _sources(context: dict) -> dict:
    return (context.get("telemetry") or {}).get("sources") or {}


def _facility(context: dict) -> dict:
    return _sources(context).get("facility") or {}


def _network(context: dict) -> dict:
    return _sources(context).get("network") or {}


def _app(context: dict) -> dict:
    return _sources(context).get("application") or {}


def _iot(context: dict) -> dict:
    return _sources(context).get("iot") or {}


def _num(value):
    return value if isinstance(value, (int, float)) else 0.0


def _reason(points: list) -> str:
    return "Evidence: " + "; ".join(points) + "."


def fallback_diagnosis(context: dict) -> dict:
    tel = context.get("telemetry") or {}
    sources = tel.get("sources") or {}
    missing = context.get("missing_sources") or []
    stale = context.get("stale_sources") or []

    fac = sources.get("facility") or {}
    net = sources.get("network") or {}
    app = sources.get("application") or {}
    iot = sources.get("iot") or {}

    missing_weight = 0.12
    base_conf = 0.62
    penalty = missing_weight * len(missing) + 0.05 * len(stale)

    evidence_points = []
    root_cause = "insufficient_data"
    confidence = 0.30

    # Only trust facility/IoT-derived signals when those sources are available.
    facility_available = "facility" not in missing
    iot_available = "iot" not in missing

    # --- Power / UPS --------------------------------------------------- #
    ups = (fac.get("ups_status") or "ONLINE").upper()
    alarms = [a.get("name", "") for a in fac.get("alarms") or []]
    battery = _num(fac.get("ups_battery_pct"))
    if facility_available and (ups == "ON_BATTERY" or any("POWER" in a or "UPS" in a for a in alarms) or battery < 40):
        root_cause = "power_ups_issue"
        confidence = base_conf + 0.22
        evidence_points = [
            f"ups_status={ups}",
            f"battery={battery}%",
            f"facility_alarms={alarms or 'none'}",
            f"power_load_kw={fac.get('power_load_kw')}",
        ]

    # --- Cooling / HVAC ------------------------------------------------ #
    temp = _num(fac.get("temperature_c"))
    hvac = (fac.get("hvac_status") or "RUNNING").upper()
    rack_temps = [
        _num(s.get("value"))
        for s in iot.get("sensors") or []
        if "temp" in s.get("name", "")
    ]
    high_rack = max(rack_temps, default=0) >= 30
    cooling_evidence = (
        (facility_available and (temp >= 28 or hvac == "FAULT"))
        or high_rack
        or any("TEMP" in a or "HVAC" in a for a in alarms)
    )
    if cooling_evidence:
        root_cause = "cooling_failure"
        confidence = base_conf + 0.20
        evidence_points = [
            f"temperature_c={temp if facility_available else 'N/A'}",
            f"hvac_status={hvac if facility_available else 'N/A'}",
            f"rack_temps={rack_temps if iot_available else 'N/A'}",
            f"fan_bank_rpm={next((_num(s.get('value')) for s in (iot.get('sensors') or []) if s.get('name') == 'fan-bank-rpm'), 0)}",
        ]

    # --- Message queue backlog ---------------------------------------- #
    queue = app.get("queue") or {}
    depth = _num(queue.get("depth"))
    lag = _num(queue.get("lag"))
    if depth > 2000 or lag > 500:
        root_cause = "message_queue_worker_backlog"
        confidence = base_conf + 0.25
        evidence_points = [
            f"queue_depth={depth}",
            f"consumer_lag={lag}",
            f"consumers={queue.get('consumers')}",
            f"avg_response_ms={_avg([_num(s.get('response_time_ms')) for s in app.get('services') or []])}",
        ]

    # --- Network device fault ----------------------------------------- #
    worst_lat = max([_num(d.get("latency_ms")) for d in net.get("devices") or []], default=0)
    worst_loss = max([_num(d.get("loss_pct")) for d in net.get("devices") or []], default=0)
    device_states = [d.get("status") for d in net.get("devices") or []]
    if worst_lat > 50 or worst_loss > 1 or "DEGRADED" in device_states:
        root_cause = "network_device_fault"
        confidence = base_conf + 0.18
        evidence_points = [
            f"device_states={device_states}",
            f"worst_latency_ms={worst_lat}",
            f"worst_loss_pct={worst_loss}",
            f"app_error_rate={_avg([_num(s.get('error_rate_pct')) for s in app.get('services') or []])}",
        ]

    # --- Traffic spike ------------------------------------------------- #
    # Checked after network so a real traffic burst (throughput far above
    # baseline) takes precedence over the secondary network degradation.
    throughput = _num(net.get("throughput_mbps"))
    if throughput > 2000:
        root_cause = "noisy_client_traffic_spike"
        confidence = base_conf + 0.22
        evidence_points = [
            f"throughput_mbps={throughput}",
            f"edge_latency_ms={_avg([_num(d.get('latency_ms')) for d in net.get('devices') or [] if 'edge' in d.get('name', '')])}",
            f"edge_loss_pct={_avg([_num(d.get('loss_pct')) for d in net.get('devices') or [] if 'edge' in d.get('name', '')])}",
        ]

    # --- Application deployment --------------------------------------- #
    # A deployment problem shows a *sharp* service-level error spike
    # (CRITICAL status or very high error rate), not just mild degradation
    # that also appears under network/queue/traffic stress.
    services = app.get("services") or []
    statuses = [s.get("status") for s in services]
    worst_err = max([_num(s.get("error_rate_pct")) for s in services], default=0)
    worst_rt = max([_num(s.get("response_time_ms")) for s in services], default=0)
    if "CRITICAL" in statuses or worst_err > 8:
        root_cause = "application_deployment_issue"
        confidence = base_conf + 0.18
        evidence_points = [
            f"service_statuses={statuses}",
            f"worst_error_rate_pct={worst_err}",
            f"worst_response_ms={worst_rt}",
        ]

    # --- Missing / stale handling -------------------------------------- #
    # If the primary evidence sources are gone, we cannot be confident.
    primary_missing = {"network", "application", "facility", "iot"} & set(missing)
    if root_cause == "insufficient_data" or len(primary_missing) >= 2:
        root_cause = "insufficient_data"
        confidence = 0.30
        evidence_points = [
            f"missing_sources={missing}",
            f"stale_sources={stale}",
            "Too little evidence available for a confident diagnosis.",
        ]

    confidence = max(0.25, min(0.92, confidence - penalty))
    missing_note = (
        f" Missing sources reduce confidence: {missing + stale or 'none'}."
        if (missing or stale)
        else ""
    )

    if root_cause == "insufficient_data":
        reasoning = (
            "Not enough live evidence to identify a root cause with confidence. "
            f"Missing/stale sources: {missing + stale or 'none'}. "
            "Recommendation is to observe and hold until data recovers."
        )
        playbook = "pb_observe_and_hold"
        risk = "LOW"
    else:
        playbook_map = {
            "cooling_failure": "pb_hvac_recovery",
            "network_device_fault": "pb_network_failover",
            "application_deployment_issue": "pb_app_rollback",
            "power_ups_issue": "pb_power_switchover",
            "message_queue_worker_backlog": "pb_queue_scale_up",
            "noisy_client_traffic_spike": "pb_client_throttle",
        }
        playbook = playbook_map.get(root_cause, "pb_observe_and_hold")
        risk_map = {
            "cooling_failure": "LOW",
            "network_device_fault": "MEDIUM",
            "application_deployment_issue": "MEDIUM",
            "power_ups_issue": "HIGH",
            "message_queue_worker_backlog": "LOW",
            "noisy_client_traffic_spike": "MEDIUM",
        }
        risk = risk_map.get(root_cause, "MEDIUM")
        reasoning = _reason(evidence_points) + missing_note

    return {
        "likely_root_cause": root_cause,
        "confidence": round(confidence, 2),
        "reasoning": reasoning,
        "recommended_playbook_id": playbook,
        "risk_level": risk,
        "missing_data_sources": list(dict.fromkeys((missing or []) + (stale or []))),
    }


def _avg(values) -> float:
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 1) if values else 0.0
