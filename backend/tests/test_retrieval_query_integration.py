"""Synthetic spelling/alias boundaries, with the original frozen indexes intact."""

from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from test_initial_corpus_integration import _segment_text
from test_knowledge_publish_integration import FakeEmbedder
from test_retrieval_structured_integration import _approve, _ids, _publish
from test_term_resolution_integration import _batch, _decide

from tcm_platform import main as main_module
from tcm_platform.db import SessionLocal
from tcm_platform.knowledge_service import create_concept, create_evidence, create_relation
from tcm_platform.model_errors import ModelUnavailableError
from tcm_platform.models import (
    ConceptTerm,
    EventLog,
    Evidence,
    EvidenceRevision,
    EvidenceSegmentRef,
    RetrievalBenchmarkRun,
    RetrievalChunk,
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
from tcm_platform.retrieval_query import QUERY_POLICY
from tcm_platform.source_import import SourceMetadata
from tcm_platform.storage import ContentAddressedStore


@pytest.fixture(autouse=True)
def isolated_database():
    with SessionLocal() as session:
        name = session.scalar(text("SELECT current_database()"))
        assert name.startswith("tcm_") and name.endswith("_test"), name


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    sources, proofs, concepts = [], [], []
    for index, phrase in enumerate(("醫药脈", "医藥脉")):
        path = tmp_path / f"glyph-{index}.txt"
        path.write_text(f"合成{phrase}，只用于测试。\n\n合成羣峯，独立关系依据。\n\n"
                        "合成發髮後臟朮，歧义及待审原文。", encoding="utf-8")
        source, rows = _segment_text(
            path, ContentAddressedStore(tmp_path / f"store-{index}"),
            SourceMetadata(source_type="OTHER", title=f"合成字形范围{index}",
                           era=f"合成时代{index}"), monkeypatch,
        )
        evidence = [create_evidence([row.id], strength="DIRECT") for row in rows]
        for proof in evidence[:2]:
            _approve("evidence_revision", proof)
        concept = create_concept("独立规范概念", concept_type="PATTERN" if index == 0 else "DISEASE",
                                 terms=("獨有別詞",), evidence_revision_id=evidence[0],
                                 era=f"合成时代{index}")
        with SessionLocal.begin() as session:
            session.add(ConceptTerm(concept_id=concept, term="錯误时代藥词", term_kind="ALIAS",
                                    era="其他时代"))
        _approve("concept", concept)
        endpoint = create_concept("合成端点", concept_type="PATTERN", evidence_revision_id=evidence[1])
        _approve("concept", endpoint)
        relation = create_relation(concept, endpoint, relation_type="RELATED_TO",
                                   assertion_text="合成候选关系", evidence_revision_id=evidence[1])
        _approve("relation", relation)
        sources.append(source.source_id)
        proofs.append(evidence)
        concepts.append(concept)
    return {"sources": sources, "proofs": proofs, "concepts": concepts, "pair": _publish()}


def _search(corpus, query, **kwargs):
    return search_published(query, knowledge_version_id=corpus["pair"][0],
                            index_build_id=corpus["pair"][1],
                            source_ids=kwargs.pop("source_ids", corpus["sources"]), limit=100, **kwargs)


def test_mixed_spellings_match_exact_fts_and_variants_without_rewriting_index(corpus):
    with SessionLocal() as session:
        before = list(session.execute(select(RetrievalChunk.id, RetrievalChunk.chunk_text,
                                              RetrievalChunk.token_text).where(
            RetrievalChunk.index_build_id == corpus["pair"][1]).order_by(RetrievalChunk.id)))
    # Frozen chunks include the neighboring context, which is searchable too.
    expected = {proof for row in corpus["proofs"] for proof in row[:2]}
    for query in ("合成医药脉", "合成醫藥脈", "合成医藥脈", "  合成醫药脈  "):
        results = _search(corpus, query)
        assert _ids(results, "exact") == _ids(results, "fts") == expected
        assert all(r["query_text"] == query and r["query_expansion"]["policy"] == QUERY_POLICY
                   and r["quote_text"].startswith("合成") for r in results)
    expected_variants = expected
    results = _search(corpus, "合成群峰")
    assert _ids(results, "exact") == _ids(results, "fts") == expected_variants
    with SessionLocal() as session:
        after = list(session.execute(select(RetrievalChunk.id, RetrievalChunk.chunk_text,
                                             RetrievalChunk.token_text).where(
            RetrievalChunk.index_build_id == corpus["pair"][1]).order_by(RetrievalChunk.id)))
    assert before == after
    assert _search(corpus, "合成发后脏术") == []
    assert _search(corpus, "未知别名") == []


def test_own_terms_and_relation_scope_preserve_distinct_identities(corpus):
    both = _search(corpus, "独有别词")
    assert _ids(both, "structured") == {row[0] for row in corpus["proofs"]}
    assert _ids(both, "relation") == {row[1] for row in corpus["proofs"]}
    only = _search(corpus, "獨有别詞", source_ids=corpus["sources"][:1])
    assert _ids(only, "structured") == {corpus["proofs"][0][0]}
    assert _ids(only, "relation") == {corpus["proofs"][0][1]}
    assert all(UUID(r["source_id"]) == corpus["sources"][0] for r in only)
    assert not _ids(_search(corpus, "錯误时代藥词"), "structured")
    assert not _ids(_search(corpus, "不存在历史词"), "relation")
    assert _search(corpus, "医药脉", source_ids=[]) == []
    with pytest.raises(PermissionError, match="scope exceeds"):
        _search(corpus, "医药脉", source_ids=[uuid4()])


def test_expansion_keeps_frozen_proof_when_new_evidence_replaces_it(corpus):
    old = corpus["proofs"][0][0]
    with SessionLocal() as session:
        identity = session.get(EvidenceRevision, old).evidence_id
        segment = session.scalar(select(EvidenceSegmentRef.segment_revision_id).where(
            EvidenceSegmentRef.evidence_revision_id == old))
    replacement = create_evidence([segment], strength="INDIRECT", evidence_id=identity)
    _approve("evidence_revision", replacement)
    newer = _publish()
    results = _search(corpus, "独有别词", source_ids=corpus["sources"][:1])
    assert _ids(results, "structured") == {old}
    corpus["pair"] = newer
    assert not _ids(_search(corpus, "独有别词", source_ids=corpus["sources"][:1]), "structured")
    assert _ids(_search(corpus, "医药脉", source_ids=corpus["sources"][:1]), "exact") == {
        replacement, corpus["proofs"][0][1]}


def test_model_fault_and_http_local_path_use_same_spelling_candidates(corpus, monkeypatch):
    class BrokenEmbedder(FakeEmbedder):
        def embed(self, texts):
            raise ModelUnavailableError("synthetic fault")

    original = "  合成醫药脈  "
    local = _search(corpus, original)
    execution = RetrievalExecution()
    assert _search(corpus, original, embedder=BrokenEmbedder(), allow_model_fallback=True,
                   execution=execution) == local
    assert execution.mode == "DEGRADED"
    with pytest.raises(ModelUnavailableError):
        _search(corpus, original, embedder=BrokenEmbedder())
    def forbidden():
        pytest.fail("local API must not load credentials")
    monkeypatch.setattr(main_module, "cloud_clients_from_environment", forbidden)
    with TestClient(main_module.app, base_url="http://127.0.0.1:8000") as client:
        body = client.get("/api/v1/retrieval/query", params={"query": original, "limit": 100}).json()
    assert body["query_text"] == original and body["normalized_query"] == original.strip()
    unscoped = search_published(original, limit=100)
    assert body["mode"] == "LOCAL" and len(body["results"]) == len(unscoped)
    assert [r["quote_text"] for r in body["results"]] == [r["quote_text"] for r in unscoped]
    assert all("evidence_revision_id" not in r for r in body["results"])


def test_research_and_benchmark_record_policy_and_keep_strict_model_failures(corpus):
    query = "  独有别词  "
    task = create_research_task(query, source_ids=corpus["sources"][:1])
    start_research_task(task, model_version="test/query-planner")
    save_research_plan(task, {"subquestions": [query]})
    # Changing the active pair cannot redirect the already frozen research task.
    frozen = corpus["pair"]
    _publish()
    assert retrieve_for_task(task, embedder=FakeEmbedder()) == 2
    with SessionLocal() as session:
        pool = set(session.scalars(select(TaskEvidenceRef.evidence_revision_id).where(
            TaskEvidenceRef.task_id == task)))
        audit = session.scalar(select(EventLog).where(EventLog.aggregate_id == str(task),
            EventLog.event_type == "research_task.evidence_retrieved").order_by(
                EventLog.sequence_no.desc()))
    assert pool == set(corpus["proofs"][0][:2])
    assert audit.payload["query_expansion"]["policy"] == QUERY_POLICY
    assert audit.payload["query"] == query.strip()  # Existing task input trimming.
    query_id = create_golden_query("独有别词", {corpus["proofs"][0][0]: "GOLD"},
                                   source_ids=corpus["sources"][:1])
    measured = run_benchmark(embedder=FakeEmbedder(), k=100)
    assert measured["knowledge_version_id"] != str(frozen[0])
    row = next(r for r in measured["queries"] if r["query_id"] == str(query_id))
    assert row["recall_at_k"] == 1 and row["query_expansion"]["policy"] == QUERY_POLICY
    with SessionLocal() as session:
        stored = session.get(RetrievalBenchmarkRun, UUID(measured["run_id"]))
        assert stored.metrics == {k: v for k, v in measured.items()
                                  if k not in {"run_id", "knowledge_version_id", "index_build_id", "k"}}
    class BrokenEmbedder(FakeEmbedder):
        def embed(self, texts):
            raise ModelUnavailableError("synthetic fault")
    with pytest.raises(ModelUnavailableError):
        retrieve_for_task(task, embedder=BrokenEmbedder())
    with pytest.raises(ModelUnavailableError):
        run_benchmark(embedder=BrokenEmbedder())


def test_adjudicated_historical_alias_never_propagates_to_comparison_identity(tmp_path, monkeypatch):
    _, candidate, source = _batch(tmp_path, monkeypatch, era="合成时代甲", ambiguous=True)
    _, _, comparison = _batch(tmp_path, monkeypatch, era="合成时代乙")
    for spec in (source, comparison):
        _approve("evidence_revision", spec.evidence_revision_id)
    compared = create_concept("独立比較詞", concept_type="CONDITION",
                              evidence_revision_id=comparison.evidence_revision_id, era="合成时代乙")
    _approve("concept", compared)
    before = _publish()
    unresolved = _decide(candidate, source, decision="UNRESOLVED")
    with pytest.raises(ValueError, match="unresolved"):
        _approve("concept", unresolved)
    resolved = _decide(candidate, source, decision="HISTORICAL_SYNONYM",
                       related_concept_id=compared, sources=(source, comparison))
    _approve("concept", resolved)
    pair = _publish()
    with SessionLocal() as session:
        ids = [session.scalar(select(Evidence.source_id).join(EvidenceRevision,
            EvidenceRevision.evidence_id == Evidence.id).where(EvidenceRevision.id == proof))
               for proof in (source.evidence_revision_id, comparison.evidence_revision_id)]
    corpus = {"pair": pair, "sources": ids}
    assert _ids(_search(corpus, "合成原词"), "structured") == {source.evidence_revision_id}
    assert not _ids(_search(corpus, "合成原词", source_ids=ids[1:]), "structured")
    assert _ids(_search(corpus, "独立比较词", source_ids=ids[:1]), "structured") == {
        source.evidence_revision_id}
    corpus["pair"] = before
    assert not _ids(_search(corpus, "合成原词"), "structured")
