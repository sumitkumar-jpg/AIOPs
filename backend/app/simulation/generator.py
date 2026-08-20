"""Telemetry generation.

Produces a realistic multi-source telemetry payload. In the normal state it
emits healthy baseline readings. When a scenario is active it emits correlated
degraded readings across the relevant sources (application, network, facility
and IoT) so the AI can reason from correlated evidence.

All values model a small e-commerce company (NexaCart) operating a single
server room (DC-01) in Mumbai, India.
"""

import random
from typing import Optional

from app.simulation.scenarios import SCENARIOS


# --------------------------------------------------------------------------- #
# Baseline (normal / healthy) readings
# --------------------------------------------------------------------------- #
def _build_baseline() -> dict:
    return {
        "network": {
            "status": "HEALTHY",
            "available": True,
            "stale": False,
            "throughput_mbps": 385.0,
            "devices": [
                {"name": "dc01-core-sw01", "status": "UP", "latency_ms": 0.4, "loss_pct": 0.0},
                {"name": "dc01-core-sw02", "status": "UP", "latency_ms": 0.5, "loss_pct": 0.0},
                {"name": "dc01-edge-rtr01", "status": "UP", "latency_ms": 2.8, "loss_pct": 0.0},
                {"name": "dc01-edge-rtr02", "status": "UP", "latency_ms": 2.4, "loss_pct": 0.0},
            ],
        },
        "application": {
            "status": "HEALTHY",
            "available": True,
            "stale": False,
            "services": [
                {"name": "api-gateway", "status": "UP", "response_time_ms": 42.0, "error_rate_pct": 0.12},
                {"name": "auth-service", "status": "UP", "response_time_ms": 28.0, "error_rate_pct": 0.05},
                {"name": "checkout-service", "status": "UP", "response_time_ms": 186.0, "error_rate_pct": 0.31},
                {"name": "orders-service", "status": "UP", "response_time_ms": 145.0, "error_rate_pct": 0.24},
                {"name": "search-service", "status": "UP", "response_time_ms": 67.0, "error_rate_pct": 0.08},
                {"name": "payments-service", "status": "UP", "response_time_ms": 210.0, "error_rate_pct": 0.19},
            ],
            "queue": {"depth": 47, "consumers": 8, "lag": 1},
        },
        "facility": {
            "status": "HEALTHY",
            "available": True,
            "stale": False,
            "alarms": [],
            "temperature_c": 23.2,
            "humidity_pct": 51.0,
            "power_load_kw": 28.4,
            "ups_status": "ONLINE",
            "ups_battery_pct": 100.0,
            "hvac_status": "RUNNING",
        },
        "iot": {
            "status": "HEALTHY",
            "available": True,
            "stale": False,
            "sensors": [
                {"name": "dc01-rack-a01-inlet-temp", "value": 24.3, "unit": "C", "status": "OK"},
                {"name": "dc01-rack-a02-inlet-temp", "value": 24.6, "unit": "C", "status": "OK"},
                {"name": "dc01-hall-temp", "value": 23.5, "unit": "C", "status": "OK"},
                {"name": "dc01-hall-humidity", "value": 52.0, "unit": "%", "status": "OK"},
                {"name": "dc01-water-leak", "value": 0, "unit": "bool", "status": "NORMAL"},
                {"name": "hvac-a-fan-rpm", "value": 1450, "unit": "rpm", "status": "NORMAL"},
                {"name": "dc01-ups-load", "value": 44.0, "unit": "%", "status": "OK"},
            ],
        },
    }


# --------------------------------------------------------------------------- #
# Scenario effects. `factor` scales degradation towards baseline during recovery.
# --------------------------------------------------------------------------- #
def _apply_cooling_failure(sources, factor):
    f = factor
    app = sources["application"]
    for svc in app["services"]:
        svc["response_time_ms"] = _round(svc["response_time_ms"] * (1 + 0.30 * f), 1)
        svc["error_rate_pct"] = _round(svc["error_rate_pct"] + 0.9 * f, 2)

    fac = sources["facility"]
    fac["temperature_c"] = _round(23.2 + 11.0 * f, 1)
    fac["humidity_pct"] = _round(51 + 14 * f, 1)
    fac["hvac_status"] = "FAULT" if f > 0.5 else "RUNNING"
    fac["alarms"] = (
        [
            {"name": "HVAC FAULT", "severity": "HIGH", "detail": "CRAC unit A compressor offline"},
            {"name": "RACK TEMP HIGH", "severity": "MEDIUM", "detail": "Rack A01 inlet above threshold"},
        ]
        if f > 0.2
        else []
    )
    fac["status"] = "DEGRADED"

    iot = sources["iot"]
    for s in iot["sensors"]:
        if s["name"] == "dc01-rack-a01-inlet-temp":
            s["value"] = _round(24.3 + 12.0 * f, 1)
        elif s["name"] == "dc01-rack-a02-inlet-temp":
            s["value"] = _round(24.6 + 11.0 * f, 1)
        elif s["name"] == "dc01-hall-temp":
            s["value"] = _round(23.5 + 9.0 * f, 1)
        elif s["name"] == "dc01-hall-humidity":
            s["value"] = _round(52 + 14 * f, 1)
        elif s["name"] == "hvac-a-fan-rpm":
            s["value"] = int(1450 + 2600 * f)
        elif s["name"] == "dc01-ups-load":
            s["value"] = _round(44 + 5 * f, 1)
        if s["name"].endswith("-temp") and f > 0.5:
            s["status"] = "CRITICAL"


def _apply_network_fault(sources, factor):
    f = factor
    net = sources["network"]
    net["devices"][0]["latency_ms"] = _round(0.4 + 72 * f, 1)
    net["devices"][0]["loss_pct"] = _round(0.0 + 4.2 * f, 2)
    net["devices"][0]["status"] = "DEGRADED" if f > 0.3 else "UP"
    net["devices"][2]["latency_ms"] = _round(2.8 + 88 * f, 1)
    net["devices"][2]["loss_pct"] = _round(0.0 + 6.1 * f, 2)
    net["devices"][2]["status"] = "DEGRADED" if f > 0.3 else "UP"
    net["throughput_mbps"] = _round(385 * (1 - 0.62 * f), 0)
    net["status"] = "CRITICAL" if f > 0.6 else ("DEGRADED" if f > 0.2 else "HEALTHY")

    app = sources["application"]
    for svc in app["services"]:
        svc["response_time_ms"] = _round(svc["response_time_ms"] * (1 + 1.4 * f), 1)
        svc["error_rate_pct"] = _round(svc["error_rate_pct"] + 4.5 * f, 2)
    app["services"][0]["status"] = "DEGRADED" if f > 0.2 else "UP"
    app["services"][4]["status"] = "DEGRADED" if f > 0.3 else "UP"


def _apply_app_deployment(sources, factor):
    f = factor
    app = sources["application"]
    svc = {s["name"]: s for s in app["services"]}
    svc["checkout-service"]["response_time_ms"] = _round(186 + 820 * f, 1)
    svc["checkout-service"]["error_rate_pct"] = _round(0.31 + 17.5 * f, 2)
    svc["checkout-service"]["status"] = "CRITICAL" if f > 0.3 else ("DEGRADED" if f > 0.1 else "UP")
    svc["orders-service"]["response_time_ms"] = _round(145 + 390 * f, 1)
    svc["orders-service"]["error_rate_pct"] = _round(0.24 + 8.5 * f, 2)
    svc["orders-service"]["status"] = "DEGRADED" if f > 0.2 else "UP"
    svc["api-gateway"]["response_time_ms"] = _round(42 + 210 * f, 1)
    svc["api-gateway"]["error_rate_pct"] = _round(0.12 + 3.8 * f, 2)
    svc["api-gateway"]["status"] = "DEGRADED" if f > 0.3 else "UP"

    net = sources["network"]
    net["throughput_mbps"] = _round(385 * (1 + 0.10 * f), 0)


def _apply_power_ups(sources, factor):
    f = factor
    fac = sources["facility"]
    fac["ups_status"] = "ON_BATTERY" if f > 0.2 else "ONLINE"
    fac["ups_battery_pct"] = _round(100 - 72 * f, 1)
    fac["power_load_kw"] = _round(28.4 + 36 * f, 1)
    fac["temperature_c"] = _round(23.2 + 3.5 * f, 1)
    fac["alarms"] = (
        [
            {"name": "POWER: MAIN FEED LOST", "severity": "HIGH", "detail": "Utility feed A absent"},
            {"name": "UPS ON BATTERY", "severity": "HIGH", "detail": "Load transferred to battery"},
        ]
        if f > 0.2
        else []
    )
    fac["status"] = "CRITICAL" if f > 0.5 else ("DEGRADED" if f > 0.2 else "HEALTHY")

    net = sources["network"]
    for d in net["devices"]:
        d["latency_ms"] = _round(d["latency_ms"] * (1 + 0.7 * f), 1)

    app = sources["application"]
    for svc in app["services"]:
        svc["response_time_ms"] = _round(svc["response_time_ms"] * (1 + 0.7 * f), 1)
        svc["error_rate_pct"] = _round(svc["error_rate_pct"] + 2.0 * f, 2)

    iot = sources["iot"]
    for s in iot["sensors"]:
        if s["name"] == "dc01-ups-load":
            s["value"] = _round(44 + 40 * f, 1)
            s["status"] = "CRITICAL" if f > 0.6 else "OK"
        elif s["name"] == "dc01-hall-temp":
            s["value"] = _round(23.5 + 4 * f, 1)
        elif s["name"] in ("dc01-rack-a01-inlet-temp", "dc01-rack-a02-inlet-temp") and f > 0.7:
            s["status"] = "FLAKY"


def _apply_queue_backlog(sources, factor):
    f = factor
    app = sources["application"]
    app["queue"]["depth"] = int(47 + 12400 * f)
    app["queue"]["lag"] = int(1 + 8200 * f)
    app["queue"]["consumers"] = max(3, int(8 - 5 * f))
    for svc in app["services"]:
        svc["response_time_ms"] = _round(svc["response_time_ms"] * (1 + 1.8 * f), 1)
        svc["error_rate_pct"] = _round(svc["error_rate_pct"] + 5.0 * f, 2)
    app["services"][2]["status"] = "DEGRADED" if f > 0.2 else "UP"
    app["services"][3]["status"] = "DEGRADED" if f > 0.3 else "UP"

    net = sources["network"]
    net["throughput_mbps"] = _round(385 * (1 + 0.18 * f), 0)


def _apply_traffic_spike(sources, factor):
    f = factor
    net = sources["network"]
    net["throughput_mbps"] = _round(385 + 2800 * f, 0)
    for i, d in enumerate(net["devices"]):
        if i >= 2:  # edge routers
            d["latency_ms"] = _round(d["latency_ms"] * (1 + 2.2 * f), 1)
            d["loss_pct"] = _round(0.0 + 2.6 * f, 2)
            d["status"] = "DEGRADED" if f > 0.3 else "UP"
    net["status"] = "DEGRADED" if f > 0.3 else "HEALTHY"

    app = sources["application"]
    for svc in app["services"]:
        svc["response_time_ms"] = _round(svc["response_time_ms"] * (1 + 2.2 * f), 1)
        svc["error_rate_pct"] = _round(svc["error_rate_pct"] + 6.5 * f, 2)
    app["services"][0]["status"] = "DEGRADED" if f > 0.2 else "UP"
    app["services"][1]["status"] = "DEGRADED" if f > 0.4 else "UP"

    fac = sources["facility"]
    fac["power_load_kw"] = _round(28.4 + 10 * f, 1)
    iot = sources["iot"]
    for s in iot["sensors"]:
        if s["name"] == "dc01-ups-load":
            s["value"] = _round(44 + 8 * f, 1)


_EFFECTS = {
    "cooling_failure": _apply_cooling_failure,
    "network_device_fault": _apply_network_fault,
    "application_deployment_issue": _apply_app_deployment,
    "power_ups_issue": _apply_power_ups,
    "message_queue_worker_backlog": _apply_queue_backlog,
    "noisy_client_traffic_spike": _apply_traffic_spike,
}


# --------------------------------------------------------------------------- #
# Missing / stale handling
# --------------------------------------------------------------------------- #
def _apply_unavailability(sources, missing, stale, missing_list, stale_list):
    for key in ("network", "application", "facility", "iot"):
        block = sources[key]
        if key in stale:
            block["stale"] = True
            block["stale_for_s"] = 900
            stale_list.append({"source": key, "stale_for_s": 900})

        if key in missing:
            block["available"] = False
            block["status"] = "OFFLINE"
            missing_list.append(key)
            if key == "network":
                for d in block["devices"]:
                    d["status"] = "OFFLINE"
                    d["latency_ms"] = None
                    d["loss_pct"] = None
                block["throughput_mbps"] = None
            elif key == "application":
                for s in block["services"]:
                    s["status"] = "OFFLINE"
                    s["response_time_ms"] = None
                    s["error_rate_pct"] = None
                block["queue"] = {"depth": None, "consumers": None, "lag": None}
            elif key == "facility":
                block["alarms"] = []
                block["temperature_c"] = None
                block["humidity_pct"] = None
                block["power_load_kw"] = None
                block["ups_status"] = "UNKNOWN"
                block["ups_battery_pct"] = None
                block["hvac_status"] = "UNKNOWN"
            elif key == "iot":
                for s in block["sensors"]:
                    s["value"] = None
                    s["status"] = "OFFLINE"


# --------------------------------------------------------------------------- #
# Status derivation + jitter
# --------------------------------------------------------------------------- #
def _derive_statuses(sources):
    net = sources["network"]
    if net.get("available") is False:
        net["status"] = "OFFLINE"
    else:
        worst = max((d["status"] for d in net["devices"]), default="UP")
        max_loss = max((d["loss_pct"] or 0 for d in net["devices"]), default=0)
        max_lat = max((d["latency_ms"] or 0 for d in net["devices"]), default=0)
        if worst == "DEGRADED" or max_loss > 1.0 or max_lat > 50:
            net["status"] = "DEGRADED"
        else:
            net["status"] = "HEALTHY"

    app = sources["application"]
    if app.get("available") is False:
        app["status"] = "OFFLINE"
    else:
        statuses = [s["status"] for s in app["services"]]
        if "CRITICAL" in statuses:
            app["status"] = "CRITICAL"
        elif "DEGRADED" in statuses or max(s["error_rate_pct"] for s in app["services"]) > 3:
            app["status"] = "DEGRADED"
        else:
            app["status"] = "HEALTHY"

    fac = sources["facility"]
    if fac.get("available") is False:
        fac["status"] = "OFFLINE"
    else:
        sev = [a["severity"] for a in fac["alarms"]]
        if "HIGH" in sev or fac["ups_status"] == "ON_BATTERY":
            fac["status"] = "CRITICAL"
        elif fac["alarms"] or (fac["temperature_c"] or 0) >= 27:
            fac["status"] = "DEGRADED"
        else:
            fac["status"] = "HEALTHY"

    iot = sources["iot"]
    if iot.get("available") is False:
        iot["status"] = "OFFLINE"
    else:
        if any(s["status"] == "CRITICAL" for s in iot["sensors"]):
            iot["status"] = "CRITICAL"
        elif any(s["status"] in ("FLAKY", "OFFLINE") for s in iot["sensors"]):
            iot["status"] = "DEGRADED"
        else:
            iot["status"] = "HEALTHY"


def _jitter(value, amount):
    if value is None:
        return None
    return _round(value + random.uniform(-amount, amount), 1)


def _add_jitter(sources):
    net = sources["network"]
    if net.get("throughput_mbps") is not None:
        net["throughput_mbps"] = _round(max(1, _jitter(net["throughput_mbps"], net["throughput_mbps"] * 0.04)), 0)
    for d in net["devices"]:
        if d["latency_ms"] is not None:
            d["latency_ms"] = _round(max(0.3, _jitter(d["latency_ms"], d["latency_ms"] * 0.08 + 0.2)), 1)
    for s in sources["application"]["services"]:
        if s["response_time_ms"] is not None:
            s["response_time_ms"] = _round(max(10, _jitter(s["response_time_ms"], s["response_time_ms"] * 0.06)), 1)
    q = sources["application"].get("queue") or {}
    if q.get("depth") is not None:
        q["depth"] = max(0, int(_jitter(q["depth"], max(2, q["depth"] * 0.05))))
    if q.get("lag") is not None:
        q["lag"] = max(0, int(_jitter(q["lag"], max(1, q["lag"] * 0.10))))
    fac = sources["facility"]
    if fac["temperature_c"] is not None:
        fac["temperature_c"] = _round(_jitter(fac["temperature_c"], 0.2), 1)
    if fac["humidity_pct"] is not None:
        fac["humidity_pct"] = _round(_jitter(fac["humidity_pct"], 1.0), 1)
    if fac["power_load_kw"] is not None:
        fac["power_load_kw"] = _round(_jitter(fac["power_load_kw"], 0.8), 1)
    if fac["ups_battery_pct"] is not None:
        fac["ups_battery_pct"] = _round(max(0, min(100, _jitter(fac["ups_battery_pct"], 0.3))), 1)
    iot = sources["iot"]
    for s in iot["sensors"]:
        if isinstance(s["value"], (int, float)) and s["status"] not in ("OFFLINE",):
            if s.get("unit") == "bool":
                continue
            s["value"] = _round(_jitter(s["value"], abs(s["value"]) * 0.03 + 0.2), 1)


def _round(value, ndigits=1):
    return round(float(value), ndigits)


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
def build_telemetry(scenario_id: Optional[str], factor: float = 1.0,
                    missing: Optional[list] = None, stale: Optional[list] = None) -> dict:
    """Return a full telemetry payload.

    scenario_id None => healthy baseline. Otherwise degraded, scaled by factor
    (0..1) where factor decays during recovery. missing/stale are source keys
    from simulation.scenarios.TELEMETRY_SOURCES.
    """
    sources = _build_baseline()
    scenario = SCENARIOS.get(scenario_id) if scenario_id else None
    if scenario:
        effect = _EFFECTS.get(scenario_id)
        if effect:
            effect(sources, max(0.0, min(1.0, factor)))

    missing = missing or []
    stale = stale or []
    missing_list = []
    stale_list = []
    _apply_unavailability(sources, missing, stale, missing_list, stale_list)
    _add_jitter(sources)
    _derive_statuses(sources)

    return {
        "sources": sources,
        "missing_sources": missing_list,
        "stale_sources": stale_list,
    }
