"""Anthropic-backed suggest services for Housing Grant."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

FORM_SCHEMA: list[dict[str, Any]] = [
    {"id": "full_name", "label": "Full legal name", "required": True, "evidence": True, "docTypes": ["lease", "id"]},
    {"id": "dob", "label": "Date of birth", "required": True, "evidence": True, "docTypes": ["id"]},
    {"id": "phone", "label": "Phone number", "required": True, "evidence": False},
    {"id": "email", "label": "Email", "required": True, "evidence": False},
    {"id": "address_line1", "label": "Street address", "required": True, "evidence": True, "docTypes": ["lease", "utility_bill"]},
    {"id": "city", "label": "City", "required": True, "evidence": True, "docTypes": ["lease", "utility_bill"]},
    {"id": "state", "label": "State (2-letter)", "required": True, "evidence": True, "docTypes": ["lease", "utility_bill"]},
    {"id": "zip", "label": "ZIP code", "required": True, "evidence": True, "docTypes": ["lease", "utility_bill"]},
    {"id": "household_size", "label": "Household size", "required": True, "evidence": False},
    {"id": "landlord_name", "label": "Landlord name", "required": True, "evidence": True, "docTypes": ["lease", "landlord_letter"]},
    {"id": "landlord_contact", "label": "Landlord contact", "required": True, "evidence": True, "docTypes": ["lease", "landlord_letter"]},
    {"id": "monthly_rent", "label": "Monthly rent (USD)", "required": True, "evidence": True, "docTypes": ["lease", "rent_ledger"]},
    {"id": "employer_name", "label": "Employer name", "required": False, "evidence": True, "docTypes": ["paystub", "income_verification"]},
    {"id": "monthly_gross_income", "label": "Monthly gross income (USD)", "required": True, "evidence": True, "docTypes": ["paystub", "income_verification"]},
    {"id": "requested_accommodation", "label": "Requested accommodation", "required": True, "evidence": True, "docTypes": ["provider_letter"]},
]

FIELD_MAP = {field["id"]: field for field in FORM_SCHEMA}

SYSTEM_PROMPT = """You are a housing grant form assistant.
Return ONLY valid JSON with keys:
field_id, suggested_value, confidence, rationale, citations, flags.
Rules:
- Use only provided evidence snippets.
- If evidence is insufficient, keep suggested_value as empty string and add a warning flag.
- confidence must be between 0 and 1.
- citations must reference provided chunk IDs when possible.
"""


def is_llm_available() -> bool:
    if not settings.ANTHROPIC_API_KEY:
        return False
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return True


def _parse_json_or_raise(raw: str) -> Any:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text[:-3].strip()
    return json.loads(text)


def _label_confidence(confidence: float) -> str:
    if confidence >= 0.8:
        return "High"
    if confidence >= 0.5:
        return "Medium"
    if confidence > 0:
        return "Low"
    return "Very Low"


def _build_user_prompt(*, field_id: str, form_data: dict[str, str], evidence_chunks: list[dict[str, Any]]) -> str:
    field = FIELD_MAP[field_id]
    return "\n".join(
        [
            f"Field: {field['label']} ({field_id})",
            f"Required: {field['required']}",
            "Current form data:",
            json.dumps(form_data, indent=2),
            "Evidence chunks (ordered by relevance):",
            json.dumps(evidence_chunks, indent=2),
            "Return one JSON object only.",
        ]
    )


def _normalize_result(*, field_id: str, result: dict[str, Any]) -> dict[str, Any]:
    result.setdefault("field_id", field_id)
    result.setdefault("suggested_value", "")
    result.setdefault("confidence", 0.0)
    result.setdefault("rationale", "")
    result.setdefault("citations", [])
    result.setdefault("flags", [])

    if not isinstance(result["confidence"], (float, int)):
        result["confidence"] = 0.0
    result["confidence"] = max(0.0, min(float(result["confidence"]), 1.0))
    result["confidenceLabel"] = _label_confidence(result["confidence"])
    return result


async def suggest_with_llm(
    *,
    field_id: str,
    form_data: dict[str, str],
    evidence_chunks: list[dict[str, Any]],
) -> dict[str, Any]:
    if not settings.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY not configured")

    import anthropic

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    prompt = _build_user_prompt(field_id=field_id, form_data=form_data, evidence_chunks=evidence_chunks)

    try:
        message = client.messages.create(
            model=settings.HOUSING_LLM_MODEL,
            max_tokens=900,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": [{"type": "text", "text": prompt}]}],
        )
    except Exception as exc:
        raise RuntimeError(f"anthropic request failed: {exc}") from exc

    text = ""
    for block in message.content:
        block_text = getattr(block, "text", None)
        if isinstance(block_text, str) and block_text.strip():
            text = block_text.strip()
            break
    if not text:
        raise RuntimeError("LLM response contained no text payload")

    try:
        parsed = _parse_json_or_raise(text)
        if not isinstance(parsed, dict):
            raise ValueError("LLM output was not a JSON object")
    except Exception as exc:
        raise RuntimeError(f"invalid structured output from LLM: {exc}") from exc

    normalized = _normalize_result(field_id=field_id, result=parsed)
    normalized["model"] = message.model
    normalized["usage"] = {
        "input_tokens": message.usage.input_tokens,
        "output_tokens": message.usage.output_tokens,
    }
    return normalized


async def suggest_all_with_llm(
    *,
    form_data: dict[str, str],
    evidence_by_field: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    suggestions: list[dict[str, Any]] = []
    for field in FORM_SCHEMA:
        result = await suggest_with_llm(
            field_id=field["id"],
            form_data=form_data,
            evidence_chunks=evidence_by_field.get(field["id"], []),
        )
        suggestions.append(result)
    return suggestions
