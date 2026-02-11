"""add housing grant tables

Revision ID: a1b2c3d4e5f6
Revises: fe56fa70289e
Create Date: 2026-02-10
"""

from alembic import op
import sqlalchemy as sa


revision = "a1b2c3d4e5f6"
down_revision = "fe56fa70289e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # pgvector extension (optional)
    try:
        conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
    except Exception:
        pass

    # Custom enum types (idempotent)
    conn.execute(sa.text(
        "DO $$ BEGIN "
        "CREATE TYPE hg_document_status AS ENUM ('pending','uploaded','processing','ready','error'); "
        "EXCEPTION WHEN duplicate_object THEN null; END $$"
    ))
    conn.execute(sa.text(
        "DO $$ BEGIN "
        "CREATE TYPE hg_ingestion_job_status AS ENUM ('queued','running','completed','error'); "
        "EXCEPTION WHEN duplicate_object THEN null; END $$"
    ))

    # ── hg_document ──
    conn.execute(sa.text("""
    CREATE TABLE IF NOT EXISTS hg_document (
        id UUID PRIMARY KEY,
        user_id UUID NOT NULL REFERENCES "user"(id),
        filename VARCHAR(512) NOT NULL,
        doc_type VARCHAR(64) NOT NULL,
        status hg_document_status NOT NULL DEFAULT 'pending',
        pages INTEGER,
        storage_path VARCHAR(1024) NOT NULL,
        content_type VARCHAR(128) NOT NULL,
        size_bytes INTEGER,
        etag VARCHAR(256),
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_hg_document_user_id ON hg_document(user_id)"))

    # ── hg_document_chunk ──
    conn.execute(sa.text("""
    CREATE TABLE IF NOT EXISTS hg_document_chunk (
        id UUID PRIMARY KEY,
        document_id UUID NOT NULL REFERENCES hg_document(id) ON DELETE CASCADE,
        chunk_index INTEGER NOT NULL DEFAULT 0,
        page INTEGER,
        content TEXT NOT NULL,
        token_count INTEGER,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_hg_document_chunk_document_id ON hg_document_chunk(document_id)"))

    # Vector column (optional)
    try:
        conn.execute(sa.text("ALTER TABLE hg_document_chunk ADD COLUMN IF NOT EXISTS embedding_vec vector(384)"))
        conn.execute(sa.text(
            "CREATE INDEX IF NOT EXISTS ix_hg_chunk_embedding_cosine "
            "ON hg_document_chunk USING hnsw (embedding_vec vector_cosine_ops)"
        ))
    except Exception:
        pass

    # ── hg_ingestion_job ──
    conn.execute(sa.text("""
    CREATE TABLE IF NOT EXISTS hg_ingestion_job (
        id UUID PRIMARY KEY,
        document_id UUID NOT NULL REFERENCES hg_document(id) ON DELETE CASCADE,
        user_id UUID NOT NULL REFERENCES "user"(id),
        status hg_ingestion_job_status NOT NULL DEFAULT 'queued',
        idempotency_key VARCHAR(128) NOT NULL,
        retry_count INTEGER NOT NULL DEFAULT 0,
        error_message VARCHAR(2048),
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_hg_ingestion_job_document_id ON hg_ingestion_job(document_id)"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_hg_ingestion_job_user_id ON hg_ingestion_job(user_id)"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_hg_ingestion_job_idempotency_key ON hg_ingestion_job(idempotency_key)"))

    # ── hg_form_submission ──
    conn.execute(sa.text("""
    CREATE TABLE IF NOT EXISTS hg_form_submission (
        id UUID PRIMARY KEY,
        user_id UUID NOT NULL REFERENCES "user"(id),
        form_data TEXT NOT NULL,
        field_meta TEXT,
        status VARCHAR(32) NOT NULL DEFAULT 'draft',
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_hg_form_submission_user_id ON hg_form_submission(user_id)"))

    # ── hg_audit_report ──
    conn.execute(sa.text("""
    CREATE TABLE IF NOT EXISTS hg_audit_report (
        id UUID PRIMARY KEY,
        submission_id UUID NOT NULL REFERENCES hg_form_submission(id),
        user_id UUID NOT NULL REFERENCES "user"(id),
        flags_json TEXT NOT NULL,
        blockers INTEGER NOT NULL DEFAULT 0,
        warnings INTEGER NOT NULL DEFAULT 0,
        infos INTEGER NOT NULL DEFAULT 0,
        risk INTEGER NOT NULL DEFAULT 0,
        coverage_pct INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_hg_audit_report_user_id ON hg_audit_report(user_id)"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_hg_audit_report_submission_id ON hg_audit_report(submission_id)"))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP TABLE IF EXISTS hg_audit_report CASCADE"))
    conn.execute(sa.text("DROP TABLE IF EXISTS hg_form_submission CASCADE"))
    conn.execute(sa.text("DROP TABLE IF EXISTS hg_ingestion_job CASCADE"))
    conn.execute(sa.text("DROP TABLE IF EXISTS hg_document_chunk CASCADE"))
    conn.execute(sa.text("DROP TABLE IF EXISTS hg_document CASCADE"))
    conn.execute(sa.text("DROP TYPE IF EXISTS hg_ingestion_job_status"))
    conn.execute(sa.text("DROP TYPE IF EXISTS hg_document_status"))
