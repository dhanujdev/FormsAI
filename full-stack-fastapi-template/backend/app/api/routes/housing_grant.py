"""Housing Grant API routes."""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException
from sqlmodel import col, func, select

from app.api.deps import CurrentUser, SessionDep
from app.core.config import settings
from app.housing_grant_db_models import (
    HGAuditReport,
    HGDocument,
    HGFormSubmission,
    HGIngestionJob,
)
from app.housing_grant_ingestion import run_ingestion_job
from app.housing_grant_models import (
    AuditFlag,
    AuditRequest,
    AuditResponse,
    Citation,
    DocumentPublic,
    DocumentsPublic,
    DocumentUploadCompleteRequest,
    DocumentUploadCompleteResponse,
    DocumentUploadInitRequest,
    DocumentUploadInitResponse,
    FlagItem,
    HGDocType,
    HGDocumentStatus,
    HGIngestionJobStatus,
    SubmissionCreateRequest,
    SubmissionPublic,
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
from app.storage import StorageError, get_storage_client
from app.vector_store import search_similar_chunks

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/housing-grant", tags=["housing-grant"])


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _status_badge(status: HGDocumentStatus) -> str:
    if status == HGDocumentStatus.ready:
        return "good"
    if status == HGDocumentStatus.error:
        return "bad"
    if status == HGDocumentStatus.processing:
        return "warn"
    return "info"


def _sanitize_filename(filename: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9._-]", "_", filename)
    return safe[:200] or "document"


def _parse_doc_type(value: str) -> HGDocType:
    try:
        return HGDocType(value)
    except ValueError:
        return HGDocType.other


def _object_key(*, user_id: uuid.UUID, document_id: uuid.UUID, filename: str) -> str:
    return f"{settings.HOUSING_S3_PREFIX}/users/{user_id}/documents/{document_id}/{_sanitize_filename(filename)}"


def _parse_money(value: str | None) -> float | None:
    if not value:
        return None
    normalized = value.replace(",", "").replace("$", "").strip()
    try:
        return float(normalized)
    except ValueError:
        return None


def _require_document_for_user(*, session: SessionDep, current_user: CurrentUser, document_id: uuid.UUID) -> HGDocument:
    document = session.get(HGDocument, document_id)
    if not document or document.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


def _resolve_doc_ids(*, session: SessionDep, current_user: CurrentUser, requested_doc_ids: list[uuid.UUID]) -> list[uuid.UUID]:
    if requested_doc_ids:
        statement = (
            select(HGDocument.id)
            .where(col(HGDocument.user_id) == current_user.id)
            .where(col(HGDocument.status) == HGDocumentStatus.ready)
            .where(col(HGDocument.id).in_(requested_doc_ids))
        )
        doc_ids = list(session.exec(statement).all())
    else:
        statement = (
            select(HGDocument.id)
            .where(col(HGDocument.user_id) == current_user.id)
            .where(col(HGDocument.status) == HGDocumentStatus.ready)
        )
        doc_ids = list(session.exec(statement).all())

    if not doc_ids:
        raise HTTPException(status_code=400, detail="No ready documents available. Upload and process documents first.")
    return doc_ids


def _queue_ingestion_task(
    *,
    background_tasks: BackgroundTasks,
    job_id: uuid.UUID,
    document_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    background_tasks.add_task(
        run_ingestion_job,
        job_id=job_id,
        document_id=document_id,
        user_id=user_id,
    )


@router.post("/documents/upload-url", response_model=DocumentUploadInitResponse)
def create_document_upload_url(
    body: DocumentUploadInitRequest,
    session: SessionDep,
    current_user: CurrentUser,
) -> Any:
    if body.size_bytes > settings.HOUSING_INGESTION_MAX_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"File exceeds max allowed size ({settings.HOUSING_INGESTION_MAX_BYTES} bytes)",
        )

    document_id = uuid.uuid4()
    object_key = _object_key(user_id=current_user.id, document_id=document_id, filename=body.filename)

    try:
        storage = get_storage_client()
        upload = storage.create_presigned_upload(object_key=object_key, content_type=body.content_type)
    except StorageError as exc:
        raise HTTPException(status_code=502, detail=f"Storage error: {exc}") from exc

    document = HGDocument(
        id=document_id,
        user_id=current_user.id,
        filename=body.filename,
        doc_type=body.doc_type.value,
        status=HGDocumentStatus.pending,
        storage_path=object_key,
        content_type=body.content_type,
        size_bytes=body.size_bytes,
        created_at=_utcnow(),
        updated_at=_utcnow(),
    )
    session.add(document)
    session.commit()

    return DocumentUploadInitResponse(
        document_id=document_id,
        object_key=object_key,
        upload_url=upload.upload_url,
        required_headers=upload.required_headers,
        expires_at=upload.expires_at,
    )


@router.post("/documents/{document_id}/complete", response_model=DocumentUploadCompleteResponse)
def complete_document_upload(
    document_id: uuid.UUID,
    body: DocumentUploadCompleteRequest,
    background_tasks: BackgroundTasks,
    session: SessionDep,
    current_user: CurrentUser,
) -> Any:
    document = _require_document_for_user(session=session, current_user=current_user, document_id=document_id)

    try:
        storage = get_storage_client()
        object_meta = storage.head_object(object_key=document.storage_path)
    except StorageError as exc:
        raise HTTPException(status_code=400, detail=f"Uploaded object verification failed: {exc}") from exc

    content_length_value = object_meta.get("ContentLength", 0)
    content_length = int(content_length_value) if isinstance(content_length_value, (int, float, str)) else 0
    if content_length <= 0:
        raise HTTPException(status_code=400, detail="Uploaded object is empty")

    etag = body.etag or str(object_meta.get("ETag", "")).strip('"')
    document.status = HGDocumentStatus.uploaded
    document.size_bytes = content_length
    document.etag = etag or None
    document.updated_at = _utcnow()

    job = HGIngestionJob(
        document_id=document.id,
        user_id=current_user.id,
        status=HGIngestionJobStatus.queued,
        idempotency_key=f"{document.id}:{int(_utcnow().timestamp())}",
        retry_count=0,
        created_at=_utcnow(),
        updated_at=_utcnow(),
    )

    session.add(document)
    session.add(job)
    session.commit()

    _queue_ingestion_task(
        background_tasks=background_tasks,
        job_id=job.id,
        document_id=document.id,
        user_id=current_user.id,
    )

    return DocumentUploadCompleteResponse(document_id=document.id, status=document.status)


@router.get("/documents", response_model=DocumentsPublic)
def list_documents(session: SessionDep, current_user: CurrentUser) -> Any:
    count_statement = (
        select(func.count())
        .select_from(HGDocument)
        .where(HGDocument.user_id == current_user.id)
    )
    count = session.exec(count_statement).one()

    statement = (
        select(HGDocument)
        .where(HGDocument.user_id == current_user.id)
        .order_by(col(HGDocument.created_at).desc())
    )
    docs = session.exec(statement).all()

    return DocumentsPublic(
        data=[
            DocumentPublic(
                id=doc.id,
                filename=doc.filename,
                doc_type=_parse_doc_type(doc.doc_type),
                status=doc.status,
                pages=doc.pages,
                badge=_status_badge(doc.status),
                created_at=doc.created_at,
                updated_at=doc.updated_at,
            )
            for doc in docs
        ],
        count=count,
    )


@router.delete("/documents/{document_id}")
def delete_document(document_id: uuid.UUID, session: SessionDep, current_user: CurrentUser) -> dict[str, str]:
    document = _require_document_for_user(session=session, current_user=current_user, document_id=document_id)

    try:
        storage = get_storage_client()
        storage.delete_object(object_key=document.storage_path)
    except StorageError:
        logger.exception("Storage deletion failed for document %s", document.id)

    session.delete(document)
    session.commit()
    return {"message": "Document deleted"}


def _suggest_field_with_context(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    field_id: str,
    form_data: dict[str, str],
    doc_ids: list[uuid.UUID],
) -> SuggestResponse:
    if field_id not in {f["id"] for f in FORM_SCHEMA}:
        raise HTTPException(status_code=404, detail="Unknown field")

    query = f"{field_id} {FORM_SCHEMA[[f['id'] for f in FORM_SCHEMA].index(field_id)]['label']}"
    evidence_chunks = search_similar_chunks(
        session=session,
        query=query,
        user_id=current_user.id,
        doc_ids=doc_ids,
        top_k=settings.HOUSING_RAG_TOP_K,
    )

    try:
        suggestion = awaitable_to_sync(
            suggest_with_llm(
                field_id=field_id,
                form_data=form_data,
                evidence_chunks=evidence_chunks,
            )
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    citations: list[Citation] = []
    for citation in suggestion.get("citations", []):
        try:
            citations.append(Citation(**citation))
        except Exception:
            logger.debug("Skipping invalid citation payload: %s", citation)

    return SuggestResponse(
        field_id=suggestion["field_id"],
        suggested_value=suggestion["suggested_value"],
        confidence=suggestion["confidence"],
        confidenceLabel=suggestion.get("confidenceLabel", "Low"),
        rationale=suggestion.get("rationale", ""),
        citations=citations,
        flags=[FlagItem(**flag) for flag in suggestion.get("flags", [])],
        model=suggestion.get("model", ""),
        usage=suggestion.get("usage", {"input_tokens": 0, "output_tokens": 0}),
    )


def awaitable_to_sync(awaitable: Any) -> Any:
    import asyncio

    return asyncio.run(awaitable)


@router.post("/suggest", response_model=SuggestResponse)
def suggest_field(body: SuggestRequest, session: SessionDep, current_user: CurrentUser) -> Any:
    if not is_llm_available():
        raise HTTPException(status_code=503, detail="LLM unavailable. Configure ANTHROPIC_API_KEY and anthropic package.")

    doc_ids = _resolve_doc_ids(
        session=session,
        current_user=current_user,
        requested_doc_ids=body.doc_ids,
    )
    return _suggest_field_with_context(
        session=session,
        current_user=current_user,
        field_id=body.field_id,
        form_data=body.form_data,
        doc_ids=doc_ids,
    )


@router.post("/suggest-all", response_model=SuggestAllResponse)
def suggest_all_fields(body: SuggestAllRequest, session: SessionDep, current_user: CurrentUser) -> Any:
    if not is_llm_available():
        raise HTTPException(status_code=503, detail="LLM unavailable. Configure ANTHROPIC_API_KEY and anthropic package.")

    doc_ids = _resolve_doc_ids(
        session=session,
        current_user=current_user,
        requested_doc_ids=body.doc_ids,
    )

    evidence_by_field: dict[str, list[dict[str, Any]]] = {}
    for field in FORM_SCHEMA:
        evidence_by_field[field["id"]] = search_similar_chunks(
            session=session,
            query=f"{field['id']} {field['label']}",
            user_id=current_user.id,
            doc_ids=doc_ids,
            top_k=settings.HOUSING_RAG_TOP_K,
        )

    try:
        suggestions = awaitable_to_sync(
            suggest_all_with_llm(
                form_data=body.form_data,
                evidence_by_field=evidence_by_field,
            )
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return SuggestAllResponse(
        suggestions=[
            SuggestResponse(
                field_id=item["field_id"],
                suggested_value=item["suggested_value"],
                confidence=item["confidence"],
                confidenceLabel=item.get("confidenceLabel", "Low"),
                rationale=item.get("rationale", ""),
                citations=[
                    Citation(**citation)
                    for citation in item.get("citations", [])
                    if isinstance(citation, dict) and citation.get("docId")
                ],
                flags=[FlagItem(**flag) for flag in item.get("flags", [])],
                model=item.get("model", ""),
                usage=item.get("usage", {"input_tokens": 0, "output_tokens": 0}),
            )
            for item in suggestions
        ]
    )


@router.post("/preview-audit", response_model=AuditResponse)
def preview_audit(body: AuditRequest, session: SessionDep, current_user: CurrentUser) -> Any:
    flags: list[AuditFlag] = []
    form = body.form_data
    meta = body.field_meta

    for field in FORM_SCHEMA:
        field_id = field["id"]
        value = form.get(field_id, "").strip()
        if field["required"] and not value:
            flags.append(
                AuditFlag(
                    severity="BLOCKER",
                    code="REQUIRED_MISSING",
                    field_id=field_id,
                    message=f"{field['label']} is required.",
                    fix="Fill this field before submission.",
                )
            )

    household = form.get("household_size", "").strip()
    if household:
        try:
            household_val = int(household)
            if household_val < 1:
                flags.append(
                    AuditFlag(
                        severity="BLOCKER",
                        code="HOUSEHOLD_INVALID",
                        field_id="household_size",
                        message="Household size must be at least 1.",
                        fix="Enter a valid household size.",
                    )
                )
            elif household_val > 20:
                flags.append(
                    AuditFlag(
                        severity="WARNING",
                        code="HOUSEHOLD_UNUSUAL",
                        field_id="household_size",
                        message="Household size is unusually high.",
                        fix="Double-check this value.",
                    )
                )
        except ValueError:
            flags.append(
                AuditFlag(
                    severity="WARNING",
                    code="HOUSEHOLD_FORMAT",
                    field_id="household_size",
                    message="Household size should be a number.",
                    fix="Enter a whole number.",
                )
            )

    state_value = form.get("state", "").strip()
    if state_value and len(state_value) != 2:
        flags.append(
            AuditFlag(
                severity="WARNING",
                code="INVALID_STATE",
                field_id="state",
                message="State should use 2-letter code.",
                fix="Use standard two-letter state code.",
            )
        )

    zip_value = form.get("zip", "").strip()
    if zip_value and not re.match(r"^\d{5}(-\d{4})?$", zip_value):
        flags.append(
            AuditFlag(
                severity="WARNING",
                code="INVALID_ZIP",
                field_id="zip",
                message="ZIP format appears invalid.",
                fix="Use 5-digit ZIP or ZIP+4.",
            )
        )

    evidence_fields = [field for field in FORM_SCHEMA if field.get("evidence")]
    grounded = 0
    for field in evidence_fields:
        field_id = field["id"]
        value = form.get(field_id, "").strip()
        field_meta = meta.get(field_id, {})
        has_citations = bool(field_meta.get("citations"))
        if has_citations:
            grounded += 1
        if value and not has_citations:
            flags.append(
                AuditFlag(
                    severity="WARNING",
                    code="MISSING_EVIDENCE_REQUIRED",
                    field_id=field_id,
                    message=f"{field['label']} has no linked evidence citation.",
                    fix="Run Suggest again or add supporting documents.",
                )
            )

    rent = _parse_money(form.get("monthly_rent"))
    income = _parse_money(form.get("monthly_gross_income"))
    if rent is not None and income is not None and income > 0 and rent / income > 0.8:
        flags.append(
            AuditFlag(
                severity="INFO",
                code="RENT_TO_INCOME_HIGH",
                field_id="monthly_rent",
                message="Rent-to-income ratio is high.",
                fix="Double-check rent and income values.",
            )
        )

    blockers = sum(1 for flag in flags if flag.severity == "BLOCKER")
    warnings = sum(1 for flag in flags if flag.severity == "WARNING")
    infos = sum(1 for flag in flags if flag.severity == "INFO")

    doc_count_statement = (
        select(func.count())
        .select_from(HGDocument)
        .where(HGDocument.user_id == current_user.id)
        .where(HGDocument.status == HGDocumentStatus.ready)
    )
    ready_doc_count = session.exec(doc_count_statement).one()

    risk = min(100, blockers * 20 + warnings * 10 + infos * 3 + (15 if ready_doc_count == 0 else 0))
    coverage = round((grounded / len(evidence_fields)) * 100) if evidence_fields else 0

    return AuditResponse(
        flags=flags,
        blockers=blockers,
        warnings=warnings,
        infos=infos,
        risk=risk,
        coveragePct=coverage,
    )


@router.post("/submissions", response_model=SubmissionPublic)
def save_submission(body: SubmissionCreateRequest, session: SessionDep, current_user: CurrentUser) -> Any:
    now = _utcnow()
    submission = HGFormSubmission(
        user_id=current_user.id,
        form_data=json.dumps(body.form_data),
        field_meta=json.dumps(body.field_meta),
        status="submitted",
        created_at=now,
        updated_at=now,
    )
    session.add(submission)
    session.commit()
    session.refresh(submission)

    audit_report_id: uuid.UUID | None = None
    if body.audit is not None:
        audit = HGAuditReport(
            submission_id=submission.id,
            user_id=current_user.id,
            flags_json=json.dumps([flag.model_dump() for flag in body.audit.flags]),
            blockers=body.audit.blockers,
            warnings=body.audit.warnings,
            infos=body.audit.infos,
            risk=body.audit.risk,
            coverage_pct=body.audit.coverage_pct,
            created_at=now,
        )
        session.add(audit)
        session.commit()
        session.refresh(audit)
        audit_report_id = audit.id

    return SubmissionPublic(
        submission_id=submission.id,
        audit_report_id=audit_report_id,
        status=submission.status,
    )
