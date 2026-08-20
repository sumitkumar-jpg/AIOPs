"""Predefined root causes, playbooks and the risk governance policy.

The AI may ONLY choose from these predefined root causes and playbooks.
Risk level is a property of the playbook, not a free-form AI decision.
"""

# --------------------------------------------------------------------------- #
# Root causes (closed set the AI must choose from)
# --------------------------------------------------------------------------- #
ROOT_CAUSES = [
    {
        "id": "cooling_failure",
        "label": "Cooling / HVAC failure",
        "description": "Data-centre or facility cooling has failed, raising rack and hall temperatures.",
    },
    {
        "id": "network_device_fault",
        "label": "Network device fault",
        "description": "A switch/router is degraded or failing, raising latency and packet loss.",
    },
    {
        "id": "application_deployment_issue",
        "label": "Application / deployment problem",
        "description": "A recently deployed service is erroring, raising error rate and response time.",
    },
    {
        "id": "power_ups_issue",
        "label": "Power / UPS problem",
        "description": "Main power feed lost; UPS on battery, load and facility alarms elevated.",
    },
    {
        "id": "message_queue_worker_backlog",
        "label": "Message queue / worker backlog",
        "description": "Consumers are falling behind; queue depth and lag are growing.",
    },
    {
        "id": "noisy_client_traffic_spike",
        "label": "Noisy client / traffic spike",
        "description": "An abnormal burst of client traffic is saturating capacity.",
    },
    {
        "id": "insufficient_data",
        "label": "Insufficient data",
        "description": "Too many sources are missing/stale to confidently identify a root cause.",
    },
]

ROOT_CAUSES_BY_ID = {rc["id"]: rc for rc in ROOT_CAUSES}


# --------------------------------------------------------------------------- #
# Playbooks (closed set, each with a fixed risk level)
# --------------------------------------------------------------------------- #
PLAYBOOKS = [
    {
        "id": "pb_hvac_recovery",
        "title": "Restore facility cooling (HVAC)",
        "risk_level": "LOW",
        "root_cause": "cooling_failure",
        "description": "Ramp up redundant cooling, clear HVAC fault and restore normal temperature set-points. Fully reversible simulated action.",
        "steps": [
            "Acknowledge HVAC fault alarm.",
            "Enable redundant cooling units and increase fan bank speed.",
            "Verify rack/hall temperature returns to set-point.",
        ],
        "affected_sources": ["facility", "iot"],
    },
    {
        "id": "pb_network_failover",
        "title": "Fail over to redundant network path",
        "risk_level": "MEDIUM",
        "root_cause": "network_device_fault",
        "description": "Isolate the degraded device and steer traffic to the redundant path. Short, bounded disruption possible.",
        "steps": [
            "Confirm degraded device via health metrics.",
            "Activate failover to redundant switch/router.",
            "Verify latency and loss recover on primary services.",
        ],
        "affected_sources": ["network", "application"],
    },
    {
        "id": "pb_app_rollback",
        "title": "Roll back application deployment",
        "risk_level": "MEDIUM",
        "root_cause": "application_deployment_issue",
        "description": "Roll the faulty service back to the previous stable build. Brief availability impact during rollback.",
        "steps": [
            "Identify the offending service release.",
            "Roll back to previous stable image.",
            "Verify error rate and response time return to baseline.",
        ],
        "affected_sources": ["application"],
    },
    {
        "id": "pb_power_switchover",
        "title": "Switch to backup power / UPS",
        "risk_level": "HIGH",
        "root_cause": "power_ups_issue",
        "description": "Transfer critical loads to backup power. Facility/power actions require explicit human approval.",
        "steps": [
            "Confirm UPS battery state and remaining runtime.",
            "Transfer critical racks to backup feed.",
            "Verify load rebalances and no further alarms trigger.",
        ],
        "affected_sources": ["facility", "network", "application", "iot"],
    },
    {
        "id": "pb_queue_scale_up",
        "title": "Scale up queue workers",
        "risk_level": "LOW",
        "root_cause": "message_queue_worker_backlog",
        "description": "Add consumer workers to drain the backlog. Reversible simulated action.",
        "steps": [
            "Record current queue depth and consumer lag.",
            "Scale consumer workers up.",
            "Verify queue depth drains toward baseline.",
        ],
        "affected_sources": ["application"],
    },
    {
        "id": "pb_client_throttle",
        "title": "Rate-limit noisy client",
        "risk_level": "MEDIUM",
        "root_cause": "noisy_client_traffic_spike",
        "description": "Apply rate limiting / throttling to the offending client while preserving normal traffic.",
        "steps": [
            "Identify the noisy client from traffic telemetry.",
            "Apply rate limit at the gateway.",
            "Verify throughput normalizes without collateral impact.",
        ],
        "affected_sources": ["network", "application"],
    },
    {
        "id": "pb_observe_and_hold",
        "title": "Observe and hold",
        "risk_level": "LOW",
        "root_cause": "insufficient_data",
        "description": "Take no risky action; continue monitoring until enough data is available.",
        "steps": [
            "Do not execute recovery actions.",
            "Escalate data-source health to operators.",
            "Re-evaluate when sources recover.",
        ],
        "affected_sources": [],
    },
]

PLAYBOOKS_BY_ID = {pb["id"]: pb for pb in PLAYBOOKS}


# --------------------------------------------------------------------------- #
# Risk governance policy
# --------------------------------------------------------------------------- #
RISK_POLICY = {
    "LOW": {
        "label": "LOW",
        "execution": "auto",
        "description": "Safe/reversible simulated actions. The AI may execute automatically.",
    },
    "MEDIUM": {
        "label": "MEDIUM",
        "execution": "approval_required",
        "description": "Moderate blast radius. Human approval is mandatory before execution.",
    },
    "HIGH": {
        "label": "HIGH",
        "execution": "approval_required",
        "description": "Database/facility/power/safety/serious-downtime. Explicit human approval required.",
    },
}


def risk_requires_approval(risk_level: str) -> bool:
    policy = RISK_POLICY.get(risk_level, RISK_POLICY["MEDIUM"])
    return policy["execution"] == "approval_required"
