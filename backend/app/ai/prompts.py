"""LLM prompts for root-cause analysis. Kept simple and explicit."""

import json

SYSTEM_PROMPT = (
    "You are the root-cause analysis engine of a HUMAN-GOVERNED AIOps platform.\n"
    "Strict rules:\n"
    "1. Reason ONLY from the evidence provided in the prompt. NEVER invent readings, "
    "incidents, root causes, playbooks, or actions.\n"
    "2. Choose likely_root_cause STRICTLY from the allowed root causes list.\n"
    "3. Choose recommended_playbook_id STRICTLY from the allowed playbooks list.\n"
    "4. If a telemetry source is missing or stale, say so in reasoning and reduce "
    "your confidence. Never guess values for missing data.\n"
    "5. Historical incidents are supporting context only; the current telemetry "
    "has priority.\n"
    "6. Return ONLY a JSON object with these fields:\n"
    "   {\n"
    '     "likely_root_cause": "<allowed root cause id>",\n'
    '     "confidence": <number 0.0 to 1.0>,\n'
    '     "reasoning": "<3-6 sentences of evidence-based reasoning>",\n'
    '     "recommended_playbook_id": "<allowed playbook id>",\n'
    '     "risk_level": "LOW|MEDIUM|HIGH",\n'
    '     "missing_data_sources": ["<source id>"]\n'
    "   }\n"
    "No markdown, no extra text."
)


def build_user_prompt(context: dict) -> str:
    allowed_root_causes = [rc["id"] for rc in context["allowed_root_causes"]]
    allowed_playbooks = [pb["id"] for pb in context["allowed_playbooks"]]

    return json.dumps(
        {
            "task": "Analyze the current incident and return the structured JSON diagnosis.",
            "allowed_root_causes": allowed_root_causes,
            "allowed_playbooks": allowed_playbooks,
            "risk_policy": {
                "LOW": "auto-execute (safe/reversible)",
                "MEDIUM": "human approval required",
                "HIGH": "explicit human approval required",
            },
            "current_scenario": context["scenario"],
            "current_telemetry": context["telemetry"],
            "missing_sources": context["missing_sources"],
            "stale_sources": context["stale_sources"],
            "historical_similar_incidents": context["historical_incidents"],
        },
        indent=2,
    )
