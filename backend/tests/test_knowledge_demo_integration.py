"""Engineering demo flow: public candidates and genuine local indexes, no model doubles."""

import re
import secrets

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select, text
from test_initial_corpus_integration import _segment_text

from tcm_platform.config import settings
from tcm_platform.db import SessionLocal
from tcm_platform.knowledge_publish import activate_knowledge_version, create_index_build
from tcm_platform.knowledge_worker import process_next_knowledge_publish
from tcm_platform.main import app
from tcm_platform.models import (
    EmbeddingRecord,
    IndexBuild,
    KnowledgeRuntimeState,
    KnowledgeVersion,
    SourceDocument,
    utc_now,
)
from tcm_platform.publication_config import publication_configuration
from tcm_platform.retrieval import RetrievalExecution, search_published
from tcm_platform.source_import import SourceMetadata
from tcm_platform.storage import ContentAddressedStore


@pytest.fixture(autouse=True)
def isolated_database(monkeypatch):
    with SessionLocal() as session:
        database = session.scalar(text("SELECT current_database()"))
        assert database.startswith("tcm_") and database.endswith("_test"), database
        session.execute(text("SELECT 1 FROM knowledge.knowledge_extraction LIMIT 1"))
    monkeypatch.setenv("TCM_OUTBOUND_MODE", "LOCAL_ONLY")
    # Both publication and public route configuration must avoid even loading a credential.
    def forbidden():
        pytest.fail("local publication attempted to construct a cloud client")
    monkeypatch.setattr("tcm_platform.knowledge_worker.cloud_clients_from_environment", forbidden)


def test_candidates_review_local_publish_and_query(tmp_path, monkeypatch):
    secret = secrets.token_urlsafe(32)
    monkeypatch.setattr(settings, "bootstrap_secret", SecretStr(secret))
    path = tmp_path / "engineering-demo.txt"
    original = "太陽病，發熱，汗出，惡風，脈緩者，名為中風。"
    path.write_text(original, encoding="utf-8")
    imported, _ = _segment_text(path, ContentAddressedStore(tmp_path / "store"),
                                SourceMetadata(source_type="OTHER", title="合成工程流程验证"),
                                monkeypatch)
    with SessionLocal() as session:
        source_id = session.get(SourceDocument, imported.source_id).public_id
    origin = "http://127.0.0.1:5173"
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        route = f"/api/v1/knowledge/sources/{source_id}/revisions/1"
        assert client.get("/api/v1/knowledge/publication-config").status_code == 401
        bootstrap = client.post("/api/v1/local-session/bootstrap", headers={"Origin": origin},
                                json={"bootstrap_secret": secret})
        assert bootstrap.status_code == 200
        headers = {"Origin": origin, "X-CSRF-Token": bootstrap.json()["csrf_token"]}
        configured = client.get("/api/v1/knowledge/publication-config")
        assert configured.status_code == 200
        assert configured.json()["mode"] == "LOCAL_ONLY"
        assert configured.json()["configuration"]["embedding_model"] is None
        assert client.get(route + "/candidates").status_code == 404
        assert client.post(route + "/extract").status_code == 403
        extracted = client.post(route + "/extract", headers=headers)
        assert extracted.status_code == 200, extracted.text
        batch = extracted.json()
        assert batch["concept_count"] > 0 and batch["relation_count"] == 1
        assert batch["evidence"][0]["quote_text"] == original
        assert not re.search(r'"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}"',
                             extracted.text)
        assert client.post(route + "/extract", headers=headers).json() == batch
        assert client.get(route + "/candidates").json() == batch
        assert all(row["status"] == "DRAFT" for row in batch["concepts"])
        targets = [("evidence_revision", f"{row['evidence_id']}@{row['revision_no']}")
                   for row in batch["evidence"]]
        targets += [("concept", row["concept_id"]) for row in batch["concepts"]]
        targets += [("relation", row["relation_id"]) for row in batch["relations"]]
        for kind, ref in targets:
            reviewed = client.post(f"/api/v1/knowledge/reviews/{kind}/{ref}", headers=headers,
                                   json={"decision": "APPROVE", "note": "合成工程校验，非专家验收"})
            assert reviewed.status_code == 201, reviewed.text
        snapshot = client.post("/api/v1/knowledge/versions", headers=headers)
        assert snapshot.status_code == 201, snapshot.text
        version_id = snapshot.json()["version_id"]
        published = client.post(f"/api/v1/knowledge/versions/{version_id}/publish",
                                headers={**headers, "Idempotency-Key": secrets.token_hex(16)},
                                json=configured.json()["configuration"])
        assert published.status_code == 202, published.text
        assert process_next_knowledge_publish() is not None
        assert client.get(published.headers["location"]).json()["status"] == "COMPLETED"
        version = client.get(f"/api/v1/knowledge/versions/{version_id}").json()
        assert version["active"] is True
        assert version["index_builds"][0]["vector_status"] == "NOT_APPLICABLE"
        assert any(row["source_id"] == source_id for row in client.get(
            "/api/v1/knowledge/published-sources").json())
        results = client.get("/api/v1/retrieval/query", params={"query": "惡風", "mode": "local"})
        assert results.status_code == 200, results.text
        assert results.json()["mode"] == "LOCAL"
        assert "vector" not in results.json()["channels"]
        assert any(row["source_id"] == source_id for row in results.json()["results"])
        with SessionLocal() as session:
            runtime = session.get(KnowledgeRuntimeState, 1)
            build_id = runtime.active_index_build_id
            assert session.scalar(select(func.count()).select_from(EmbeddingRecord).where(
                EmbeddingRecord.index_build_id == build_id)) == 0
        class ForbiddenModel:
            model_version = "must-not-be-used"

            def embed(self, texts):
                pytest.fail("local retrieval called a vector model")

            def rerank(self, query, documents):
                pytest.fail("local retrieval called a rerank model")

        execution = RetrievalExecution()
        assert search_published("惡風", embedder=ForbiddenModel(), reranker=ForbiddenModel(),
                                execution=execution)
        assert execution.mode == "LOCAL" and "vector" not in execution.channels


def test_formula_candidate_field_spans_and_rejected_replay(tmp_path, monkeypatch):
    secret = secrets.token_urlsafe(32)
    monkeypatch.setattr(settings, "bootstrap_secret", SecretStr(secret))
    path = tmp_path / "synthetic-formula.txt"
    path.write_text("合成測試湯方：\n\n桂枝三兩（去皮）；芍藥三兩。\n\n"
                    "右二味，以水七升，煮取三升。\n\n分溫再服。", encoding="utf-8")
    imported, _ = _segment_text(path, ContentAddressedStore(tmp_path / "store"),
                                SourceMetadata(source_type="OTHER", title="合成方剂投影测试"), monkeypatch)
    with SessionLocal() as session:
        source_id = session.get(SourceDocument, imported.source_id).public_id
    origin = "http://127.0.0.1:5173"
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        bootstrap = client.post("/api/v1/local-session/bootstrap", headers={"Origin": origin},
                                json={"bootstrap_secret": secret})
        headers = {"Origin": origin, "X-CSRF-Token": bootstrap.json()["csrf_token"]}
        route = f"/api/v1/knowledge/sources/{source_id}/revisions/1"
        extracted = client.post(route + "/extract", headers=headers)
        assert extracted.status_code == 200, extracted.text
        batch = extracted.json()
        assert batch["formula_count"] == 1
        formula = batch["formulas"][0]
        assert formula["original_name"] == "合成測試湯"
        assert formula["field_sources"] and formula["ingredients"]
        assert all(span["segment_ref"].endswith("@1") for span in formula["field_sources"])
        assert not re.search(r'"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}"',
                             extracted.text)
        rejected = client.post(f"/api/v1/knowledge/reviews/formula_revision/"
                               f"{formula['formula_id']}@{formula['revision_no']}", headers=headers,
                               json={"decision": "REJECT", "note": "工程拒绝重放验证"})
        assert rejected.status_code == 201, rejected.text
        replay = client.post(route + "/extract", headers=headers).json()
        assert replay["extraction_id"] == batch["extraction_id"]
        assert replay["formulas"][0]["status"] == "REJECTED"


def test_local_status_cannot_bypass_fts_coverage_or_change_active_pair(tmp_path, monkeypatch):
    from tcm_platform.knowledge_publish import create_knowledge_version, review_object
    from tcm_platform.knowledge_service import create_evidence

    path = tmp_path / "incomplete-index.txt"
    path.write_text("合成门禁验证。", encoding="utf-8")
    _, segments = _segment_text(path, ContentAddressedStore(tmp_path / "store"),
                                SourceMetadata(source_type="OTHER", title="工程门禁验证"), monkeypatch)
    revision_id = create_evidence([segments[0].id], strength="DIRECT")
    review_object("evidence_revision", revision_id, reviewer_id="test-curator",
                  decision="APPROVE", note="工程门禁验证，非专家验收")
    version_id = create_knowledge_version()
    build_id = create_index_build(version_id,
                                  configuration=publication_configuration()["configuration"])
    with SessionLocal.begin() as session:
        runtime = session.get(KnowledgeRuntimeState, 1)
        active_pair = runtime.active_knowledge_version_id, runtime.active_index_build_id
        build = session.get(IndexBuild, build_id)
        build.status, build.fts_status, build.vector_status = "READY", "READY", "NOT_APPLICABLE"
        build.validated_at = utc_now()
        session.get(KnowledgeVersion, version_id).status = "VALIDATING"
    with pytest.raises(ValueError, match="incomplete"):
        activate_knowledge_version(version_id, build_id)
    with SessionLocal() as session:
        runtime = session.get(KnowledgeRuntimeState, 1)
        assert (runtime.active_knowledge_version_id, runtime.active_index_build_id) == active_pair
