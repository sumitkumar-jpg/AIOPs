"""AI diagnosis orchestrator.

Tries the Groq LLM first; on any failure (missing key, timeout, network, bad
JSON, out-of-set output) it safely falls back to the deterministic rule-based
diagnosis and reports that AI was unavailable. Never crashes the app, never
exposes the API key.
"""

import json
import re

from app.ai.fallback import fallback_diagnosis
from app.ai.prompts import SYSTEM_PROMPT, build_user_prompt
from app.ai.validation import validate_diagnosis
from app.config import AI_AVAILABLE, AI_TIMEOUT, GROQ_API_KEY, GROQ_MODEL
from app.playbooks import PLAYBOOKS, ROOT_CAUSES


class _GroqUnavailable(Exception):
    pass


def _parse_json(text: str) -> dict:
    """Robustly extract the first JSON object from the model output."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("no JSON object in model output")
    return json.loads(cleaned[start : end + 1])


def _call_groq(messages: list) -> str:
    if not AI_AVAILABLE or not GROQ_API_KEY:
        raise _GroqUnavailable("GROQ_API_KEY is not configured")

    try:
        from groq import Groq
    except Exception as exc:  # pragma: no cover
        raise _GroqUnavailable(f"groq SDK import failed: {exc}")

    client = Groq(api_key=GROQ_API_KEY)
    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=messages,
        temperature=0.2,
        max_tokens=800,
        timeout=AI_TIMEOUT,
    )
    return response.choices[0].message.content


def diagnose(context: dict):
    """Return (diagnosis_dict, engine, note)."""
    context_with_allowed = {
        **context,
        "allowed_root_causes": ROOT_CAUSES,
        "allowed_playbooks": PLAYBOOKS,
    }

    if AI_AVAILABLE:
        try:
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(context_with_allowed)},
            ]
            raw = _call_groq(messages)
            parsed = _parse_json(raw)
            validated = validate_diagnosis(parsed, context)
            note = None
            return validated, "groq", note
        except Exception as exc:
            # Record why the fallback was used (never leaks the key value).
            note = f"Groq unavailable; used rule-based fallback. Reason: {type(exc).__name__}"
    else:
        note = "GROQ_API_KEY not set; used rule-based fallback diagnosis."

    fallback = fallback_diagnosis(context)
    validated = validate_diagnosis(fallback, context)
    return validated, "fallback", note
