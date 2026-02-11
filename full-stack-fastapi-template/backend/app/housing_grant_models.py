"""Housing Grant API models."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class HGDocType(str, Enum):
    lease = "lease"
    paystub = "paystub"
    utility_bill = "utility_bill"
    provider_letter = "provider_letter"
    landlord_letter = "landlord_letter"
    rent_ledger = "rent_ledger"
    income_verification = "income_verification"
    other = "other"


class HGDocumentStatus(str, Enum):
    pending = "pending"
    uploaded = "uploaded"
    processing = "processing"
    ready = "ready"
    error = "error"


class HGIngestionJobStatus(str, Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    error = "error"


class DocumentUploadInitRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=512)
    doc_type: HGDocType
    content_type: str = Field(min_length=1, max_length=128)
    size_bytes: int = Field(gt=0)


class DocumentUploadInitResponse(BaseModel):
    document_id: uuid.UUID
    object_key: str
    upload_url: str
    required_headers: dict[str, str] = Field(default_factory=dict)
    expires_at: datetime


class DocumentUploadCompleteRequest(BaseModel):
    etag: str | None = Field(default=None, max_length=256)


class DocumentUploadCompleteResponse(BaseModel):
    document_id: uuid.UUID
    status: HGDocumentStatus


class DocumentPublic(BaseModel):
    id: uuid.UUID
    filename: str
    doc_type: HGDocType
    status: HGDocumentStatus
    pages: int | None = None
    badge: str = "info"
    created_at: datetime
    updated_at: datetime


class DocumentsPublic(BaseModel):
    data: list[DocumentPublic]
    count: int


class Citation(BaseModel):
    doc_id: uuid.UUID = Field(alias="docId")
    doc: str
    doc_type: str = Field(alias="docType", default="")
    page: str = ""
    chunk: str = ""
    quote: str = ""

    model_config = {"populate_by_name": True}


class FlagItem(BaseModel):
    code: str
    severity: str
    message: str


class SuggestRequest(BaseModel):
    field_id: str
    form_data: dict[str, str] = Field(default_factory=dict)
    doc_ids: list[uuid.UUID] = Field(default_factory=list)


class SuggestResponse(BaseModel):
    field_id: str
    suggested_value: str
    confidence: float
    confidence_label: str = Field(alias="confidenceLabel", default="")
    rationale: str
    citations: list[Citation] = Field(default_factory=list)
    flags: list[FlagItem] = Field(default_factory=list)
    model: str = ""
    usage: dict[str, int] = Field(default_factory=lambda: {"input_tokens": 0, "output_tokens": 0})

    model_config = {"populate_by_name": True}


class SuggestAllRequest(BaseModel):
    form_data: dict[str, str] = Field(default_factory=dict)
    doc_ids: list[uuid.UUID] = Field(default_factory=list)


class SuggestAllResponse(BaseModel):
    suggestions: list[SuggestResponse]


class AuditFlag(BaseModel):
    severity: str
    code: str
    field_id: str
    message: str
    fix: str = ""


class AuditRequest(BaseModel):
    form_data: dict[str, str] = Field(default_factory=dict)
    doc_ids: list[uuid.UUID] = Field(default_factory=list)
    field_meta: dict[str, dict[str, object]] = Field(default_factory=dict)


class AuditResponse(BaseModel):
    flags: list[AuditFlag]
    blockers: int
    warnings: int
    infos: int
    risk: int
    coverage_pct: int = Field(alias="coveragePct", default=0)

    model_config = {"populate_by_name": True}


class SubmissionCreateRequest(BaseModel):
    form_data: dict[str, str] = Field(default_factory=dict)
    field_meta: dict[str, dict[str, object]] = Field(default_factory=dict)
    audit: AuditResponse | None = None


class SubmissionPublic(BaseModel):
    submission_id: uuid.UUID
    audit_report_id: uuid.UUID | None = None
    status: str
