"""Isolated synthetic triage checks; no medical relevance or cloud qualification."""

import json
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from test_initial_corpus_integration import _process_target, _segment_text
from test_knowledge_publish_integration import FakeEmbedder
from test_retrieval_structured_integration import _approve, _publish

from tcm_platform import knowledge_publish, main, retrieval_quality
from tcm_platform.audit import verify_chain
from tcm_platform.db import SessionLocal
from tcm_platform.knowledge_publish import open_quality_issue, resolve_quality_issue, review_object
from tcm_platform.knowledge_service import (
    IngredientSpec,
    create_concept,
    create_evidence,
    create_formula,
    create_herb,
    create_relation,
)
from tcm_platform.model_errors import ModelUnavailableError
from tcm_platform.models import (
    Concept,
    ConceptTerm,
    EventLog,
    EvidenceRevision,
    QualityIssue,
    TaskEvidenceRef,
    TextSegmentRevision,
)
from tcm_platform.research_service import (
    create_research_task,
    retrieve_for_task,
    save_research_plan,
    start_research_task,
)
from tcm_platform.retrieval import search_published
from tcm_platform.source_import import SourceMetadata, import_file
from tcm_platform.storage import ContentAddressedStore


@pytest.fixture
def candidates(tmp_path, monkeypatch):
    with SessionLocal() as session:
        name = session.scalar(text("SELECT current_database()"))
        assert name.startswith("tcm_") and name.endswith("_test"), name
    token = f"合成质量{uuid4().hex}"
    sources, segments, reviewed, drafts = [], [], [], []
    for index in range(2):
        path = tmp_path / f"quality-{index}.txt"
        path.write_text(f"{token} 已发布原文。\n\n{token} 待审原文。\n\n"
                        f"{token} 尚无证据的原文。\n\n无关段落。", encoding="utf-8")
        source, rows = _segment_text(
            path, ContentAddressedStore(tmp_path / f"store-{index}"),
            SourceMetadata(source_type="OTHER", title=f"合成质量来源{index}"), monkeypatch,
        )
        proof = create_evidence([rows[0].id], strength="DIRECT")
        _approve("evidence_revision", proof)
        draft = create_evidence([rows[1].id], strength="DIRECT")
        sources.append(source)
        segments.append(rows)
        reviewed.append(proof)
        drafts.append(draft)
    concept = create_concept(token, concept_type="UNKNOWN", evidence_revision_id=drafts[0])
    endpoint = create_concept("其他端点", concept_type="UNKNOWN", evidence_revision_id=drafts[0])
    relation = create_relation(concept, endpoint, relation_type="RELATED_TO",
                               assertion_text=f"{token} 合成待审关系", evidence_revision_id=drafts[0])
    herb = create_herb(token, evidence_revision_id=drafts[0])
    formula = create_formula(token, evidence_revision_id=drafts[0],
                             ingredients=(IngredientSpec(original_name="合成药味"),))
    pair = _publish()
    return {"token": token, "sources": sources, "segments": segments, "reviewed": reviewed,
            "drafts": drafts, "pair": pair, "concept": concept, "relation": relation,
            "herb": herb, "formula": formula}


def _search(g, query=None, **kwargs):
    return search_published(
        g["token"] if query is None else query, knowledge_version_id=g["pair"][0],
        index_build_id=g["pair"][1], source_ids=[g["sources"][0].source_id], **kwargs,
    )


def _issues(g):
    with SessionLocal() as session:
        return list(session.scalars(select(QualityIssue).where(
            QualityIssue.issue_type == retrieval_quality.ISSUE_TYPE,
            QualityIssue.description.contains(g["token"]),
        ).order_by(QualityIssue.target_kind, QualityIssue.target_id)))


def test_literal_matches_triage_all_kinds_without_returning_drafts(candidates):
    g = candidates
    original = f"  {g['token']}  "
    results = _search(g, original)
    assert {UUID(r["evidence_revision_id"]) for r in results} == {g["reviewed"][0]}
    issues = _issues(g)
    assert {(i.target_kind, i.target_id) for i in issues} == {
        ("evidence_revision", g["drafts"][0]), ("concept", g["concept"]),
        ("relation", g["relation"]), ("herb", g["herb"]),
        ("formula_revision", g["formula"]), ("text_segment_revision", g["segments"][0][2].id),
    }
    for issue in issues:
        detail = json.loads(issue.description)
        assert issue.status == "OPEN" and issue.severity == "WARNING"
        assert detail["query_text"] == original and detail["normalized_query"] == g["token"]
        assert detail["requires_human_review"] and detail["policy"] == retrieval_quality.POLICY
        assert detail["source_revision_id"] == str(g["sources"][0].source_revision_id)
        assert detail["knowledge_version_id"] == str(g["pair"][0])
        assert all(s["checksum"] and s["locator"] for s in detail["segments"])
    with SessionLocal() as session:
        assert session.get(EvidenceRevision, g["drafts"][0]).status == "DRAFT"
        assert session.get(Concept, g["concept"]).status == "DRAFT"
        assert verify_chain(session)


@pytest.mark.parametrize("waive", [False, True])
def test_repeat_queries_preserve_first_observation_and_human_resolution(candidates, waive):
    g = candidates
    _search(g)
    first = _issues(g)
    resolve_quality_issue(first[0].id, reviewer_id="synthetic-reviewer", note="Human triage", waive=waive)
    newer = _publish()
    g["pair"] = newer
    _search(g, f"{g['token']} more words")
    _search(g)
    again = _issues(g)
    assert [i.id for i in again] == [i.id for i in first]
    assert again[0].status == ("WAIVED" if waive else "RESOLVED")
    assert [i.description for i in again] == [i.description for i in first]


def test_concurrent_queries_create_one_issue_and_event_per_target(candidates):
    g = candidates
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda _: _search(g), range(3)))
    assert all(result == results[0] for result in results)
    issues = _issues(g)
    assert len(issues) == 6
    with SessionLocal() as session:
        events = list(session.scalars(select(EventLog).where(
            EventLog.aggregate_id.in_([str(i.id) for i in issues]),
            EventLog.event_type == "quality_issue.opened",
        )))
        assert len(events) == 6 and verify_chain(session)


def test_old_published_revision_stays_visible_while_new_draft_is_triaged(candidates):
    g = candidates
    with SessionLocal() as session:
        identity = session.get(EvidenceRevision, g["reviewed"][0]).evidence_id
    new = create_evidence([g["segments"][0][0].id], strength="INDIRECT", evidence_id=identity)
    results = _search(g)
    assert {UUID(r["evidence_revision_id"]) for r in results} == {g["reviewed"][0]}
    assert new in {i.target_id for i in _issues(g)}
    assert g["reviewed"][0] not in {i.target_id for i in _issues(g)}


def test_unindexed_reviewed_candidate_is_triaged_but_published_history_is_not(candidates):
    g = candidates
    _approve("evidence_revision", g["drafts"][0])
    _search(g)
    assert g["drafts"][0] in {i.target_id for i in _issues(g)}
    newer = _publish()
    g["pair"] = newer
    extra = create_evidence([g["segments"][0][0].id], strength="INDIRECT")
    _approve("evidence_revision", extra)
    _publish()
    _search(g)
    assert extra not in {i.target_id for i in _issues(g)}


def test_same_source_new_revision_and_other_source_cannot_expand_scope(candidates, tmp_path, monkeypatch):
    g = candidates
    path = tmp_path / "quality-0.txt"
    path.write_text(f"{g['token']} 新来源修订。", encoding="utf-8")
    store = ContentAddressedStore(tmp_path / "store-0")
    newer = import_file(
        path, SourceMetadata(source_type="OTHER", title="合成质量来源0"), store=store,
        source_id=g["sources"][0].source_id, request_key=f"quality-revision:{uuid4()}",
    )
    assert _process_target(newer, store, monkeypatch).status == "PARSED"
    assert _process_target(newer, store, monkeypatch, segment=True).status == "SEGMENTED"
    with SessionLocal() as session:
        rows = list(session.scalars(select(TextSegmentRevision).where(
            TextSegmentRevision.source_revision_id == newer.source_revision_id,
            TextSegmentRevision.segment_type == "PARAGRAPH",
        )))
    new_proof = create_evidence([rows[0].id], strength="DIRECT")
    _search(g)
    assert newer.source_revision_id != g["sources"][0].source_revision_id
    assert newer.source_id == g["sources"][0].source_id
    assert new_proof not in {i.target_id for i in _issues(g)}
    assert g["drafts"][1] not in {i.target_id for i in _issues(g)}
    with pytest.raises(PermissionError):
        search_published(g["token"], source_ids=[uuid4()],
                         knowledge_version_id=g["pair"][0], index_build_id=g["pair"][1])


def test_empty_scope_no_hits_and_rejected_candidates_create_no_issues(candidates):
    g = candidates
    assert _search(g, uuid4().hex) == []
    assert search_published(g["token"], source_ids=[], knowledge_version_id=g["pair"][0],
                            index_build_id=g["pair"][1]) == []
    assert _issues(g) == []
    review_object("concept", g["concept"], reviewer_id="synthetic", decision="REJECT", note="Rejected")
    _search(g)
    assert g["concept"] not in {i.target_id for i in _issues(g)}


def test_rejected_evidence_is_not_recreated_as_a_raw_segment_issue(candidates):
    g = candidates
    review_object("evidence_revision", g["drafts"][0], reviewer_id="synthetic", decision="REJECT",
                  note="Rejected evidence must not be reintroduced by raw triage")
    _search(g)
    targets = {i.target_id for i in _issues(g)}
    assert g["drafts"][0] not in targets and g["segments"][0][1].id not in targets


def test_nfkc_own_terms_keep_original_query_and_do_not_follow_outside_proofs(candidates):
    g = candidates
    with SessionLocal.begin() as session:
        session.add(ConceptTerm(concept_id=g["concept"], term="ＡＢＣ", term_kind="ALIAS"))
    outside = create_concept("ＡＢＣ", concept_type="UNKNOWN", evidence_revision_id=g["drafts"][1])
    assert _search(g, " ＡＢＣ ") == []
    with SessionLocal() as session:
        issues = list(session.scalars(select(QualityIssue).where(
            QualityIssue.issue_type == retrieval_quality.ISSUE_TYPE,
            QualityIssue.target_id.in_([g["concept"], outside]),
        )))
        assert len(issues) == 1 and issues[0].target_id == g["concept"]
        detail = json.loads(issues[0].description)
        assert detail["query_text"] == " ＡＢＣ " and detail["normalized_query"] == "ABC"


def test_sentence_evidence_does_not_create_duplicate_parent_segment_issue(candidates):
    g = candidates
    parent = g["segments"][0][2]
    with SessionLocal() as session:
        child = session.scalar(select(TextSegmentRevision).where(
            TextSegmentRevision.source_revision_id == parent.source_revision_id,
            TextSegmentRevision.parent_segment_id == parent.segment_id,
            TextSegmentRevision.segment_type == "SENTENCE",
        ))
        assert child is not None
    proof = create_evidence([child.id], strength="DIRECT")
    _search(g)
    targets = {i.target_id for i in _issues(g)}
    assert proof in targets and parent.id not in targets and child.id not in targets


def test_outer_commentary_note_case_and_formula_segments_are_triaged_once(tmp_path, monkeypatch):
    token = f"合成外层片段{uuid4().hex}"
    path = tmp_path / "raw-kinds.txt"
    path.write_text("合成发布基线。\n\n" + "\n\n".join(
        f"{prefix}{token} 待核对原文。" for prefix in ("按语：", "注：", "医案：", "方：")
    ), encoding="utf-8")
    source, rows = _segment_text(path, ContentAddressedStore(tmp_path / "store"),
                                  SourceMetadata(source_type="OTHER", title="合成外层片段"), monkeypatch)
    proof = create_evidence([rows[0].id], strength="DIRECT")
    _approve("evidence_revision", proof)
    pair = _publish()
    search_published(token, source_ids=[source.source_id], knowledge_version_id=pair[0],
                     index_build_id=pair[1])
    with SessionLocal() as session:
        issues = list(session.scalars(select(QualityIssue).where(
            QualityIssue.issue_type == retrieval_quality.ISSUE_TYPE,
            QualityIssue.description.contains(token),
        )))
        assert len(issues) == 4 and all(i.target_kind == "text_segment_revision" for i in issues)
        kinds = {session.get(TextSegmentRevision, i.target_id).segment_type for i in issues}
        assert kinds == {"COMMENTARY", "NOTE", "CASE_NOTE", "FORMULA_TEXT"}


def test_unpublished_only_query_returns_empty_but_creates_quality_issue(candidates):
    g = candidates
    assert _search(g, "尚无证据的原文") == []
    with SessionLocal() as session:
        issue = session.scalar(select(QualityIssue).where(
            QualityIssue.issue_type == retrieval_quality.ISSUE_TYPE,
            QualityIssue.target_id == g["segments"][0][2].id,
        ))
        assert issue is not None and issue.target_kind == "text_segment_revision"


@pytest.mark.parametrize("phase", ["embedding", "rerank"])
def test_fallback_triages_locally_and_never_sends_drafts_to_model(candidates, phase):
    g = candidates
    class QueryEmbedder(FakeEmbedder):
        def embed(self, texts):
            assert texts == [g["token"]]
            if phase == "embedding":
                raise ModelUnavailableError("Synthetic unavailable")
            return super().embed(texts)

    class Reranker:
        model_version = "test/quality-rerank"

        def rerank(self, query, documents):
            assert len(documents) == 1 and "已发布原文" in documents[0]
            assert "待审原文" not in documents[0]
            raise ModelUnavailableError("Synthetic unavailable")

    if phase == "rerank":
        g["pair"] = _publish({"rerank_model": Reranker.model_version})
    with pytest.raises(ModelUnavailableError):
        _search(g, embedder=QueryEmbedder(), reranker=Reranker() if phase == "rerank" else None)
    assert _issues(g) == []
    _search(g, embedder=QueryEmbedder(), reranker=Reranker() if phase == "rerank" else None,
            allow_model_fallback=True)
    assert len(_issues(g)) == 6


def test_batch_rolls_back_on_audit_failure_and_does_not_degrade(candidates, monkeypatch):
    g = candidates
    append = knowledge_publish.append_event
    count = 0

    def broken(*args, **kwargs):
        nonlocal count
        count += 1
        if count == 2:
            raise RuntimeError("Synthetic audit failure")
        return append(*args, **kwargs)

    monkeypatch.setattr(knowledge_publish, "append_event", broken)
    with pytest.raises(RuntimeError, match="audit failure"):
        _search(g, allow_model_fallback=True)
    assert _issues(g) == []
    with SessionLocal() as session:
        assert verify_chain(session)


def test_bound_does_not_starve_remaining_targets(candidates, monkeypatch):
    g = candidates
    monkeypatch.setattr(retrieval_quality, "MAX_MATCHES", 2)
    for count in (2, 4, 6, 6):
        _search(g)
        assert len(_issues(g)) == count


def test_existing_blocker_and_evidence_first_review_gates_remain(candidates):
    g = candidates
    _search(g)
    with pytest.raises(ValueError, match="evidence must be reviewed first"):
        _approve("concept", g["concept"])
    blocker = open_quality_issue("evidence_revision", g["drafts"][0], issue_type="MANUAL_CHECK",
                                 severity="BLOCKER", description="Synthetic manual blocker")
    try:
        with pytest.raises(ValueError, match="open blocker"):
            _approve("evidence_revision", g["drafts"][0])
    finally:
        resolve_quality_issue(blocker, reviewer_id="synthetic", note="Synthetic cleanup")


def test_api_keeps_quality_details_private(candidates, monkeypatch):
    g = candidates
    monkeypatch.setattr(main, "cloud_clients_from_environment",
                        lambda: pytest.fail("Local API must not read credentials"))
    with TestClient(main.app, base_url="http://127.0.0.1:8000") as client:
        response = client.get("/api/v1/retrieval/query", params={"query": g["token"], "mode": "local"})
        assert response.status_code == 200
        assert len(_issues(g)) >= 6  # API uses all sources in the frozen active build.
        assert "requires_human_review" not in response.text
        assert all(r["quote_text"].endswith("已发布原文。") for r in response.json()["results"])


def test_research_triages_with_task_context_and_pool_remains_published(candidates):
    g = candidates
    task = create_research_task(g["token"], source_ids=[g["sources"][0].source_id])
    start_research_task(task, model_version="test/quality-generation")
    save_research_plan(task, {"subquestions": [g["token"]]})
    assert retrieve_for_task(task, embedder=FakeEmbedder()) == 1
    with SessionLocal() as session:
        pool = set(session.scalars(select(TaskEvidenceRef.evidence_revision_id).where(
            TaskEvidenceRef.task_id == task,
        )))
        assert pool == {g["reviewed"][0]}
    assert len(_issues(g)) == 6
    assert all(json.loads(i.description)["task_id"] == str(task) for i in _issues(g))
