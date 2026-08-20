"""Scenario definitions.

Each scenario describes a realistic correlated degradation across multiple
telemetry sources plus the expected root cause and recovery playbook.
The AI does not invent the root cause: it reasons from the injected evidence.
"""

SCENARIOS = {
    "cooling_failure": {
        "id": "cooling_failure",
        "name": "Cooling failure / HVAC fault",
        "description": "Chilled-water compressor goes offline. Rack and hall temperatures climb, HVAC reports FAULT and fan banks spin up. Application response degrades slightly as server-room heat rises.",
        "severity": "major",
        "root_cause_id": "cooling_failure",
        "playbook_id": "pb_hvac_recovery",
        "zone": "DC-1",
        "affected_services": ["checkout-service", "orders-service"],
        "affected_devices": ["hvac-a-fan-rpm", "dc01-rack-a01-inlet-temp", "dc01-rack-a02-inlet-temp"],
    },
    "network_device_fault": {
        "id": "network_device_fault",
        "name": "Network device fault",
        "description": "Core switch and edge router develop high latency and packet loss. Application response time and error rate rise because traffic crosses the failing path.",
        "severity": "critical",
        "root_cause_id": "network_device_fault",
        "playbook_id": "pb_network_failover",
        "zone": "DC-1",
        "affected_services": ["api-gateway", "search-service"],
        "affected_devices": ["dc01-core-sw01", "dc01-edge-rtr01"],
    },
    "application_deployment_issue": {
        "id": "application_deployment_issue",
        "name": "Application deployment problem",
        "description": "A faulty release of checkout-service was just deployed. Its error rate and response time spike, and dependent services degrade behind the gateway.",
        "severity": "critical",
        "root_cause_id": "application_deployment_issue",
        "playbook_id": "pb_app_rollback",
        "zone": "APP-FLEET",
        "affected_services": ["checkout-service", "orders-service", "api-gateway"],
        "affected_devices": [],
    },
    "power_ups_issue": {
        "id": "power_ups_issue",
        "name": "Power / UPS problem",
        "description": "Main power feed is lost. UPS drops to battery, battery percentage falls, power load spikes and IoT sensors report flaky availability. Brownouts add latency everywhere.",
        "severity": "critical",
        "root_cause_id": "power_ups_issue",
        "playbook_id": "pb_power_switchover",
        "zone": "DC-1",
        "affected_services": ["api-gateway", "checkout-service"],
        "affected_devices": ["dc01-ups-load", "dc01-hall-temp"],
    },
    "message_queue_worker_backlog": {
        "id": "message_queue_worker_backlog",
        "name": "Message queue / worker backlog",
        "description": "Consumer workers crash in batches; queue depth and consumer lag explode. Downstream services wait on queued work, raising response time and error rate.",
        "severity": "major",
        "root_cause_id": "message_queue_worker_backlog",
        "playbook_id": "pb_queue_scale_up",
        "zone": "APP-FLEET",
        "affected_services": ["checkout-service", "orders-service"],
        "affected_devices": [],
    },
    "noisy_client_traffic_spike": {
        "id": "noisy_client_traffic_spike",
        "name": "Noisy client / traffic spike",
        "description": "A misconfigured client floods the gateway. Throughput spikes far above baseline, latency and loss climb on the edges, and application error rate rises under load.",
        "severity": "major",
        "root_cause_id": "noisy_client_traffic_spike",
        "playbook_id": "pb_client_throttle",
        "zone": "EDGE",
        "affected_services": ["api-gateway", "auth-service"],
        "affected_devices": ["dc01-edge-rtr01", "dc01-edge-rtr02"],
    },
}

SCENARIOS_BY_ID = {sid: s for sid, s in SCENARIOS.items()}

SCENARIO_IDS = list(SCENARIOS.keys())

# Sources that can be marked missing/stale in the admin panel.
TELEMETRY_SOURCES = {
    "network": "Network devices",
    "application": "Application metrics",
    "facility": "Facility monitoring",
    "iot": "IoT sensors",
}
