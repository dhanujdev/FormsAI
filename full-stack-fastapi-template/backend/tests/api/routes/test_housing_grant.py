import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, col, select

from app.api.routes import housing_grant
from app.core.config import settings
from app.housing_grant_db_models import HGDocument, HGIngestionJob
from app.housing_grant_ingestion import run_ingestion_job
from app.housing_grant_models import HGDocType, HGDocumentStatus, HGIngestionJobStatus
from app.models import User
from app.storage import PresignedUpload


def _api(path: str) -> str:
    return f"{settings.API_V1_STR}/housing-grant{path}"


def _get_normal_user(db: Session) -> User:
    user = db.exec(select(User).where(col(User.email) == settings.EMAIL_TEST_USER)).first()
    assert user is not None
    return user


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("POST", "/documents/upload-url", {"filename": "lease.pdf", "doc_type": "lease", "content_type": "application/pdf", "size_bytes": 128}),
        ("POST", f"/documents/{uuid.uuid4()}/complete", {"etag": "test-etag"}),
        ("GET", "/documents", None),
        ("DELETE", f"/documents/{uuid.uuid4()}", None),
        ("POST", "/suggest", {"field_id": "full_name", "form_data": {}, "doc_ids": []}),
        ("POST", "/suggest-all", {"form_data": {}, "doc_ids": []}),
        ("POST", "/preview-audit", {"form_data": {}, "doc_ids": [], "field_meta": {}}),
        ("POST", "/submissions", {"form_data": {}, "field_meta": {}, "audit": None}),
    ],
)
def test_housing_routes_require_auth(
    client: TestClient,
    method: str,
    path: str,
    payload: dict[str, object] | None,
) -> None:
    response = client.request(method, _api(path), json=payload)
    assert response.status_code in {401, 403}


def test_upload_complete_flow_persists_document_and_job(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeStorage:
        def create_presigned_upload(self, *, object_key: str, content_type: str) -> PresignedUpload:
            return PresignedUpload(
                object_key=object_key,
                upload_url="https://uploads.example.test/fake",
                required_headers={"Content-Type": content_type},
                expires_at=datetime.now(timezone.utc),
            )

        def head_object(self, *, object_key: str) -> dict[str, object]:
            return {"ContentLength": 1024, "ETag": '"etag-from-storage"'}

        def delete_object(self, *, object_key: str) -> None:
            _ = object_key

    def _noop_ingestion(**_kwargs: object) -> None:
        return None

    monkeypatch.setattr(housing_grant, "get_storage_client", lambda: FakeStorage())
    monkeypatch.setattr(housing_grant, "run_ingestion_job", _noop_ingestion)

    init_response = client.post(
        _api("/documents/upload-url"),
        headers=normal_user_token_headers,
        json={
            "filename": "lease.pdf",
            "doc_type": "lease",
            "content_type": "application/pdf",
            "size_bytes": 512,
        },
    )
    assert init_response.status_code == 200
    init_payload = init_response.json()
    document_id = uuid.UUID(init_payload["document_id"])

    document = db.get(HGDocument, document_id)
    assert document is not None
    assert document.status == HGDocumentStatus.pending

    complete_response = client.post(
        _api(f"/documents/{document_id}/complete"),
        headers=normal_user_token_headers,
        json={"etag": "explicit-etag"},
    )
    assert complete_response.status_code == 200
    complete_payload = complete_response.json()
    assert complete_payload["status"] == HGDocumentStatus.uploaded.value

    db.expire_all()
    persisted_document = db.get(HGDocument, document_id)
    assert persisted_document is not None
    assert persisted_document.status == HGDocumentStatus.uploaded
    assert persisted_document.etag == "explicit-etag"

    job = db.exec(
        select(HGIngestionJob)
        .where(col(HGIngestionJob.document_id) == document_id)
        .order_by(col(HGIngestionJob.created_at).desc())
    ).first()
    assert job is not None
    assert job.status == HGIngestionJobStatus.queued


def test_ingestion_job_transitions_to_ready(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = _get_normal_user(db)
    document = HGDocument(
        user_id=user.id,
        filename="income.txt",
        doc_type=HGDocType.income_verification.value,
        status=HGDocumentStatus.uploaded,
        storage_path="housing-grant/test/income.txt",
        content_type="text/plain",
        size_bytes=24,
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    job = HGIngestionJob(
        document_id=document.id,
        user_id=user.id,
        status=HGIngestionJobStatus.queued,
        idempotency_key=f"test-{document.id}",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    class GoodStorage:
        def get_object_bytes(self, *, object_key: str) -> bytes:
            _ = object_key
            return b"Tenant name Jane Doe\nMonthly rent $1200\n"

    def _store_chunks(
        *,
        _session: Session,
        _document_id: uuid.UUID,
        _text: str,
        _page: int | None,
    ) -> int:
        return 2

    monkeypatch.setattr("app.housing_grant_ingestion.get_storage_client", lambda: GoodStorage())
    monkeypatch.setattr("app.housing_grant_ingestion.store_document_chunks", _store_chunks)

    run_ingestion_job(job_id=job.id, document_id=document.id, user_id=user.id)

    db.expire_all()
    reloaded_document = db.get(HGDocument, document.id)
    reloaded_job = db.get(HGIngestionJob, job.id)
    assert reloaded_document is not None
    assert reloaded_job is not None
    assert reloaded_document.status == HGDocumentStatus.ready
    assert reloaded_document.pages == 1
    assert reloaded_job.status == HGIngestionJobStatus.completed
    assert reloaded_job.error_message is None


def test_ingestion_job_marks_error_when_no_extractable_text(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = _get_normal_user(db)
    document = HGDocument(
        user_id=user.id,
        filename="empty.txt",
        doc_type=HGDocType.other.value,
        status=HGDocumentStatus.uploaded,
        storage_path="housing-grant/test/empty.txt",
        content_type="text/plain",
        size_bytes=1,
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    job = HGIngestionJob(
        document_id=document.id,
        user_id=user.id,
        status=HGIngestionJobStatus.queued,
        idempotency_key=f"test-{document.id}-error",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    class EmptyStorage:
        def get_object_bytes(self, *, object_key: str) -> bytes:
            _ = object_key
            return b"   "

    monkeypatch.setattr("app.housing_grant_ingestion.get_storage_client", lambda: EmptyStorage())

    with pytest.raises(ValueError, match="no extractable text"):
        run_ingestion_job(job_id=job.id, document_id=document.id, user_id=user.id)

    db.expire_all()
    reloaded_document = db.get(HGDocument, document.id)
    reloaded_job = db.get(HGIngestionJob, job.id)
    assert reloaded_document is not None
    assert reloaded_job is not None
    assert reloaded_document.status == HGDocumentStatus.error
    assert reloaded_job.status == HGIngestionJobStatus.error
    assert reloaded_job.error_message is not None


def test_suggest_hard_fails_when_llm_unavailable(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(housing_grant, "is_llm_available", lambda: False)

    response = client.post(
        _api("/suggest"),
        headers=normal_user_token_headers,
        json={"field_id": "full_name", "form_data": {}, "doc_ids": []},
    )
    assert response.status_code == 503
    assert "LLM unavailable" in response.json()["detail"]


def test_suggest_returns_grounded_citations(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = _get_normal_user(db)
    document = HGDocument(
        user_id=user.id,
        filename="lease.pdf",
        doc_type=HGDocType.lease.value,
        status=HGDocumentStatus.ready,
        storage_path="housing-grant/test/lease.pdf",
        content_type="application/pdf",
        size_bytes=2048,
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    monkeypatch.setattr(housing_grant, "is_llm_available", lambda: True)
    monkeypatch.setattr(
        housing_grant,
        "search_similar_chunks",
        lambda **_kwargs: [
            {
                "docId": str(document.id),
                "doc": "lease.pdf",
                "docType": "lease",
                "page": "1",
                "chunk": "chk_00001",
                "quote": "Monthly rent is $1200.",
            }
        ],
    )
    monkeypatch.setattr(
        housing_grant,
        "awaitable_to_sync",
        lambda _awaitable: {
            "field_id": "monthly_rent",
            "suggested_value": "1200",
            "confidence": 0.91,
            "confidenceLabel": "High",
            "rationale": "Lease states monthly rent as $1200.",
            "citations": [
                {
                    "docId": str(document.id),
                    "doc": "lease.pdf",
                    "docType": "lease",
                    "page": "1",
                    "chunk": "chk_00001",
                    "quote": "Monthly rent is $1200.",
                }
            ],
            "flags": [],
            "model": "test-model",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        },
    )

    response = client.post(
        _api("/suggest"),
        headers=normal_user_token_headers,
        json={
            "field_id": "monthly_rent",
            "form_data": {},
            "doc_ids": [str(document.id)],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["suggested_value"] == "1200"
    assert payload["confidenceLabel"] == "High"
    assert payload["citations"]
    assert payload["citations"][0]["docId"] == str(document.id)


def test_preview_audit_marks_missing_evidence_as_warning(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    response = client.post(
        _api("/preview-audit"),
        headers=normal_user_token_headers,
        json={
            "form_data": {"full_name": "Jane Doe"},
            "doc_ids": [],
            "field_meta": {},
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert any(
        flag["code"] == "MISSING_EVIDENCE_REQUIRED"
        and flag["field_id"] == "full_name"
        and flag["severity"] == "WARNING"
        for flag in payload["flags"]
    )
