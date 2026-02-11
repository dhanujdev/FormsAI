"""Document ingestion pipeline for housing grant uploads."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from io import BytesIO

from pypdf import PdfReader
from sqlmodel import Session, col, delete, select

from app.core.config import settings
from app.core.db import engine
from app.housing_grant_db_models import (
    HGDocument,
    HGDocumentChunk,
    HGIngestionJob,
)
from app.housing_grant_models import HGDocumentStatus, HGIngestionJobStatus
from app.storage import StorageError, get_storage_client
from app.vector_store import store_document_chunks

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _extract_text_pages(file_bytes: bytes, *, content_type: str, filename: str) -> list[tuple[int, str]]:
    if content_type == "application/pdf" or filename.lower().endswith(".pdf"):
        pages: list[tuple[int, str]] = []
        reader = PdfReader(BytesIO(file_bytes))
        for idx, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            text = text.strip()
            if text:
                pages.append((idx, text))
        return pages

    decoded = file_bytes.decode("utf-8", errors="ignore").strip()
    if not decoded:
        return []
    return [(1, decoded)]


def run_ingestion_job(*, job_id: uuid.UUID, document_id: uuid.UUID, user_id: uuid.UUID) -> None:
    storage = get_storage_client()

    with Session(engine) as session:
        job = session.get(HGIngestionJob, job_id)
        document = session.get(HGDocument, document_id)
        if not job or not document or document.user_id != user_id:
            logger.warning("Ingestion target not found for job=%s document=%s", job_id, document_id)
            return

        job.status = HGIngestionJobStatus.running
        job.updated_at = _utcnow()
        document.status = HGDocumentStatus.processing
        document.updated_at = _utcnow()
        session.add(job)
        session.add(document)
        session.commit()

        try:
            file_bytes = storage.get_object_bytes(object_key=document.storage_path)
            if len(file_bytes) > settings.HOUSING_INGESTION_MAX_BYTES:
                raise ValueError("file exceeds ingestion size limit")

            pages = _extract_text_pages(
                file_bytes,
                content_type=document.content_type,
                filename=document.filename,
            )
            if not pages:
                raise ValueError("no extractable text found in uploaded document")

            session.exec(delete(HGDocumentChunk).where(col(HGDocumentChunk.document_id) == document.id))
            total_chunks = 0
            for page_num, text in pages:
                total_chunks += store_document_chunks(
                    session=session,
                    document_id=document.id,
                    text=text,
                    page=page_num,
                )

            if total_chunks <= 0:
                raise ValueError("failed to generate chunks from document text")

            document.status = HGDocumentStatus.ready
            document.pages = len(pages)
            document.updated_at = _utcnow()
            job.status = HGIngestionJobStatus.completed
            job.error_message = None
            job.updated_at = _utcnow()
            session.add(document)
            session.add(job)
            session.commit()
        except (StorageError, ValueError, Exception) as exc:
            logger.exception("Document ingestion failed: job=%s doc=%s", job_id, document_id)
            job.retry_count += 1
            job.status = HGIngestionJobStatus.error
            job.error_message = str(exc)[:2000]
            job.updated_at = _utcnow()
            document.status = HGDocumentStatus.error
            document.updated_at = _utcnow()
            session.add(job)
            session.add(document)
            session.commit()
            raise


def latest_document_job(*, session: Session, document_id: uuid.UUID) -> HGIngestionJob | None:
    statement = (
        select(HGIngestionJob)
        .where(col(HGIngestionJob.document_id) == document_id)
        .order_by(col(HGIngestionJob.created_at).desc())
        .limit(1)
    )
    return session.exec(statement).first()
