import base64
import secrets

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

from tcm_platform.config import settings
from tcm_platform.db import SessionLocal, engine
from tcm_platform.knowledge_worker import process_next_knowledge_publish
from tcm_platform.main import app
from tcm_platform.models import SourceDocument, SourceRevision, TaskJob, utc_now
from tcm_platform.segment_service import process_next_segment
from tcm_platform.source_import import process_next_import
from tcm_platform.storage import ContentAddressedStore


class FakeEmbedder:
    model_version = "test/fixed-embedding-v1"
    endpoint = "https://example.invalid/embeddings"
    max_batch_size = 10

    def embed(self, texts):
        return [[1.0, float(len(value) % 7 + 1), 2.0] for value in texts]


class FakeReranker:
    model_version = "test/fixed-reranker-v1"
    endpoint = "https://example.invalid/rerank"


class FailingEmbedder(FakeEmbedder):
    def embed(self, texts):
        raise RuntimeError("simulated model outage")


@pytest.fixture(autouse=True)
def migrated_postgres():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1 FROM governance.knowledge_version LIMIT 1"))
    except SQLAlchemyError:
        pytest.skip("knowledge migrations are unavailable")


def test_knowledge_api_import_review_and_publish_job(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_root", tmp_path / "store")
    secret = secrets.token_urlsafe(32)
    monkeypatch.setattr(settings, "bootstrap_secret", SecretStr(secret))
    monkeypatch.setattr(
        "tcm_platform.knowledge_worker.cloud_clients_from_environment",
        lambda: (FakeEmbedder(), FakeReranker()),
    )
    origin = "http://127.0.0.1:5173"
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        assert client.get("/api/v1/knowledge/sources").status_code == 401
        bootstrap = client.post("/api/v1/local-session/bootstrap", headers={"Origin": origin},
                                json={"bootstrap_secret": secret})
        assert bootstrap.status_code == 200
        headers = {"Origin": origin, "X-CSRF-Token": bootstrap.json()["csrf_token"]}
        payload = {"metadata": {"source_type": "CLASSIC", "title": "API 测试古籍"},
                   "file_format": "txt",
                   "content_base64": base64.b64encode("太阳之为病，脉浮。".encode()).decode()}
        patient_case = client.post("/api/v1/knowledge/sources/import", headers={
            **headers, "Idempotency-Key": secrets.token_hex(12)},
            json={**payload, "metadata": {**payload["metadata"], "source_type": "PATIENT_CASE"}})
        assert patient_case.status_code == 400
        assert client.post("/api/v1/knowledge/sources/import", json=payload,
                           headers={"Origin": origin}).status_code == 403
        imported = client.post("/api/v1/knowledge/sources/import", json=payload,
                               headers={**headers, "Idempotency-Key": secrets.token_hex(12)})
        assert imported.status_code == 202, imported.text
        source_id = imported.json()["source_id"]
        assert imported.json()["job_id"].startswith("JOB-")
        assert imported.headers["location"].endswith(imported.json()["job_id"])
        store = ContentAddressedStore(settings.data_root)
        with SessionLocal() as session:
            source_uuid = session.scalar(select(SourceDocument.id).where(
                SourceDocument.public_id == source_id))
            source_revision_uuid = session.scalar(select(SourceRevision.id).where(
                SourceRevision.source_id == source_uuid, SourceRevision.revision_no == 1))
        for _ in range(100):
            result = process_next_import(store=store)
            if result is not None and result.source_revision_id == source_revision_uuid:
                assert result.status == "PARSED"
                break
        else:
            pytest.fail("source parse job did not complete")
        for _ in range(100):
            result = process_next_segment(store=store)
            if result is not None and result.source_revision_id == source_revision_uuid:
                assert result.status == "SEGMENTED"
                break
        else:
            pytest.fail("source segment job did not complete")
        segments = client.get(f"/api/v1/knowledge/sources/{source_id}/revisions/1/segments")
        assert segments.status_code == 200
        segment = next(row for row in segments.json() if row["segment_type"] == "PARAGRAPH")
        reference = f"{segment['segment_id']}@1"
        drafted = client.post("/api/v1/knowledge/drafts/evidence", headers=headers,
                              json={"segment_ids": [reference], "strength": "DIRECT"})
        assert drafted.status_code == 201
        evidence_id = drafted.json()["evidence_id"]
        assert drafted.json()["quote_text"] == "太阳之为病，脉浮。"
        evidence_ref = f"{evidence_id}@1"
        issue = client.post("/api/v1/knowledge/quality-issues", headers=headers,
                            json={"target_kind": "evidence_revision", "target_ref": evidence_ref,
                                  "issue_type": "LOCATION_CHECK", "severity": "BLOCKER",
                                  "description": "待核对"})
        assert issue.status_code == 201
        quality = client.get("/api/v1/knowledge/quality-report")
        assert quality.status_code == 200
        assert quality.json()["publication_blocked"] is True
        review_url = f"/api/v1/knowledge/reviews/evidence_revision/{evidence_ref}"
        denied = client.post(review_url, headers=headers,
                             json={"decision": "APPROVE", "note": "已核对"})
        assert denied.status_code == 409
        resolved = client.post(f"/api/v1/knowledge/quality-issues/{issue.json()['issue_id']}/resolve",
                               headers=headers, json={"note": "已核对"})
        assert resolved.status_code == 200
        assert client.post(review_url, headers=headers,
                           json={"decision": "APPROVE", "note": "原文已核对"}).status_code == 201
        concept = client.post("/api/v1/knowledge/drafts/concepts", headers=headers,
                              json={"canonical_name": "太阳病", "concept_type": "DISEASE",
                                    "evidence_id": evidence_id, "evidence_revision_no": 1})
        assert concept.status_code == 201
        concept_id = concept.json()["concept_id"]
        assert client.post(f"/api/v1/knowledge/reviews/concept/{concept_id}", headers=headers,
                           json={"decision": "APPROVE", "note": "术语已核对"}).status_code == 201
        detail = client.get(f"/api/v1/knowledge/drafts/concept/{concept_id}")
        assert detail.status_code == 200
        assert detail.json()["evidence"][0]["quote_text"] == "太阳之为病，脉浮。"
        snapshot = client.post("/api/v1/knowledge/versions", headers=headers)
        assert snapshot.status_code == 201
        version_id = snapshot.json()["version_id"]
        publish_payload = {"embedding_model": FakeEmbedder.model_version,
                           "rerank_model": FakeReranker.model_version,
                           "embedding_endpoint": FakeEmbedder.endpoint,
                           "rerank_endpoint": FakeReranker.endpoint}
        publish_headers = {**headers, "Idempotency-Key": secrets.token_hex(12)}
        published = client.post(f"/api/v1/knowledge/versions/{version_id}/publish",
                                headers=publish_headers, json=publish_payload)
        assert published.status_code == 202
        assert client.post(f"/api/v1/knowledge/versions/{version_id}/publish",
                           headers=publish_headers, json=publish_payload).json() == published.json()
        assert process_next_knowledge_publish() is not None
        job = client.get(published.headers["location"])
        assert job.status_code == 200
        assert job.json()["status"] == "COMPLETED"
        version = client.get(f"/api/v1/knowledge/versions/{version_id}")
        assert version.json()["active"] is True
        assert version.json()["index_builds"][0]["status"] == "READY"
        batch = client.post("/api/v1/knowledge/evidence/batch", headers=headers,
                            json=[evidence_ref])
        assert batch.status_code == 200
        assert batch.json()[0]["source_id"] == source_id
        assert client.post(review_url, headers=headers,
                           json={"decision": "REJECT", "note": "改写"}).status_code == 409
        assert client.get(f"/api/v1/knowledge/versions/{version_id}/compare/{version_id}").status_code == 200
        next_snapshot = client.post("/api/v1/knowledge/versions", headers=headers)
        assert next_snapshot.status_code == 201
        next_version_id = next_snapshot.json()["version_id"]
        next_publish = client.post(f"/api/v1/knowledge/versions/{next_version_id}/publish",
                                   headers={**headers, "Idempotency-Key": secrets.token_hex(12)},
                                   json=publish_payload)
        assert next_publish.status_code == 202
        monkeypatch.setattr(
            "tcm_platform.knowledge_worker.cloud_clients_from_environment",
            lambda: (FailingEmbedder(), FakeReranker()),
        )
        assert process_next_knowledge_publish() is not None
        assert client.get(next_publish.headers["location"]).json()["status"] == "RETRY_WAIT"
        assert client.get(f"/api/v1/knowledge/versions/{version_id}").json()["active"] is True
        monkeypatch.setattr(
            "tcm_platform.knowledge_worker.cloud_clients_from_environment",
            lambda: (FakeEmbedder(), FakeReranker()),
        )
        with SessionLocal.begin() as session:
            session.query(TaskJob).filter_by(public_id=next_publish.json()["job_id"]).update(
                {TaskJob.available_at: utc_now()})
        assert process_next_knowledge_publish() is not None
        assert client.get(next_publish.headers["location"]).json()["status"] == "COMPLETED"
        assert client.get(f"/api/v1/knowledge/versions/{next_version_id}").json()["active"] is True
