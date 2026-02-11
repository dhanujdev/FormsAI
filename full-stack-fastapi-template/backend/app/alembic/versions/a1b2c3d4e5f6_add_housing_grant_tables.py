"""add housing grant tables

Revision ID: a1b2c3d4e5f6
Revises: fe56fa70289e
Create Date: 2026-02-10

Creates:
  - hg_document
  - hg_document_chunk (with pgvector embedding_vec column)
  - hg_form_submission
  - hg_audit_report
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "a1b2c3d4e5f6"
down_revision = "fe56fa70289e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable pgvector extension (safe to call multiple times)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # hg_document
    op.create_table(
        "hg_document",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("doc_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("pages", sa.Integer(), nullable=True),
        sa.Column("storage_path", sa.String(1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_hg_document_user_id", "hg_document", ["user_id"])

    # hg_document_chunk
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

    # Add pgvector embedding column (384-dim for bge-small-en-v1.5)
    op.execute(
        "ALTER TABLE hg_document_chunk ADD COLUMN embedding_vec vector(384)"
    )

    # Create HNSW index for fast cosine similarity search
    op.execute(
        "CREATE INDEX ix_hg_chunk_embedding_cosine ON hg_document_chunk "
        "USING hnsw (embedding_vec vector_cosine_ops)"
    )

    # hg_form_submission
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

    # hg_audit_report
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
    op.drop_table("hg_document_chunk")
    op.drop_table("hg_document")
