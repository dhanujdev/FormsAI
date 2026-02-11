"""Housing Grant AI Copilot – API routes.

Suggest endpoints call Claude with REAL document content.
Refuses to suggest if no documents are uploaded.
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException

from app.housing_grant_models import (
    AuditFlag,
    AuditRequest,
    AuditResponse,
    Citation,
    DocumentCreate,
    DocumentPublic,
    DocumentsPublic,
    FlagItem,
    SuggestAllRequest,
    SuggestAllResponse,
    SuggestRequest,
    SuggestResponse,
)
from app.llm_service import (
    FORM_SCHEMA,
    is_llm_available,
    suggest_all_with_llm,
    suggest_with_llm,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/housing-grant", tags=["housing-grant"])


# ─── In-memory document store ───────────────────────────────────────

_docs_store: dict[str, list[DocumentPublic]] = {}


def _label_confidence(c: float) -> str:
    if c >= 0.8:
        return "High"
    if c >= 0.5:
        return "Medium"
    if c >= 0.25:
        return "Low"
    return "Very Low"


def _parse_money(v: str | None) -> float | None:
    if not v:
        return None
    s = v.replace(",", "").replace("$", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


# ─── Document endpoints ─────────────────────────────────────────────


@router.post("/documents/upload", response_model=DocumentPublic)
def upload_document(body: DocumentCreate) -> Any:
    """Create a document record (in-memory demo store)."""
    doc_id = f"doc_{uuid.uuid4().hex[:8]}"
    doc = DocumentPublic(
        id=doc_id,
        filename=body.filename,
        doc_type=body.doc_type,
        status="Ready",
        pages=3 if body.doc_type == "lease" else 1,
        badge="good",
    )
    _docs_store.setdefault("default", []).append(doc)
    return doc


@router.get("/documents", response_model=DocumentsPublic)
def list_documents() -> Any:
    """List all documents for current user."""
    docs = _docs_store.get("default", [])
    return DocumentsPublic(data=docs, count=len(docs))


@router.delete("/documents/{doc_id}")
def delete_document(doc_id: str) -> dict[str, str]:
    """Delete a document."""
    docs = _docs_store.get("default", [])
    _docs_store["default"] = [d for d in docs if d.id != doc_id]
    return {"message": "Document deleted"}


# ─── Suggest endpoints (Claude + real documents) ────────────────────


@router.post("/suggest", response_model=SuggestResponse)
async def suggest_field(body: SuggestRequest) -> Any:
    """Suggest a value for a single field by extracting from uploaded documents.

    Requires ANTHROPIC_API_KEY and at least one document with content.
    """
    if not is_llm_available():
        raise HTTPException(
            status_code=503,
            detail="LLM not configured. Set ANTHROPIC_API_KEY in .env to enable suggestions.",
        )

    # Require actual document content
    if not body.doc_contents:
        raise HTTPException(
            status_code=400,
            detail="No documents provided. Upload documents first, then click Suggest to extract values from them.",
        )

    # Pass document content blocks to LLM
    # Convert Pydantic models to dicts for the service
    doc_dicts = [d.model_dump() for d in body.doc_contents]

    try:
        result = await suggest_with_llm(
            field_id=body.field_id,
            form_data=body.form_data,
            doc_contents=doc_dicts,
        )
        return SuggestResponse(
            field_id=result["field_id"],
            suggested_value=result["suggested_value"],
            confidence=result["confidence"],
            confidenceLabel=result.get("confidenceLabel", _label_confidence(result["confidence"])),
            rationale=result["rationale"],
            citations=[Citation(**c) for c in result.get("citations", [])],
            flags=[FlagItem(**f) for f in result.get("flags", [])],
            model=result.get("model", "claude"),
            usage=result.get("usage", {"input_tokens": 0, "output_tokens": 0}),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Claude suggest failed for field %s", body.field_id)
        raise HTTPException(status_code=500, detail=f"LLM error: {e}") from e


@router.post("/suggest-all", response_model=SuggestAllResponse)
async def suggest_all_fields(body: SuggestAllRequest) -> Any:
    """Suggest values for all fields by extracting from uploaded documents.

    Requires ANTHROPIC_API_KEY and at least one document with content.
    """
    if not is_llm_available():
        raise HTTPException(
            status_code=503,
            detail="LLM not configured. Set ANTHROPIC_API_KEY in .env to enable suggestions.",
        )

    # Require actual document content
    if not body.doc_contents:
        raise HTTPException(
            status_code=400,
            detail="No documents provided. Upload documents first, then click Suggest All to extract values from them.",
        )

    # Pass document content blocks to LLM
    doc_dicts = [d.model_dump() for d in body.doc_contents]

    try:
        results = await suggest_all_with_llm(
            form_data=body.form_data,
            doc_contents=doc_dicts,
        )
        suggestions = []
        for r in results:
            suggestions.append(SuggestResponse(
                field_id=r["field_id"],
                suggested_value=r["suggested_value"],
                confidence=r["confidence"],
                confidenceLabel=r.get("confidenceLabel", _label_confidence(r["confidence"])),
                rationale=r["rationale"],
                citations=[Citation(**c) for c in r.get("citations", [])],
                flags=[FlagItem(**f) for f in r.get("flags", [])],
                model=r.get("model", "claude"),
                usage=r.get("usage", {"input_tokens": 0, "output_tokens": 0}),
            ))
        return SuggestAllResponse(suggestions=suggestions)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Claude suggest-all failed")
        raise HTTPException(status_code=500, detail=f"LLM error: {e}") from e


# ─── Audit endpoint ─────────────────────────────────────────────────


@router.post("/preview-audit", response_model=AuditResponse)
def preview_audit(body: AuditRequest) -> Any:
    """Run deterministic audit checks on form data."""
    flags: list[AuditFlag] = []
    form = body.form_data
    meta = body.field_meta

    # Required fields
    for f in FORM_SCHEMA:
        fid = f["id"]
        val = form.get(fid, "").strip()
        if f["required"] and not val:
            flags.append(AuditFlag(
                severity="BLOCKER",
                code="REQUIRED_MISSING",
                field_id=fid,
                message=f"{f['label']} is required.",
                fix="Fill this field (use Suggest if evidence is available).",
            ))

    # State format
    state_val = form.get("state", "").strip()
    if state_val and len(state_val) != 2:
        flags.append(AuditFlag(
            severity="WARNING", code="INVALID_STATE", field_id="state",
            message="State should be 2 letters.", fix="Use 2-letter state code.",
        ))

    # ZIP format
    zip_val = form.get("zip", "").strip()
    if zip_val and not re.match(r"^\d{5}(-\d{4})?$", zip_val):
        flags.append(AuditFlag(
            severity="WARNING", code="INVALID_ZIP", field_id="zip",
            message="ZIP code format looks wrong.", fix="Use 5-digit ZIP (or ZIP+4).",
        ))

    # Evidence checks
    evidence_fields = [f for f in FORM_SCHEMA if f.get("evidence")]
    grounded = 0
    for f in evidence_fields:
        fid = f["id"]
        field_meta = meta.get(fid, {})
        has_cites = bool(field_meta.get("citations"))
        if has_cites:
            grounded += 1
        filled = bool(form.get(fid, "").strip())
        if filled and not has_cites:
            flags.append(AuditFlag(
                severity="BLOCKER", code="MISSING_EVIDENCE_REQUIRED", field_id=fid,
                message=f"{f['label']} filled but has no evidence.",
                fix=f"Upload docs ({', '.join(f.get('docTypes', []))}) then re-run Suggest.",
            ))

    # Accommodation length
    acc = form.get("requested_accommodation", "").strip()
    if acc and len(acc) < 120:
        flags.append(AuditFlag(
            severity="WARNING", code="ACCOMMODATION_TOO_SHORT",
            field_id="requested_accommodation",
            message="Description may be too brief.",
            fix="Add what you need, why, and how it impacts housing access.",
        ))

    # Rent/income ratio
    rent = _parse_money(form.get("monthly_rent"))
    income = _parse_money(form.get("monthly_gross_income"))
    if rent and income and income > 0 and rent / income > 0.8:
        flags.append(AuditFlag(
            severity="INFO", code="RENT_TO_INCOME_HIGH", field_id="monthly_rent",
            message="Rent-to-income ratio appears high.",
            fix="Ensure values are correct and supported by docs.",
        ))

    blockers = sum(1 for f in flags if f.severity == "BLOCKER")
    warnings = sum(1 for f in flags if f.severity == "WARNING")
    infos = sum(1 for f in flags if f.severity == "INFO")
    doc_count = len(_docs_store.get("default", []))
    risk = min(100, blockers * 22 + warnings * 10 + infos * 3 + (18 if doc_count == 0 else 0))
    cov = round((grounded / len(evidence_fields)) * 100) if evidence_fields else 0

    return AuditResponse(
        flags=flags, blockers=blockers, warnings=warnings, infos=infos,
        risk=risk, coveragePct=cov,
    )
