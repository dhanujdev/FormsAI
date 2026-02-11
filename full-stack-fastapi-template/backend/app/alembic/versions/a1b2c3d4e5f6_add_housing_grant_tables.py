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


document_status_enum = sa.Enum(
    "pending",
    "uploaded",
    "processing",
    "ready",
    "error",
    name="hg_document_status",
)

ingestion_status_enum = sa.Enum(
    "queued",
    "running",
    "completed",
    "error",
    name="hg_ingestion_job_status",
)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    document_status_enum.create(op.get_bind(), checkfirst=True)
    ingestion_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "hg_document",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("doc_type", sa.String(64), nullable=False),
        sa.Column("status", document_status_enum, nullable=False, server_default="pending"),
        sa.Column("pages", sa.Integer(), nullable=True),
        sa.Column("storage_path", sa.String(1024), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("etag", sa.String(256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_hg_document_user_id", "hg_document", ["user_id"])

    op.create_table(
        "hg_document_chunk",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("document_id", sa.Uuid(), sa.ForeignKey("hg_document.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_hg_document_chunk_document_id", "hg_document_chunk", ["document_id"])
    op.execute("ALTER TABLE hg_document_chunk ADD COLUMN embedding_vec vector(384)")
    op.execute(
        "CREATE INDEX ix_hg_chunk_embedding_cosine ON hg_document_chunk USING hnsw (embedding_vec vector_cosine_ops)"
    )

    op.create_table(
        "hg_ingestion_job",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("document_id", sa.Uuid(), sa.ForeignKey("hg_document.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("status", ingestion_status_enum, nullable=False, server_default="queued"),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.String(2048), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_hg_ingestion_job_document_id", "hg_ingestion_job", ["document_id"])
    op.create_index("ix_hg_ingestion_job_user_id", "hg_ingestion_job", ["user_id"])
    op.create_index("ix_hg_ingestion_job_idempotency_key", "hg_ingestion_job", ["idempotency_key"])

    op.create_table(
        "hg_form_submission",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("form_data", sa.Text(), nullable=False),
        sa.Column("field_meta", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_hg_form_submission_user_id", "hg_form_submission", ["user_id"])

    op.create_table(
        "hg_audit_report",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("submission_id", sa.Uuid(), sa.ForeignKey("hg_form_submission.id"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("flags_json", sa.Text(), nullable=False),
        sa.Column("blockers", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("warnings", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("infos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("risk", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("coverage_pct", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_hg_audit_report_user_id", "hg_audit_report", ["user_id"])
    op.create_index("ix_hg_audit_report_submission_id", "hg_audit_report", ["submission_id"])


def downgrade() -> None:
    op.drop_table("hg_audit_report")
    op.drop_table("hg_form_submission")
    op.drop_table("hg_ingestion_job")
    op.drop_table("hg_document_chunk")
    op.drop_table("hg_document")

    ingestion_status_enum.drop(op.get_bind(), checkfirst=True)
    document_status_enum.drop(op.get_bind(), checkfirst=True)
