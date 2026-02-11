"""Housing Grant database models (SQLModel + pgvector).

Tables:
  - hg_document       – uploaded documents (lease, paystub, etc.)
  - hg_document_chunk – text chunks with vector embeddings for RAG
  - hg_form_submission – saved form snapshots
  - hg_audit_report   – stored audit results
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Text
from sqlmodel import Field, Relationship, SQLModel

# pgvector column type — imported conditionally so the app
# still starts even without the pgvector extension installed
try:
    from pgvector.sqlalchemy import Vector

    VECTOR_DIM = 384  # matches fastembed / all-MiniLM-L6-v2
    HAS_PGVECTOR = True
except ImportError:
    Vector = None  # type: ignore
    VECTOR_DIM = 384
    HAS_PGVECTOR = False


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ─── Document ────────────────────────────────────────────────────────


class HGDocument(SQLModel, table=True):
    """An uploaded document (lease, paystub, utility bill, provider letter)."""

    __tablename__ = "hg_document"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="user.id", nullable=False, index=True)
    filename: str = Field(max_length=512)
    doc_type: str = Field(max_length=64)  # lease | paystub | utility | provider_letter
    status: str = Field(default="pending", max_length=32)  # pending | processing | ready | error
    pages: int | None = None
    storage_path: str | None = Field(default=None, max_length=1024)
    created_at: datetime = Field(default_factory=_utcnow, sa_type=DateTime(timezone=True))  # type: ignore

    # relationships
    chunks: list["HGDocumentChunk"] = Relationship(back_populates="document", cascade_delete=True)


# ─── Document Chunk (with vector embedding) ─────────────────────────


class HGDocumentChunk(SQLModel, table=True):
    """A text chunk extracted from a document, with an embedding vector for RAG."""

    __tablename__ = "hg_document_chunk"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    document_id: uuid.UUID = Field(foreign_key="hg_document.id", nullable=False, index=True)
    chunk_index: int = Field(default=0)
    page: int | None = None
    content: str = Field(sa_column=Column(Text, nullable=False))
    token_count: int | None = None
    # NOTE: The embedding_vec column is added dynamically below via pgvector.
    # Do NOT add a `list[float]` field here — SQLModel cannot map it.

    created_at: datetime = Field(default_factory=_utcnow, sa_type=DateTime(timezone=True))  # type: ignore

    # relationships
    document: HGDocument | None = Relationship(back_populates="chunks")


# If pgvector is installed, add the vector column properly
if HAS_PGVECTOR:
    # Add the vector column via SQLAlchemy column override
    HGDocumentChunk.__table__.append_column(  # type: ignore
        Column("embedding_vec", Vector(VECTOR_DIM), nullable=True)
    )


# ─── Form Submission ────────────────────────────────────────────────


class HGFormSubmission(SQLModel, table=True):
    """A snapshot of the form data at a point in time."""

    __tablename__ = "hg_form_submission"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="user.id", nullable=False, index=True)
    form_data: str = Field(sa_column=Column(Text, nullable=False))  # JSON blob
    field_meta: str | None = Field(default=None, sa_column=Column(Text))  # JSON blob of suggestion metadata
    status: str = Field(default="draft", max_length=32)  # draft | submitted | approved
    created_at: datetime = Field(default_factory=_utcnow, sa_type=DateTime(timezone=True))  # type: ignore
    updated_at: datetime = Field(default_factory=_utcnow, sa_type=DateTime(timezone=True))  # type: ignore


# ─── Audit Report ───────────────────────────────────────────────────


class HGAuditReport(SQLModel, table=True):
    """A stored audit result linked to a form submission."""

    __tablename__ = "hg_audit_report"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    submission_id: uuid.UUID = Field(foreign_key="hg_form_submission.id", nullable=False, index=True)
    user_id: uuid.UUID = Field(foreign_key="user.id", nullable=False, index=True)
    flags_json: str = Field(sa_column=Column(Text, nullable=False))  # JSON array of flags
    blockers: int = 0
    warnings: int = 0
    infos: int = 0
    risk: int = 0
    coverage_pct: int = 0
    created_at: datetime = Field(default_factory=_utcnow, sa_type=DateTime(timezone=True))  # type: ignore
