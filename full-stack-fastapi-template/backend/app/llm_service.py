"""
Housing Grant LLM Service — Anthropic Claude integration.

Calls Claude to generate field suggestions for housing grant forms.
Claude generates reasonable values based on context, and explicitly
reports confidence levels based on available evidence.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

# ── Form schema (same 15 fields the frontend knows about) ──────

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

FIELD_MAP = {f["id"]: f for f in FORM_SCHEMA}

# ── System prompt ───────────────────────────────────────────────

SYSTEM_PROMPT = """You are an AI copilot that helps fill housing grant and reasonable accommodation application forms.

Your job: Given the field being requested, any uploaded document context, and any already-filled fields, produce a suggested value for the field.

RULES:
1. ALWAYS return a non-empty "suggested_value". If you have document evidence, extract directly. If not, generate a realistic, plausible value for a housing grant application.
2. Set confidence honestly:
   - 0.85-1.0: Value directly extracted from a document with exact match
   - 0.6-0.84: Strong evidence or inference from documents
   - 0.3-0.59: Partial evidence, reasonable inference, or generated from context of other fields
   - 0.05-0.29: No direct evidence — value is a plausible placeholder
3. In "rationale", explain where the value came from (document extraction vs. generated).
4. In "citations", include document references only if you actually extracted from a document. Empty array is fine.
5. In "flags", note if the value needs manual verification.

RESPONSE FORMAT — return ONLY valid JSON, no markdown fences:
{
  "field_id": "<field_id>",
  "suggested_value": "<non-empty value>",
  "confidence": <float 0.05-1.0>,
  "rationale": "<brief explanation>",
  "citations": [
    {"doc": "<filename>", "docType": "<type>", "page": "<page>", "chunk": "<chunk_id>", "quote": "<relevant quote>"}
  ],
  "flags": [
    {"code": "<CODE>", "severity": "info|warning|error", "message": "<message>"}
  ]
}"""

SUGGEST_ALL_SYSTEM = """You are an AI copilot that helps fill housing grant and reasonable accommodation application forms.

Given the uploaded documents and any already-filled fields, produce suggested values for ALL fields at once. Return a JSON array of suggestion objects.

RULES:
1. ALWAYS return a non-empty "suggested_value" for EVERY field. If you extract from documents, great. If not, generate realistic plausible values that are internally consistent (e.g. address, city, state, zip should match).
2. Set confidence honestly: 0.85+ for document-extracted, 0.6-0.84 for inferred, 0.3-0.59 for partial evidence, 0.05-0.29 for generated placeholders.
3. Make generated values internally consistent — if you generate a city, the state and ZIP should match.
4. For monetary fields, use realistic dollar amounts.
5. For "requested_accommodation", write a detailed 2-3 sentence request.

RESPONSE FORMAT — return ONLY a valid JSON array, no markdown fences:
[
  {
    "field_id": "<field_id>",
    "suggested_value": "<non-empty value>",
    "confidence": <float>,
    "rationale": "<brief explanation>",
    "citations": [],
    "flags": []
  },
  ...
]"""


def _build_suggest_prompt(
    field_id: str,
    form_data: dict[str, str],
) -> str:
    """Build a user prompt for suggesting a single field."""
    field = FIELD_MAP.get(field_id)
    if not field:
        return f"Suggest a value for field '{field_id}'. Return JSON."

    parts = [
        f"Suggest a value for: **{field['label']}** (field_id: `{field_id}`)",
        f"Required: {'Yes' if field.get('required') else 'No'}",
    ]

    if field.get("docTypes"):
        parts.append(f"Relevant document types: {', '.join(field['docTypes'])}")

    # Include existing form data for context
    filled = {k: v for k, v in form_data.items() if v.strip()}
    if filled:
        parts.append(f"\nAlready-filled fields:\n{json.dumps(filled, indent=2)}")

    parts.append(f"\nReturn JSON for field_id='{field_id}'. The suggested_value MUST be non-empty.")
    return "\n".join(parts)


def _build_suggest_all_prompt(
    form_data: dict[str, str],
) -> str:
    """Build a user prompt for suggesting all fields at once."""
    parts = ["Fill ALL 15 fields of the housing grant form.\n"]
    parts.append("Fields to fill:")
    for f in FORM_SCHEMA:
        existing = form_data.get(f["id"], "").strip()
        status = f" (already filled: {existing})" if existing else ""
        parts.append(f"  - {f['id']}: {f['label']} {'[Required]' if f['required'] else '[Optional]'}{status}")

    filled = {k: v for k, v in form_data.items() if v.strip()}
    if filled:
        parts.append(f"\nAlready-filled fields:\n{json.dumps(filled, indent=2)}")

    parts.append("\nReturn a JSON array with one object per field. Every suggested_value MUST be non-empty.")
    return "\n".join(parts)


def _parse_content_block(doc: dict[str, Any]) -> dict[str, Any]:
    """Convert a document object to a Claude content block (text or image)."""
    content: str = doc.get("content", "")
    filename: str = doc.get("filename", "unknown")
    doc_type: str = doc.get("doc_type", "unknown")

    if content.startswith("data:"):
        try:
            # Format: data:image/png;base64,......
            meta, data = content.split(",", 1)
            media_type = meta.split(":")[1].split(";")[0]
            if not media_type.startswith("image/"):
                # Fallback for non-image data URIs (e.g. PDF if sent as data URI but not supported as image)
                return {
                    "type": "text",
                    "text": f"=== Document: {filename} ({doc_type}) ===\n[Unsupported media type: {media_type}]"
                }
            return {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": data
                }
            }
        except Exception:
            return {
                "type": "text",
                "text": f"=== Document: {filename} ({doc_type}) ===\n[Error parsing image data]"
            }
    else:
        # Standard text content
        return {
            "type": "text",
            "text": f"=== Document: {filename} ({doc_type}) ===\n{content}"
        }


def _parse_json(raw: str) -> Any:
    """Parse JSON from Claude response, stripping markdown fences if present."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text[:-3].strip()
    return json.loads(text)


def _label_confidence(conf: float) -> str:
    if conf >= 0.8:
        return "High"
    if conf >= 0.5:
        return "Medium"
    if conf >= 0.25:
        return "Low"
    return "Very Low"


async def suggest_with_llm(
    field_id: str,
    form_data: dict[str, str],
    doc_contents: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Call Claude to suggest a value for a single field."""
    if not settings.ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY not configured")

    import anthropic

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    # Build prompt content blocks
    messages_content: list[dict[str, Any]] = []
    
    # 1. Instructions & Form Context
    prompt_text = _build_suggest_prompt(field_id, form_data)
    messages_content.append({"type": "text", "text": prompt_text})

    # 2. Document Evidence (Text or Images)
    if doc_contents:
        messages_content.append({"type": "text", "text": "\nUploaded documents (evidence):"})
        for doc in doc_contents:
            messages_content.append(_parse_content_block(doc))
    else:
        messages_content.append({"type": "text", "text": "\nNo documents uploaded yet — generate a plausible value."})

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": messages_content}],
    )

    raw_text = message.content[0].text.strip()

    try:
        result = _parse_json(raw_text)
    except json.JSONDecodeError:
        logger.warning("LLM returned non-JSON: %s", raw_text[:200])
        result = {
            "field_id": field_id,
            "suggested_value": raw_text[:100],  # Use raw text
            "confidence": 0.1,
            "rationale": "LLM response could not be parsed as JSON.",
            "citations": [],
            "flags": [{"code": "PARSE_ERROR", "severity": "warning", "message": "Response was not valid JSON"}],
        }

    # Ensure required fields
    result.setdefault("field_id", field_id)
    result.setdefault("suggested_value", "")
    result.setdefault("confidence", 0.1)
    result.setdefault("rationale", "")
    result.setdefault("citations", [])
    result.setdefault("flags", [])

    # Add model + usage metadata
    result["model"] = message.model
    result["usage"] = {
        "input_tokens": message.usage.input_tokens,
        "output_tokens": message.usage.output_tokens,
    }
    result["confidenceLabel"] = _label_confidence(result["confidence"])

    return result


async def suggest_all_with_llm(
    form_data: dict[str, str],
    doc_contents: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Call Claude once to suggest all 15 fields in a single request."""
    if not settings.ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY not configured")

    import anthropic

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    # Build prompt content blocks
    messages_content: list[dict[str, Any]] = []

    # 1. Instructions & Form Context
    prompt_text = _build_suggest_all_prompt(form_data)
    messages_content.append({"type": "text", "text": prompt_text})

    # 2. Document Evidence (Text or Images)
    if doc_contents:
        messages_content.append({"type": "text", "text": "\nUploaded documents (evidence):"})
        for doc in doc_contents:
            messages_content.append(_parse_content_block(doc))
    else:
        messages_content.append({"type": "text", "text": "\nNo documents uploaded yet — generate plausible values."})

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        system=SUGGEST_ALL_SYSTEM,
        messages=[{"role": "user", "content": messages_content}],
    )

    raw_text = message.content[0].text.strip()

    try:
        results = _parse_json(raw_text)
        if not isinstance(results, list):
            results = [results]
    except json.JSONDecodeError:
        logger.error("LLM suggest-all returned non-JSON: %s", raw_text[:300])
        return [{
            "field_id": f["id"],
            "suggested_value": "",
            "confidence": 0.0,
            "rationale": "LLM batch response could not be parsed.",
            "citations": [],
            "flags": [{"code": "PARSE_ERROR", "severity": "error", "message": "Batch parse failed"}],
            "model": message.model,
            "usage": {"input_tokens": 0, "output_tokens": 0},
            "confidenceLabel": "None",
        } for f in FORM_SCHEMA]

    # Normalize each result
    for r in results:
        r.setdefault("suggested_value", "")
        r.setdefault("confidence", 0.1)
        r.setdefault("rationale", "")
        r.setdefault("citations", [])
        r.setdefault("flags", [])
        r["model"] = message.model
        r["usage"] = {
            "input_tokens": message.usage.input_tokens // max(len(results), 1),
            "output_tokens": message.usage.output_tokens // max(len(results), 1),
        }
        r["confidenceLabel"] = _label_confidence(r["confidence"])

    return results


def is_llm_available() -> bool:
    """Check if the LLM is configured and available."""
    return bool(settings.ANTHROPIC_API_KEY)
