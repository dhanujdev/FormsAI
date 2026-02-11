"""Housing Grant AI Copilot – Pydantic models for API request/response."""

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field
from sqlmodel import SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ─── Document schemas ───────────────────────────────────────────────


class DocumentCreate(BaseModel):
    filename: str = Field(min_length=1, max_length=512)
    doc_type: str = Field(min_length=1, max_length=64)


class DocumentPublic(BaseModel):
    id: str
    filename: str
    doc_type: str
    status: str
    pages: int | None = None
    badge: str = "good"
    created_at: str | None = None


class DocumentsPublic(BaseModel):
    data: list[DocumentPublic]
    count: int


# ─── Suggest schemas ────────────────────────────────────────────────


class Citation(BaseModel):
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


class DocContent(BaseModel):
    """Actual document text passed to the LLM."""
    filename: str
    doc_type: str
    content: str  # text content or base64 for images


class SuggestRequest(BaseModel):
    field_id: str
    form_data: dict[str, str] = {}
    doc_ids: list[str] = []
    doc_contents: list[DocContent] = []  # actual document text for LLM


class SuggestResponse(BaseModel):
    field_id: str
    suggested_value: str
    confidence: float
    confidence_label: str = Field(alias="confidenceLabel", default="")
    rationale: str
    citations: list[Citation] = []
    flags: list[FlagItem] = []
    model: str = "mock"
    usage: dict[str, int] = {"input_tokens": 0, "output_tokens": 0}

    model_config = {"populate_by_name": True}


class SuggestAllRequest(BaseModel):
    form_data: dict[str, str] = {}
    doc_ids: list[str] = []
    doc_contents: list[DocContent] = []  # actual document text for LLM


class SuggestAllResponse(BaseModel):
    suggestions: list[SuggestResponse]


# ─── Audit schemas ──────────────────────────────────────────────────


class AuditFlag(BaseModel):
    severity: str
    code: str
    field_id: str
    message: str
    fix: str = ""


class AuditRequest(BaseModel):
    form_data: dict[str, str] = {}
    doc_ids: list[str] = []
    field_meta: dict[str, dict] = {}  # type: ignore[type-arg]


class AuditResponse(BaseModel):
    flags: list[AuditFlag]
    blockers: int
    warnings: int
    infos: int
    risk: int
    coverage_pct: int = Field(alias="coveragePct", default=0)

    model_config = {"populate_by_name": True}
