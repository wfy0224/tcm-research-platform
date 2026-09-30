"""Synthetic diversity, frozen proof identity and durable ranking checks."""

from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from test_initial_corpus_integration import _segment_text
from test_knowledge_publish_integration import FakeEmbedder
from test_retrieval_structured_integration import _approve, _publish

from tcm_platform import main as main_module
from tcm_platform.db import SessionLocal
from tcm_platform.knowledge_service import create_concept, create_evidence
from tcm_platform.model_errors import ModelUnavailableError
from tcm_platform.models import (
    EventLog,
    EvidenceRetrievalEvent,
    EvidenceRevision,
    RetrievalBenchmarkRun,
    TaskEvidenceRef,
)
from tcm_platform.research_service import (
    create_research_task,
    retrieve_for_task,
    save_research_plan,
    start_research_task,
)
from tcm_platform.retrieval import RetrievalExecution, search_published
from tcm_platform.retrieval_benchmark import create_golden_query, run_benchmark
from tcm_platform.retrieval_diversity import DIVERSITY_POLICY
from tcm_platform.source_import import SourceMetadata
from tcm_platform.storage import ContentAddressedStore


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    with SessionLocal() as session:
        name = session.scalar(text("SELECT current_database()"))
        assert name.startswith("tcm_") and name.endswith("_test")
    query = f"合成多样性{uuid4().hex}"
    sources, segments, proofs = [], [], []
    for index in range(3):
        path = tmp_path / f"diversity-{index}.txt"
        path.write_text(
            f"{query}。" + "合成补充文字。" * index
            + f"\n\n{query}，合成独立论据甲。\n\n{query}，合成独立论据乙。",
            encoding="utf-8",
        )
        source, rows = _segment_text(
            path, ContentAddressedStore(tmp_path / f"store-{index}"),
            SourceMetadata(source_type="OTHER", title=f"合成多样性来源{index}"), monkeypatch,
        )
        # More than the old pre-rerank cap: independent proofs of one passage.
        selected = [rows[0]] * 24 + rows[1:] if index == 0 else [rows[0]]
        ids = [create_evidence([row.id], strength="DIRECT") for row in selected]
        for identity in ids:
            _approve("evidence_revision", identity)
        sources.append(source)
        segments.append(rows)
        proofs.append(ids)
    concept = create_concept(query, concept_type="UNKNOWN", evidence_revision_id=proofs[0][0])
    _approve("concept", concept)
    return {"query": query, "sources": sources, "segments": segments,
            "proofs": proofs, "pair": _publish()}


def _search(corpus, *, sources=None, pair=None, **kwargs):
    pair = pair or corpus["pair"]
    return search_published(
        f"  {corpus['query']}  ", source_ids=(sources if sources is not None else
                                              [s.source_id for s in corpus["sources"]]),
        knowledge_version_id=pair[0], index_build_id=pair[1], **kwargs,
    )


def test_diversity_prevents_one_source_occupying_bounded_candidate_pool(corpus):
    results = _search(corpus, limit=3)
    assert len(results) == 3
    assert {UUID(r["source_id"]) for r in results} == {s.source_id for s in corpus["sources"]}
    assert all(r["diversity"]["source_occurrence"] == 1 for r in results)
    assert all(r["diversity"]["policy"] == DIVERSITY_POLICY for r in results)
    assert _search(corpus, limit=3) == results  # Stable channel ties and diversity ties.
    assert all(r["query_text"] == f"  {corpus['query']}  " for r in results)


def test_single_source_prefers_distinct_context_and_backfills_exact_proofs(corpus):
    scope = [corpus["sources"][0].source_id]
    top = _search(corpus, sources=scope, limit=3)
    assert len({tuple(r["segment_revision_ids"]) for r in top}) == 3
    all_results = _search(corpus, sources=scope, limit=100)
    assert {UUID(r["evidence_revision_id"]) for r in all_results} == set(corpus["proofs"][0])
    assert len(all_results) == 26
    assert all(r["diversity"]["context_overlap"] == 0 for r in all_results[:3])
    assert all(r["diversity"]["context_overlap"] > 0 for r in all_results[3:])
    assert [r["diversity"]["source_occurrence"] for r in all_results] == list(range(1, 27))
    multichannel = next(r for r in all_results
                        if UUID(r["evidence_revision_id"]) == corpus["proofs"][0][0])
    assert {"exact", "fts", "structured"}.issubset(multichannel["matched_channels"])
    assert len(multichannel["matched_channels"]) == len(set(multichannel["matched_channels"]))


def test_diversity_keeps_old_snapshot_revisions_and_rejects_scope_expansion(corpus):
    original = corpus["proofs"][0][0]
    with SessionLocal() as session:
        evidence = session.get(EvidenceRevision, original).evidence_id
    replacement = create_evidence([corpus["segments"][0][0].id], strength="INDIRECT",
                                  evidence_id=evidence)
    _approve("evidence_revision", replacement)
    newer = _publish()
    old_ids = {UUID(r["evidence_revision_id"]) for r in _search(corpus, limit=100)}
    new_ids = {UUID(r["evidence_revision_id"]) for r in _search(corpus, pair=newer, limit=100)}
    assert original in old_ids and replacement not in old_ids
    assert replacement in new_ids and original not in new_ids
    with pytest.raises(PermissionError, match="scope exceeds"):
        _search(corpus, sources=[uuid4()], limit=3)


def test_empty_scope_does_not_call_model_for_diversity(corpus):
    class NeverEmbedder(FakeEmbedder):
        def embed(self, texts):
            pytest.fail("empty scope must not invoke a model")
    assert _search(corpus, sources=[], embedder=NeverEmbedder(), limit=3) == []


def test_embedding_fallback_uses_identical_local_diversity(corpus):
    class BrokenEmbedder(FakeEmbedder):
        def embed(self, texts):
            raise ModelUnavailableError("synthetic unavailable")
    status = RetrievalExecution()
    assert _search(corpus, embedder=BrokenEmbedder(), allow_model_fallback=True,
                   execution=status, limit=3) == _search(corpus, limit=3)
    assert status.mode == "DEGRADED" and status.reasons == ["embedding_unavailable"]


@pytest.mark.parametrize("broken", [False, True])
def test_rerank_and_fault_apply_final_diversity_with_safe_score_scales(corpus, broken):
    class SyntheticReranker:
        model_version = "test/diversity-rerank"

        def rerank(self, query, documents):
            if broken:
                raise ModelUnavailableError("synthetic rerank failure")
            # Every score is negative; v1 uses ranks rather than dividing scores.
            return [(index, -float(len(doc))) for index, doc in enumerate(documents)]

    pair = _publish({"rerank_model": SyntheticReranker.model_version})
    status = RetrievalExecution()
    results = _search(corpus, pair=pair, embedder=FakeEmbedder(), reranker=SyntheticReranker(),
                      allow_model_fallback=True, execution=status, limit=3)
    assert len({r["source_id"] for r in results}) == 3
    assert all(r["diversity"]["selection_score"] > 0 for r in results)
    assert all((r["rerank_score"] is None) == broken for r in results)
    assert status.mode == ("DEGRADED" if broken else "HYBRID")
    assert status.reasons == (["rerank_unavailable"] if broken else [])


def test_api_exposes_safe_explanations_and_keeps_legacy_array(corpus):
    with TestClient(main_module.app, base_url="http://127.0.0.1:8000") as client:
        params = {"query": corpus["query"], "limit": 3, "mode": "local"}
        body = client.get("/api/v1/retrieval/query", params=params)
        assert body.status_code == 200
        results = body.json()["results"]
        assert len({r["source_id"] for r in results}) == 3
        assert all(r["diversity"]["policy"] == DIVERSITY_POLICY for r in results)
        assert all("evidence_revision_id" not in r["diversity"] for r in results)
        assert client.get("/api/v1/retrieval/search", params=params).json() == results


def test_research_pool_persists_actual_rank_channels_and_explanations(corpus):
    task = create_research_task(corpus["query"],
                                source_ids=[s.source_id for s in corpus["sources"]])
    start_research_task(task, model_version="test/diversity-planner")
    save_research_plan(task, {"subquestions": [corpus["query"]]})
    assert retrieve_for_task(task, embedder=FakeEmbedder(), limit=3) == 3
    assert retrieve_for_task(task, embedder=FakeEmbedder(), limit=3) == 0
    with SessionLocal() as session:
        events = list(session.scalars(select(EvidenceRetrievalEvent).where(
            EvidenceRetrievalEvent.task_id == task).order_by(EvidenceRetrievalEvent.rank)))
        pool = list(session.scalars(select(TaskEvidenceRef).where(TaskEvidenceRef.task_id == task)))
        audit = session.scalar(select(EventLog).where(
            EventLog.aggregate_id == str(task),
            EventLog.event_type == "research_task.evidence_retrieved",
        ).order_by(EventLog.sequence_no.desc()))
    assert len(events) == len(pool) == 3
    assert [e.rank for e in events] == [1, 2, 3]
    assert [e.evidence_revision_id for e in events] == [
        UUID(r["evidence_revision_id"]) for r in audit.payload["ranking"]]
    assert all("vector" in e.channels for e in events)
    assert all(r["policy"] == DIVERSITY_POLICY for r in audit.payload["ranking"])


def test_benchmark_preserves_metrics_and_records_diverse_exact_ranking(corpus):
    labels = {corpus["proofs"][1][0]: "GOLD", corpus["proofs"][2][0]: "COUNTER"}
    query_id = create_golden_query(corpus["query"], labels,
                                   source_ids=[s.source_id for s in corpus["sources"]])
    result = run_benchmark(embedder=FakeEmbedder(), k=3)
    measured = next(row for row in result["queries"] if row["query_id"] == str(query_id))
    assert measured["recall_at_k"] == measured["counter_evidence_recall_at_k"] == 1
    assert measured["evidence_resolution_rate"] == 1
    assert len(measured["ranking"]) == 3
    assert result["ranking_policy"] == DIVERSITY_POLICY
    assert all(isinstance(value, float) for value in result["aggregate"].values())
    with SessionLocal() as session:
        stored = session.get(RetrievalBenchmarkRun, UUID(result["run_id"]))
        assert stored.metrics["queries"] == result["queries"]
        assert stored.metrics["ranking_policy"] == DIVERSITY_POLICY
