"""Housing Grant Vector Store Service.

Handles:
  - Text chunking (fixed-size with overlap)
  - Embedding generation (fastembed / all-MiniLM-L6-v2)
  - Storing chunks + embeddings in Postgres via pgvector
  - Similarity search for RAG retrieval

The service degrades gracefully:
  - No fastembed → skip embedding generation
  - No pgvector → skip vector storage/search
  - No database → return empty results
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

logger = logging.getLogger(__name__)

# ── Embedding model (lazy-loaded) ───────────────────────────────────

_embedding_model = None
EMBEDDING_DIM = 384  # all-MiniLM-L6-v2 output dimension


def _get_embedding_model():
    """Lazy-load the fastembed model."""
    global _embedding_model
    if _embedding_model is None:
        try:
            from fastembed import TextEmbedding

            _embedding_model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
            logger.info("Loaded fastembed model: BAAI/bge-small-en-v1.5")
        except ImportError:
            logger.warning("fastembed not installed — embeddings disabled")
            return None
        except Exception as e:
            logger.error("Failed to load embedding model: %s", e)
            return None
    return _embedding_model


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Generate embeddings for a list of texts.

    Returns a list of float vectors, one per input text.
    Returns empty list if embedding model is not available.
    """
    model = _get_embedding_model()
    if model is None:
        return []

    try:
        embeddings = list(model.embed(texts))
        return [emb.tolist() for emb in embeddings]
    except Exception as e:
        logger.error("Embedding generation failed: %s", e)
        return []


def embed_single(text: str) -> list[float] | None:
    """Generate embedding for a single text."""
    results = embed_texts([text])
    return results[0] if results else None


# ── Text chunking ───────────────────────────────────────────────────


def chunk_text(
    text: str,
    chunk_size: int = 512,
    chunk_overlap: int = 64,
) -> list[dict[str, Any]]:
    """Split text into overlapping chunks.

    Returns list of dicts with:
      - content: the chunk text
      - chunk_index: 0-based index
      - char_start: character offset in original text
      - char_end: character offset end
    """
    if not text or not text.strip():
        return []

    chunks = []
    start = 0
    idx = 0

    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunk_text_content = text[start:end].strip()

        if chunk_text_content:
            chunks.append({
                "content": chunk_text_content,
                "chunk_index": idx,
                "char_start": start,
                "char_end": end,
            })
            idx += 1

        # Move forward by chunk_size - overlap
        start += chunk_size - chunk_overlap
        if start >= len(text):
            break

    return chunks


# ── Store chunks in database ────────────────────────────────────────


async def store_document_chunks(
    session: Any,
    document_id: uuid.UUID,
    text: str,
    page: int | None = None,
) -> int:
    """Chunk text, generate embeddings, and store in the database.

    Returns the number of chunks stored.
    """
    from app.housing_grant_db_models import HGDocumentChunk, HAS_PGVECTOR

    chunks = chunk_text(text)
    if not chunks:
        return 0

    # Generate embeddings for all chunks
    contents = [c["content"] for c in chunks]
    embeddings = embed_texts(contents)

    stored = 0
    for i, chunk in enumerate(chunks):
        db_chunk = HGDocumentChunk(
            document_id=document_id,
            chunk_index=chunk["chunk_index"],
            page=page,
            content=chunk["content"],
            token_count=len(chunk["content"].split()),  # rough token estimate
        )

        # Set embedding if available
        if embeddings and i < len(embeddings):
            if HAS_PGVECTOR:
                # Store in the pgvector column
                db_chunk.embedding = embeddings[i]  # type: ignore
            else:
                # Store as JSON list (fallback)
                db_chunk.embedding = embeddings[i]

        session.add(db_chunk)
        stored += 1

    session.commit()
    return stored


# ── Similarity search ───────────────────────────────────────────────


async def search_similar_chunks(
    session: Any,
    query: str,
    user_id: uuid.UUID | None = None,
    doc_ids: list[str] | None = None,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """Find the most similar document chunks to a query.

    Uses pgvector cosine distance when available.
    Falls back to returning recent chunks if pgvector is not installed.
    """
    from app.housing_grant_db_models import HGDocumentChunk, HGDocument, HAS_PGVECTOR

    # Generate query embedding
    query_embedding = embed_single(query)

    if HAS_PGVECTOR and query_embedding:
        try:
            from sqlalchemy import select, func

            # Build query with cosine distance
            stmt = (
                select(
                    HGDocumentChunk,
                    HGDocument.filename,
                    HGDocument.doc_type,
                )
                .join(HGDocument, HGDocumentChunk.document_id == HGDocument.id)
            )

            if user_id:
                stmt = stmt.where(HGDocument.user_id == user_id)

            if doc_ids:
                stmt = stmt.where(HGDocument.id.in_(doc_ids))  # type: ignore

            # Order by cosine distance (closest first)
            stmt = stmt.order_by(
                HGDocumentChunk.__table__.c.embedding_vec.cosine_distance(query_embedding)
            ).limit(top_k)

            results = session.exec(stmt).all()

            return [
                {
                    "chunk_id": str(chunk.id),
                    "doc": filename,
                    "docType": doc_type,
                    "page": str(chunk.page or "1"),
                    "chunk": f"chk_{chunk.chunk_index:05d}",
                    "quote": chunk.content[:200],  # Truncate for safety
                    "score": 0.0,  # Would need to compute distance separately
                }
                for chunk, filename, doc_type in results
            ]
        except Exception as e:
            logger.error("Vector search failed: %s", e)

    # Fallback: return recent chunks without vector ranking
    try:
        from sqlalchemy import select

        stmt = (
            select(HGDocumentChunk, HGDocument.filename, HGDocument.doc_type)
            .join(HGDocument, HGDocumentChunk.document_id == HGDocument.id)
        )

        if user_id:
            stmt = stmt.where(HGDocument.user_id == user_id)

        stmt = stmt.order_by(HGDocumentChunk.created_at.desc()).limit(top_k)  # type: ignore
        results = session.exec(stmt).all()

        return [
            {
                "chunk_id": str(chunk.id),
                "doc": filename,
                "docType": doc_type,
                "page": str(chunk.page or "1"),
                "chunk": f"chk_{chunk.chunk_index:05d}",
                "quote": chunk.content[:200],
                "score": 0.0,
            }
            for chunk, filename, doc_type in results
        ]
    except Exception as e:
        logger.warning("Chunk retrieval failed: %s", e)
        return []


# ── Utility ─────────────────────────────────────────────────────────


def is_vector_store_available() -> bool:
    """Check if the vector store is fully functional."""
    try:
        from app.housing_grant_db_models import HAS_PGVECTOR
        model = _get_embedding_model()
        return HAS_PGVECTOR and model is not None
    except Exception:
        return False
