"""The review workspace keeps exact source revisions and readable field citations."""

import re
import secrets
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select, text
from test_initial_corpus_integration import _process_target

from tcm_platform.config import settings
from tcm_platform.db import SessionLocal
from tcm_platform.knowledge_formula_provenance import FormulaFieldSourceSpec
from tcm_platform.knowledge_service import (
    IngredientSpec,
    create_concept,
    create_evidence,
    create_formula,
    create_herb,
    create_relation,
)
from tcm_platform.main import app
from tcm_platform.models import (
    Concept,
    Evidence,
    EvidenceRevision,
    Formula,
    FormulaRevision,
    Herb,
    KnowledgeRelation,
    SourceDocument,
    TextSegment,
    TextSegmentRevision,
)
from tcm_platform.source_import import SourceMetadata, import_file
from tcm_platform.storage import ContentAddressedStore


@pytest.fixture
def workflow(tmp_path, monkeypatch):
    with SessionLocal() as session:
        database = session.scalar(text("SELECT current_database()"))
        assert database.startswith("tcm_") and database.endswith("_test"), database
    secret = secrets.token_urlsafe(32)
    monkeypatch.setattr(settings, "bootstrap_secret", SecretStr(secret))
    store = ContentAddressedStore(tmp_path / "store")

    def material(number, source_id=None, evidence_id=None):
        path = tmp_path / f"source-{number}.txt"
        original = f"合成工作區{number}：桂枝三兩。"
        path.write_text(original, encoding="utf-8")
        imported = import_file(
            path, SourceMetadata(source_type="OTHER",
                                 title=f"合成审核工作区{1 if source_id else number}"),
            source_id=source_id, request_key=f"workflow:{uuid4()}", store=store,
        )
        assert _process_target(imported, store, monkeypatch).status == "PARSED"
        assert _process_target(imported, store, monkeypatch, segment=True).status == "SEGMENTED"
        with SessionLocal() as session:
            segment = session.scalar(select(TextSegmentRevision).where(
                TextSegmentRevision.source_revision_id == imported.source_revision_id,
                TextSegmentRevision.segment_type == "PARAGRAPH"))
        evidence = create_evidence([segment.id], strength="DIRECT", evidence_id=evidence_id)
        concept = create_concept(f"合成概念{number}", concept_type="OTHER",
                                 evidence_revision_id=evidence)
        relation = create_relation(concept, concept, relation_type="RELATED_TO",
                                   assertion_text="合成关系", evidence_revision_id=evidence)
        herb = create_herb("桂枝", evidence_revision_id=evidence)
        herb_start = original.index("桂枝")
        formula = create_formula(
            f"合成工作區{number}", evidence_revision_id=evidence,
            ingredients=(IngredientSpec(original_name="桂枝", herb_id=herb,
                                        amount_original="三兩"),),
            field_sources=(
                FormulaFieldSourceSpec("original_name", evidence, segment.id, 0, original.index("：")),
                FormulaFieldSourceSpec("ingredients.0.herb_id", evidence, segment.id,
                                       herb_start, herb_start + 2, basis="合成药材对应验证"),
            ),
        )
        with SessionLocal() as session:
            formula_row = session.get(FormulaRevision, formula)
            ev_row = session.get(EvidenceRevision, evidence)
            return {
                "source_internal": imported.source_id,
                "source_public": session.get(SourceDocument, imported.source_id).public_id,
                "evidence_internal": ev_row.evidence_id,
                "evidence_ref": f"{session.get(Evidence, ev_row.evidence_id).public_id}@{ev_row.revision_no}",
                "segment_ref": (
                    f"{session.get(TextSegment, segment.segment_id).public_id}"
                    f"@{2 if source_id else 1}"),
                "herb_public": session.get(Herb, herb).public_id,
                "checksum": segment.checksum,
                "refs": {
                    "concept": session.get(Concept, concept).public_id,
                    "relation": session.get(KnowledgeRelation, relation).public_id,
                    "herb": session.get(Herb, herb).public_id,
                    "formula_revision": f"{session.get(Formula, formula_row.formula_id).public_id}@1",
                },
            }

    first = material(1)
    second = material(2, first["source_internal"], first["evidence_internal"])
    other = material(3)
    origin = "http://127.0.0.1:5173"
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        assert client.get("/api/v1/knowledge/drafts/concept").status_code == 401
        bootstrap = client.post("/api/v1/local-session/bootstrap", headers={"Origin": origin},
                                json={"bootstrap_secret": secret})
        assert bootstrap.status_code == 200
        headers = {"Origin": origin, "X-CSRF-Token": bootstrap.json()["csrf_token"]}
        yield client, headers, first, second, other


def test_review_lists_filter_exact_revision_before_limit(workflow):
    client, _, first, second, other = workflow
    for kind in first["refs"]:
        route = f"/api/v1/knowledge/drafts/{kind}"
        for candidate, revision in ((first, 1), (second, 2), (other, 1)):
            response = client.get(route, params={"source_id": candidate["source_public"],
                                                "source_revision_no": revision, "limit": 1})
            assert response.status_code == 200, response.text
            assert response.json() == [{"ref": candidate["refs"][kind], "status": "DRAFT"}]
        all_revisions = client.get(route, params={"source_id": first["source_public"]}).json()
        assert {row["ref"] for row in all_revisions} == {
            first["refs"][kind], second["refs"][kind]}
    evidence = client.get("/api/v1/knowledge/evidence", params={
        "source_id": first["source_public"], "source_revision_no": 1, "limit": 1})
    assert evidence.status_code == 200
    assert len(evidence.json()) == 1 and evidence.json()[0]["source_revision_no"] == 1
    assert client.get("/api/v1/knowledge/drafts/concept", params={
        "source_revision_no": 1}).status_code == 422
    assert client.get("/api/v1/knowledge/drafts/concept", params={
        "source_id": "SRC-unknown"}).status_code == 404
    assert client.get("/api/v1/knowledge/drafts/concept", params={
        "source_id": first["source_public"], "source_revision_no": 999}).status_code == 404


def test_evidence_details_load_full_context_from_exact_historical_revision(
    workflow, tmp_path, monkeypatch
):
    client, _, _, _, _ = workflow
    before = "上文完整内容，" * 220 + "上文结束。"
    after = "下文完整内容，" * 220 + "下文结束。"
    store = ContentAddressedStore(tmp_path / "context-store")
    path = tmp_path / "context.txt"
    path.write_text(f"{before}\n\n中间引用。\n\n{after}", encoding="utf-8")
    imported = import_file(
        path, SourceMetadata(source_type="OTHER", title="合成完整上下文"),
        request_key=f"context:{uuid4()}", store=store,
    )
    assert _process_target(imported, store, monkeypatch).status == "PARSED"
    assert _process_target(imported, store, monkeypatch, segment=True).status == "SEGMENTED"
    with SessionLocal() as session:
        rows = session.scalars(select(TextSegmentRevision).where(
            TextSegmentRevision.source_revision_id == imported.source_revision_id,
            TextSegmentRevision.segment_type == "PARAGRAPH",
        ).order_by(TextSegmentRevision.sequence_no)).all()
        assert len(rows) == 3
    refs = []
    for segment in rows:
        revision_id = create_evidence([segment.id], strength="DIRECT")
        with SessionLocal() as session:
            revision = session.get(EvidenceRevision, revision_id)
            public_id = session.get(Evidence, revision.evidence_id).public_id
            refs.append((public_id, revision_id))
    # A newer revision changes the context. Old evidence must retain revision 1.
    path.write_text("新修订上文。\n\n中间引用。\n\n新修订下文。", encoding="utf-8")
    newer = import_file(path, SourceMetadata(source_type="OTHER", title="合成完整上下文"),
                        source_id=imported.source_id, request_key=f"context:{uuid4()}",
                        store=store)
    assert _process_target(newer, store, monkeypatch).status == "PARSED"
    assert _process_target(newer, store, monkeypatch, segment=True).status == "SEGMENTED"
    for index, (public_id, revision_id) in enumerate(refs):
        response = client.get(f"/api/v1/knowledge/evidence/{public_id}?revision_no=1")
        assert response.status_code == 200, response.text
        detail = response.json()
        assert detail["source_revision_no"] == 1
        assert detail["full_context_before"] == (rows[index - 1].original_text if index else "")
        assert detail["full_context_after"] == (rows[index + 1].original_text if index < 2 else "")
        assert detail["context_complete"] is True
        with SessionLocal() as session:
            saved = session.get(EvidenceRevision, revision_id)
            assert detail["context_before"] == saved.context_before
            assert detail["context_after"] == saved.context_after
    assert len(before) > 1000 and len(after) > 1000


def test_complete_mixed_body_range_and_reading_pagination(workflow, tmp_path, monkeypatch):
    client, headers, _, _, _ = workflow
    original = ["【组成】合成甲药三两。", "续文保留剂量说明。", "【用法】合成煎服方法。"]
    path = tmp_path / "mixed-body.txt"
    path.write_text("\n".join(original), encoding="utf-8")
    store = ContentAddressedStore(tmp_path / "mixed-store")
    imported = import_file(path, SourceMetadata(source_type="OTHER", title="连续混合正文回归"),
                           request_key=f"mixed:{uuid4()}", store=store)
    assert _process_target(imported, store, monkeypatch).status == "PARSED"
    assert _process_target(imported, store, monkeypatch, segment=True).status == "SEGMENTED"
    with SessionLocal() as session:
        source_id = session.get(SourceDocument, imported.source_id).public_id
    route = f"/api/v1/knowledge/sources/{source_id}/revisions/1/segments"
    all_rows = client.get(route).json()
    body = [row for row in all_rows if row["segment_type"] in {"CLAUSE", "PARAGRAPH"}]
    assert [row["original_text"] for row in body] == original
    first_page = client.get(route, params={"view": "reading", "limit": 2}).json()
    second_page = client.get(route, params={"view": "reading", "limit": 2, "after": first_page[-1]["sequence_no"]}).json()
    assert [row["segment_id"] for row in first_page + second_page] == [row["segment_id"] for row in all_rows if row["segment_type"] != "SENTENCE"]
    refs = [row["segment_id"] + "@1" for row in body]
    response = client.post("/api/v1/knowledge/drafts/evidence", headers=headers,
                           json={"segment_ids": refs, "strength": "DIRECT"})
    assert response.status_code == 201, response.text
    assert response.json()["quote_text"] == "\n".join(original)
    assert response.json()["segment_ids"] == [row["segment_id"] for row in body]
    # Same-type endpoints may not hide the intervening ordinary paragraph.
    omitted = client.post("/api/v1/knowledge/drafts/evidence", headers=headers,
                          json={"segment_ids": [refs[0], refs[-1]], "strength": "DIRECT"})
    assert omitted.status_code == 400 and "contiguous" in omitted.text
    sentence = next(row for row in all_rows if row["segment_type"] == "SENTENCE")
    repeated = client.post("/api/v1/knowledge/drafts/evidence", headers=headers,
                           json={"segment_ids": [refs[0], sentence["segment_id"] + "@1"], "strength": "DIRECT"})
    assert repeated.status_code == 400


def test_partial_formula_field_sources_are_public_and_readable(workflow):
    client, headers, first, _, _ = workflow
    route = f"/api/v1/knowledge/drafts/formula_revision/{first['refs']['formula_revision']}"
    response = client.get(route)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "DRAFT"
    sources = {row["field_key"]: row for row in body["field_sources"]}
    assert set(sources) == {"original_name", "ingredients.0.herb_id"}
    assert sources["original_name"]["quote_text"] == "合成工作區1"
    assert sources["ingredients.0.herb_id"]["value_snapshot"] == first["herb_public"]
    assert sources["ingredients.0.herb_id"]["basis"] == "合成药材对应验证"
    for source in sources.values():
        assert source["evidence_ref"] == first["evidence_ref"]
        assert source["segment_ref"] == first["segment_ref"]
        assert source["source_ref"] == f"{first['source_public']}@1"
        assert source["segment_checksum"] == first["checksum"]
        assert not {"id", "evidence_revision_id", "segment_revision_id", "source_revision_id"} & source.keys()
    assert not re.search(r'"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}"', response.text)
    review_route = f"/api/v1/knowledge/reviews/formula_revision/{first['refs']['formula_revision']}"
    payload = {"decision": "APPROVE", "note": "合成门禁验证，非医学验收"}
    assert client.post(review_route, json=payload).status_code == 403
    evidence_review = client.post(
        f"/api/v1/knowledge/reviews/evidence_revision/{first['evidence_ref']}",
        json=payload, headers=headers)
    assert evidence_review.status_code == 201, evidence_review.text
    # Reading partial sources does not relax the existing review-completeness gate.
    assert client.post(review_route, json=payload, headers=headers).status_code == 409
