"""Housing Grant vector store helpers."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlmodel import Session, col, select

logger = logging.getLogger(__name__)

_embedding_model: Any | None = None
EMBEDDING_DIM = 384


def _get_embedding_model() -> Any | None:
    global _embedding_model
    if _embedding_model is None:
        try:
            from fastembed import TextEmbedding

            _embedding_model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
        except ImportError:
            logger.warning("fastembed not installed, embeddings disabled")
            return None
        except Exception as exc:  # pragma: no cover - defensive path
            logger.error("Failed loading embedding model: %s", exc)
            return None
    return _embedding_model


def embed_texts(texts: list[str]) -> list[list[float]]:
    model = _get_embedding_model()
    if model is None:
        return []
    try:
        vectors = list(model.embed(texts))
        return [vec.tolist() for vec in vectors]
    except Exception as exc:
        logger.error("Embedding generation failed: %s", exc)
        return []


def embed_single(text: str) -> list[float] | None:
    vectors = embed_texts([text])
    return vectors[0] if vectors else None


def chunk_text(text: str, *, chunk_size: int = 512, chunk_overlap: int = 64) -> list[dict[str, Any]]:
    if not text.strip():
        return []

    chunks: list[dict[str, Any]] = []
    start = 0
    idx = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        content = text[start:end].strip()
        if content:
            chunks.append(
                {
                    "content": content,
                    "chunk_index": idx,
                    "char_start": start,
                    "char_end": end,
                }
            )
            idx += 1
        start += chunk_size - chunk_overlap
    return chunks


def store_document_chunks(
    *,
    session: Session,
    document_id: uuid.UUID,
    text: str,
    page: int | None,
) -> int:
    from app.housing_grant_db_models import HAS_PGVECTOR, HGDocumentChunk

    chunks = chunk_text(text)
    if not chunks:
        return 0

    embeddings = embed_texts([chunk["content"] for chunk in chunks])
    stored = 0
    for idx, chunk in enumerate(chunks):
        db_chunk = HGDocumentChunk(
            document_id=document_id,
            chunk_index=chunk["chunk_index"],
            page=page,
            content=chunk["content"],
            token_count=len(chunk["content"].split()),
        )
        if HAS_PGVECTOR and idx < len(embeddings) and hasattr(db_chunk, "embedding_vec"):
            db_chunk.embedding_vec = embeddings[idx]

        session.add(db_chunk)
        stored += 1

    session.commit()
    return stored


def search_similar_chunks(
    *,
    session: Session,
    query: str,
    user_id: uuid.UUID,
    doc_ids: list[uuid.UUID] | None = None,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    from app.housing_grant_db_models import HAS_PGVECTOR, HGDocument, HGDocumentChunk

    query_vector = embed_single(query)

    if HAS_PGVECTOR and query_vector is not None:
        try:
            stmt = (
                select(HGDocumentChunk, HGDocument)
                .join(HGDocument, col(HGDocumentChunk.document_id) == col(HGDocument.id))
                .where(col(HGDocument.user_id) == user_id)
            )
            if doc_ids:
                stmt = stmt.where(col(HGDocument.id).in_(doc_ids))

            embedding_column = getattr(HGDocumentChunk, "embedding_vec", None)
            if embedding_column is None:
                raise RuntimeError("pgvector column not available")

            stmt = stmt.order_by(embedding_column.cosine_distance(query_vector)).limit(top_k)
            results = session.exec(stmt).all()

            return [
                {
                    "doc_id": str(doc.id),
                    "chunk_id": str(chunk.id),
                    "doc": doc.filename,
                    "docType": doc.doc_type,
                    "page": str(chunk.page or "1"),
                    "chunk": f"chk_{chunk.chunk_index:05d}",
                    "quote": chunk.content[:240],
                    "score": 0.0,
                }
                for chunk, doc in results
            ]
        except Exception as exc:
            logger.warning("Vector search failed, falling back to recency: %s", exc)

    stmt = (
        select(HGDocumentChunk, HGDocument)
        .join(HGDocument, col(HGDocumentChunk.document_id) == col(HGDocument.id))
        .where(col(HGDocument.user_id) == user_id)
    )
    if doc_ids:
        stmt = stmt.where(col(HGDocument.id).in_(doc_ids))

    stmt = stmt.order_by(col(HGDocumentChunk.created_at).desc()).limit(top_k)
    results = session.exec(stmt).all()

    return [
        {
            "doc_id": str(doc.id),
            "chunk_id": str(chunk.id),
            "doc": doc.filename,
            "docType": doc.doc_type,
            "page": str(chunk.page or "1"),
            "chunk": f"chk_{chunk.chunk_index:05d}",
            "quote": chunk.content[:240],
            "score": 0.0,
        }
        for chunk, doc in results
    ]


def is_vector_store_available() -> bool:
    from app.housing_grant_db_models import HAS_PGVECTOR

    return HAS_PGVECTOR and _get_embedding_model() is not None
