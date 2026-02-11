"""Housing Grant database models (SQLModel + pgvector)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import Column, Text
from sqlmodel import Field, Relationship, SQLModel

from app.housing_grant_models import HGDocumentStatus, HGIngestionJobStatus

try:
    from pgvector.sqlalchemy import Vector

    VECTOR_DIM = 384
    HAS_PGVECTOR = True
except ImportError:
    Vector = None
    VECTOR_DIM = 384
    HAS_PGVECTOR = False


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class HGDocument(SQLModel, table=True):
    __tablename__ = "hg_document"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="user.id", nullable=False, index=True)
    filename: str = Field(max_length=512)
    doc_type: str = Field(max_length=64)
    status: HGDocumentStatus = Field(
        default=HGDocumentStatus.pending,
        sa_column=Column(
            sa.Enum(HGDocumentStatus, name="hg_document_status"),
            nullable=False,
            server_default=HGDocumentStatus.pending.value,
        ),
    )
    pages: int | None = None
    storage_path: str = Field(max_length=1024)
    content_type: str = Field(max_length=128)
    size_bytes: int | None = None
    etag: str | None = Field(default=None, max_length=256)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    chunks: list[HGDocumentChunk] = Relationship(back_populates="document", cascade_delete=True)
    ingestion_jobs: list[HGIngestionJob] = Relationship(back_populates="document", cascade_delete=True)


class HGDocumentChunk(SQLModel, table=True):
    __tablename__ = "hg_document_chunk"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    document_id: uuid.UUID = Field(foreign_key="hg_document.id", nullable=False, index=True)
    chunk_index: int = Field(default=0)
    page: int | None = None
    content: str = Field(sa_column=Column(Text, nullable=False))
    token_count: int | None = None
    created_at: datetime = Field(default_factory=_utcnow)

    document: HGDocument | None = Relationship(back_populates="chunks")


if HAS_PGVECTOR:
    HGDocumentChunk.__table__.append_column(  # type: ignore[attr-defined]
        Column("embedding_vec", Vector(VECTOR_DIM), nullable=True)
    )


class HGIngestionJob(SQLModel, table=True):
    __tablename__ = "hg_ingestion_job"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    document_id: uuid.UUID = Field(foreign_key="hg_document.id", nullable=False, index=True)
    user_id: uuid.UUID = Field(foreign_key="user.id", nullable=False, index=True)
    status: HGIngestionJobStatus = Field(
        default=HGIngestionJobStatus.queued,
        sa_column=Column(
            sa.Enum(HGIngestionJobStatus, name="hg_ingestion_job_status"),
            nullable=False,
            server_default=HGIngestionJobStatus.queued.value,
        ),
    )
    idempotency_key: str = Field(max_length=128, index=True)
    retry_count: int = 0
    error_message: str | None = Field(default=None, max_length=2048)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    document: HGDocument | None = Relationship(back_populates="ingestion_jobs")


class HGFormSubmission(SQLModel, table=True):
    __tablename__ = "hg_form_submission"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="user.id", nullable=False, index=True)
    form_data: str = Field(sa_column=Column(Text, nullable=False))
    field_meta: str | None = Field(default=None, sa_column=Column(Text))
    status: str = Field(default="draft", max_length=32)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class HGAuditReport(SQLModel, table=True):
    __tablename__ = "hg_audit_report"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    submission_id: uuid.UUID = Field(foreign_key="hg_form_submission.id", nullable=False, index=True)
    user_id: uuid.UUID = Field(foreign_key="user.id", nullable=False, index=True)
    flags_json: str = Field(sa_column=Column(Text, nullable=False))
    blockers: int = 0
    warnings: int = 0
    infos: int = 0
    risk: int = 0
    coverage_pct: int = 0
    created_at: datetime = Field(default_factory=_utcnow)
