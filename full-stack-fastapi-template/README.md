# Housing Grant AI Copilot

Authenticated housing-grant workflow built on the FastAPI full-stack template.

## What Is Implemented

- Auth-protected `/api/v1/housing-grant/*` backend endpoints.
- Signed object-storage upload flow (`upload-url` + `complete`) with persisted document metadata.
- Async ingestion jobs with status lifecycle: `pending -> uploaded -> processing -> ready|error`.
- Text extraction (`pypdf` for PDFs, UTF-8 fallback for text files), chunking, and embeddings.
- RAG retrieval from Postgres/pgvector with per-user ownership filters.
- LLM suggest/suggest-all endpoints with hard-fail behavior when Anthropic is unavailable.
- Preview audit endpoint with warning-level missing-evidence policy.
- Submission persistence for form payload + audit snapshot.
- React UI for upload, suggest, preview audit, evidence modal, and submission save.

## Stack

- Frontend: React + TypeScript + Vite + Playwright.
- Backend: FastAPI + SQLModel + Alembic.
- Data: PostgreSQL + `pgvector`.
- Storage: S3-compatible API (dev/prod configurable).
- LLM: Anthropic API (required for suggest/suggest-all).

## Local Development

1. Configure environment:

```bash
cp .env.example .env
```

2. Start backend dependencies (Postgres and optional local S3-compatible service).
3. Backend:

```bash
cd backend
uv sync --dev
uv run fastapi dev app/main.py
```

4. Frontend:

```bash
cd frontend
npm install
npm run dev
```

## Validation Commands

- Backend lint: `uv run ruff check app tests`
- Backend types: `uv run mypy app`
- Frontend build: `npm run build`
- Housing E2E (mocked API flow): `npx playwright test tests/housing-grant.spec.ts --project=chromium --no-deps`

## Deployment

See `deployment.md` for AWS-first deployment mapping, environment variables, and smoke-test checklist.
