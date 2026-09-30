"""Synthetic publication/scope checks; no real terminology or model quality claims."""

from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from test_initial_corpus_integration import _segment_text
from test_knowledge_publish_integration import FakeEmbedder
from test_term_resolution_integration import _batch, _decide

from tcm_platform import main as main_module
from tcm_platform.db import SessionLocal
from tcm_platform.knowledge_extraction import extract_source_candidates
from tcm_platform.knowledge_publish import (
    activate_knowledge_version,
    create_index_build,
    create_knowledge_version,
    review_object,
)
from tcm_platform.knowledge_service import create_concept, create_evidence, create_relation
from tcm_platform.model_errors import (
    ModelCredentialMissing,
    ModelCredentialUnavailable,
    ModelResponseError,
    ModelUnavailableError,
)
from tcm_platform.models import (
    ConceptTerm,
    Evidence,
    EvidenceRetrievalEvent,
    EvidenceRevision,
    IndexBuild,
)
from tcm_platform.research_service import (
    create_research_task,
    retrieve_for_task,
    save_research_plan,
    start_research_task,
)
from tcm_platform.retrieval import RetrievalExecution, build_retrieval_index, search_published
from tcm_platform.source_import import SourceMetadata
from tcm_platform.storage import ContentAddressedStore


@pytest.fixture(autouse=True)
def isolated_database():
    with SessionLocal() as session:
        name = session.scalar(text("SELECT current_database()"))
        assert name.startswith("tcm_") and name.endswith("_test"), name


def _approve(kind, identity):
    review_object(kind, identity, reviewer_id="synthetic-curator", decision="APPROVE",
                  note="Synthetic retrieval engineering validation only")


def _publish(configuration=None):
    version = create_knowledge_version()
    build = create_index_build(version, configuration={
        "strategy": "hybrid-v1", "embedding_model": FakeEmbedder.model_version,
        **(configuration or {}),
    })
    build_retrieval_index(build, embedder=FakeEmbedder())
    activate_knowledge_version(version, build)
    return version, build


def _search(query, pair, sources):
    return search_published(query, embedder=FakeEmbedder(), limit=100,
                            knowledge_version_id=pair[0], index_build_id=pair[1],
                            source_ids=sources)


def _ids(results, channel):
    return {UUID(r["evidence_revision_id"]) for r in results if channel in r["matched_channels"]}


@pytest.fixture
def graph(tmp_path, monkeypatch):
    alias = f"合成查询{uuid4().hex}"
    imported, segments, evidence = [], [], []
    for index in range(2):
        path = tmp_path / f"scope-{index}.txt"
        path.write_text("合成锚点甲，保留原文。\n\n合成关系依据乙。\n\n合成待审依据丙。",
                        encoding="utf-8")
        source, rows = _segment_text(
            path, ContentAddressedStore(tmp_path / f"store-{index}"),
            SourceMetadata(source_type="OTHER", title=f"合成检索范围{index}",
                           era=f"合成时代{index}"), monkeypatch,
        )
        proofs = [create_evidence([s.id], strength="DIRECT") for s in rows]
        for proof in proofs:
            _approve("evidence_revision", proof)
        imported.append(source)
        segments.append(rows)
        evidence.append(proofs)
    first = create_concept(alias, concept_type="PATTERN", terms=("ＡＢＣ", "安全别名"),
                           evidence_revision_id=evidence[0][0], era="合成时代0")
    # A mismatched term is never an authorization to cross era/school boundaries.
    with SessionLocal.begin() as session:
        session.add(ConceptTerm(concept_id=first, term="错误时代词", term_kind="ALIAS",
                                era="合成时代1", school=None))
    second = create_concept(alias, concept_type="DISEASE", evidence_revision_id=evidence[1][0],
                            era="合成时代1")
    endpoint = create_concept("合成关系端点", concept_type="PATTERN",
                              evidence_revision_id=evidence[0][1])
    for concept in (first, second, endpoint):
        _approve("concept", concept)
    relation = create_relation(first, endpoint, relation_type="RELATED_TO",
                                assertion_text="合成关系，不作为真实医学知识",
                                evidence_revision_id=evidence[0][1])
    _approve("relation", relation)
    draft = create_concept(alias, concept_type="UNKNOWN", evidence_revision_id=evidence[0][2])
    draft_relation = create_relation(first, endpoint, relation_type="RELATED_TO",
                                      assertion_text="未审关系", evidence_revision_id=evidence[0][2])
    pair = _publish()
    return {"alias": alias, "sources": imported, "segments": segments, "evidence": evidence,
            "first": first, "second": second, "endpoint": endpoint, "draft": draft,
            "draft_relation": draft_relation, "pair": pair}


def test_structured_relation_and_same_term_identities_stay_in_scope(graph):
    g = graph
    both = _search(g["alias"], g["pair"], [s.source_id for s in g["sources"]])
    assert _ids(both, "structured") == {g["evidence"][0][0], g["evidence"][1][0]}
    assert _ids(both, "relation") == {g["evidence"][0][1]}
    scoped = _search(g["alias"], g["pair"], [g["sources"][0].source_id])
    assert _ids(scoped, "structured") == {g["evidence"][0][0]}
    assert _ids(scoped, "relation") == {g["evidence"][0][1]}
    assert {UUID(r["source_id"]) for r in scoped} == {g["sources"][0].source_id}
    assert all(len(r["matched_channels"]) == len(set(r["matched_channels"])) for r in both)


def test_later_review_and_active_switch_do_not_change_frozen_candidates(graph):
    g = graph
    _approve("concept", g["draft"])
    _approve("relation", g["draft_relation"])
    newer = _publish()
    sources = [g["sources"][0].source_id]
    old = _search(g["alias"], g["pair"], sources)
    new = _search(g["alias"], newer, sources)
    assert g["evidence"][0][2] not in _ids(old, "structured") | _ids(old, "relation")
    assert g["evidence"][0][2] in _ids(new, "structured") & _ids(new, "relation")


def test_historical_evidence_link_never_substitutes_latest_revision(graph):
    g = graph
    with SessionLocal() as session:
        identity = session.get(EvidenceRevision, g["evidence"][0][0]).evidence_id
    replacement = create_evidence([g["segments"][0][0].id], strength="INDIRECT", evidence_id=identity)
    _approve("evidence_revision", replacement)
    newer = _publish()
    sources = [g["sources"][0].source_id]
    old = _search(g["alias"], g["pair"], sources)
    new = _search(g["alias"], newer, sources)
    assert _ids(old, "structured") == {g["evidence"][0][0]}
    assert not _ids(new, "structured")
    assert replacement in {UUID(r["evidence_revision_id"]) for r in new}
    assert not _ids(new, "relation")  # The query anchor itself is no longer published.


def test_empty_scope_returns_no_results_or_model_call(graph):
    class NeverEmbedder(FakeEmbedder):
        def embed(self, texts):
            pytest.fail("an empty scope must not invoke a model")

    assert search_published(graph["alias"], embedder=NeverEmbedder(), source_ids=[],
                            knowledge_version_id=graph["pair"][0],
                            index_build_id=graph["pair"][1]) == []


def _local_search(graph, query=None, **kwargs):
    return search_published(
        graph["alias"] if query is None else query,
        knowledge_version_id=graph["pair"][0], index_build_id=graph["pair"][1],
        source_ids=[graph["sources"][0].source_id], limit=100, **kwargs,
    )


def test_local_search_keeps_frozen_scope_proofs_and_query(graph):
    original = f"  {graph['alias']} ＡＢＣ  "
    execution = RetrievalExecution()
    results = _local_search(graph, original, execution=execution)
    assert _ids(results, "structured") == {graph["evidence"][0][0]}
    assert _ids(results, "relation") == {graph["evidence"][0][1]}
    assert {UUID(r["source_id"]) for r in results} == {graph["sources"][0].source_id}
    assert all("vector" not in r["matched_channels"] and r["rerank_score"] is None
               and r["query_text"] == original for r in results)
    assert execution.mode == "LOCAL" and not execution.reasons
    assert execution.knowledge_version_id == graph["pair"][0]
    lexical = _local_search(graph, "合成锚点甲")
    assert graph["evidence"][0][0] in _ids(lexical, "exact") & _ids(lexical, "fts")
    assert _local_search(graph, "' OR TRUE --") == []


@pytest.mark.parametrize("failure", [ModelUnavailableError, ModelResponseError, TimeoutError])
def test_embedding_fault_falls_back_only_when_requested(graph, failure):
    class BrokenEmbedder(FakeEmbedder):
        def embed(self, texts):
            raise failure("private provider details must not reach status")

    with pytest.raises(failure):
        _local_search(graph, embedder=BrokenEmbedder())
    execution = RetrievalExecution()
    local = _local_search(graph)
    fallback = _local_search(graph, embedder=BrokenEmbedder(), allow_model_fallback=True,
                             execution=execution)
    assert fallback == local
    assert execution.mode == "DEGRADED" and execution.reasons == ["embedding_unavailable"]
    assert "vector" not in execution.channels


def test_invalid_embedding_and_internal_failure_are_distinguished(graph):
    class InvalidEmbedder(FakeEmbedder):
        def embed(self, texts):
            return [[float("nan"), 1.0]]

    execution = RetrievalExecution()
    assert _local_search(graph, embedder=InvalidEmbedder(), allow_model_fallback=True,
                          execution=execution) == _local_search(graph)
    assert execution.reasons == ["embedding_unavailable"]

    class InternalFailure(FakeEmbedder):
        def embed(self, texts):
            raise RuntimeError("audit storage failure")

    with pytest.raises(RuntimeError, match="audit storage"):
        _local_search(graph, embedder=InternalFailure(), allow_model_fallback=True)


@pytest.mark.parametrize("consent", [False, True])
def test_policy_denial_falls_back_without_remote_call(graph, consent):
    class RemoteEmbedder(FakeEmbedder):
        is_remote = True
        endpoint = "https://api.siliconflow.cn/v1/embeddings"

        def embed(self, texts):
            pytest.fail("denied outbound request must not invoke the remote adapter")

    graph["pair"] = _publish({"embedding_endpoint": RemoteEmbedder.endpoint})
    with pytest.raises(PermissionError):
        _local_search(graph, embedder=RemoteEmbedder(), query_outbound_authorized=consent)
    execution = RetrievalExecution()
    assert _local_search(graph, embedder=RemoteEmbedder(), query_outbound_authorized=consent,
                          allow_model_fallback=True, execution=execution) == _local_search(graph)
    assert execution.reasons == ["outbound_policy_blocked" if consent
                                 else "remote_query_not_authorized"]


@pytest.mark.parametrize("invalid", [False, True])
def test_rerank_fault_preserves_vector_fusion(graph, invalid):
    class BrokenReranker:
        model_version = "test/rerank-fault"

        def rerank(self, query, documents):
            if invalid:
                return [(len(documents), float("nan"))]
            raise ModelUnavailableError("private provider message")

    graph["pair"] = _publish({"rerank_model": BrokenReranker.model_version})
    execution = RetrievalExecution()
    results = _local_search(graph, embedder=FakeEmbedder(), reranker=BrokenReranker(),
                             allow_model_fallback=True, execution=execution)
    assert results and any("vector" in r["matched_channels"] for r in results)
    assert all(r["rerank_score"] is None for r in results)
    assert execution.mode == "DEGRADED" and execution.reasons == ["rerank_unavailable"]
    assert "vector" in execution.channels and "rerank" not in execution.channels


@pytest.mark.parametrize("remote", [False, True])
def test_rerank_success_or_policy_denial_records_completed_channels(graph, remote):
    class QueryReranker:
        model_version = "test/rerank-channel"
        is_remote = remote
        endpoint = "https://api.siliconflow.cn/v1/rerank"

        def rerank(self, query, documents):
            assert not remote, "policy denied reranking must never reach the adapter"
            return [(index, float(index)) for index in range(len(documents))]

    graph["pair"] = _publish({"rerank_model": QueryReranker.model_version,
                              "rerank_endpoint": QueryReranker.endpoint})
    execution = RetrievalExecution()
    results = _local_search(graph, embedder=FakeEmbedder(), reranker=QueryReranker(),
                             query_outbound_authorized=True, allow_model_fallback=True,
                             execution=execution)
    assert results and "vector" in execution.channels
    if remote:
        assert execution.mode == "DEGRADED"
        assert execution.reasons == ["outbound_policy_blocked"]
        assert "rerank" not in execution.channels
        assert all(r["rerank_score"] is None for r in results)
    else:
        assert execution.mode == "HYBRID" and not execution.reasons
        assert "rerank" in execution.channels
        assert all(r["rerank_score"] is not None for r in results)


def test_local_fallback_cannot_bypass_scope_model_or_publish_gates(graph):
    with pytest.raises(PermissionError, match="scope exceeds"):
        search_published(graph["alias"], source_ids=[uuid4()], allow_model_fallback=True,
                         knowledge_version_id=graph["pair"][0], index_build_id=graph["pair"][1])
    class WrongModel(FakeEmbedder):
        model_version = "test/wrong-model"
    with pytest.raises(ValueError, match="active index model"):
        _local_search(graph, embedder=WrongModel(), allow_model_fallback=True)
    with SessionLocal.begin() as session:
        session.get(IndexBuild, graph["pair"][1]).vector_status = "PENDING"
    with pytest.raises(ValueError, match="inconsistent"):
        _local_search(graph)


def test_local_empty_scope_and_no_hits_still_record_execution(graph):
    execution = RetrievalExecution()
    assert search_published(graph["alias"], source_ids=[], execution=execution,
                            knowledge_version_id=graph["pair"][0],
                            index_build_id=graph["pair"][1]) == []
    assert execution.knowledge_version_id == graph["pair"][0]
    assert _local_search(graph, uuid4().hex, execution=RetrievalExecution()) == []


@pytest.mark.parametrize("failure,reason", [
    (ModelCredentialMissing, "model_not_configured"),
    (ModelCredentialUnavailable, "credential_unavailable"),
    (ValueError, "model_configuration_error"),
])
def test_api_missing_model_returns_local_proofs_and_safe_status(graph, monkeypatch, failure, reason):
    def unavailable():
        raise failure("private credential/configuration details")
    monkeypatch.setattr(main_module, "cloud_clients_from_environment", unavailable)
    with TestClient(main_module.app, base_url="http://127.0.0.1:8000") as client:
        response = client.get("/api/v1/retrieval/query", params={
            "query": f"  {graph['alias']}  ", "allow_remote_query": "true",
        })
        assert response.status_code == 200
        body = response.json()
        assert body["mode"] == "DEGRADED" and body["reasons"] == [reason]
        assert body["query_text"] == f"  {graph['alias']}  "
        assert body["results"] and all(r["evidence_id"].startswith("EV-")
                                       for r in body["results"])
        assert "private" not in response.text and "vector" not in body["channels"]
        empty = client.get("/api/v1/retrieval/query", params={
            "query": uuid4().hex, "allow_remote_query": "true",
        }).json()
        assert empty["results"] == [] and empty["reasons"] == [reason]


def test_api_local_modes_never_read_credentials_and_keep_legacy_array(graph, monkeypatch):
    def forbidden():
        pytest.fail("local search must not read credentials or create cloud clients")
    monkeypatch.setattr(main_module, "cloud_clients_from_environment", forbidden)
    with TestClient(main_module.app, base_url="http://127.0.0.1:8000") as client:
        for params, reason in (({}, "remote_query_not_authorized"),
                               ({"mode": "local", "allow_remote_query": "true"}, "local_requested")):
            response = client.get("/api/v1/retrieval/query", params={"query": graph["alias"], **params})
            assert response.status_code == 200
            assert response.json()["mode"] == "LOCAL"
            assert response.json()["reasons"] == [reason]
            legacy = client.get("/api/v1/retrieval/search", params={"query": graph["alias"], **params})
            assert legacy.status_code == 200 and legacy.json() == response.json()["results"]


@pytest.mark.parametrize("broken", [False, True])
def test_api_reports_success_or_model_failure_channels(graph, monkeypatch, broken):
    class QueryEmbedder(FakeEmbedder):
        def embed(self, texts):
            if broken:
                raise ModelUnavailableError("private upstream fault")
            return super().embed(texts)
    monkeypatch.setattr(main_module, "cloud_clients_from_environment", lambda: (QueryEmbedder(), None))
    with TestClient(main_module.app, base_url="http://127.0.0.1:8000") as client:
        response = client.get("/api/v1/retrieval/query", params={
            "query": graph["alias"], "allow_remote_query": "true",
        })
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == ("DEGRADED" if broken else "HYBRID")
    assert body["reasons"] == (["embedding_unavailable"] if broken else [])
    assert ("vector" in body["channels"]) == (not broken)
    assert body["results"] and "private" not in response.text


def test_unknown_source_scope_is_rejected(graph):
    with pytest.raises(PermissionError, match="scope exceeds"):
        _search(graph["alias"], graph["pair"], [uuid4()])


def test_scoped_terms_and_original_query_are_preserved(graph):
    g = graph
    sources = [g["sources"][0].source_id]
    assert not _ids(_search("错误时代词", g["pair"], sources), "structured")
    assert _ids(_search("ＡＢＣ", g["pair"], sources), "structured") == {g["evidence"][0][0]}
    original = "  安全别名 ＡＢＣ  "
    results = _search(original, g["pair"], sources)
    assert _ids(results, "structured") == {g["evidence"][0][0]}
    assert all(r["query_text"] == original and r["normalized_query"] == "安全别名 ABC"
               for r in results)
    assert not _ids(_search("' OR TRUE --", g["pair"], sources), "structured")


def test_relation_query_anchor_cannot_come_from_excluded_source(graph):
    g = graph
    exclusive = f"外部专词{uuid4().hex}"
    external = create_concept(exclusive, concept_type="PATTERN",
                               evidence_revision_id=g["evidence"][1][0])
    _approve("concept", external)
    relation = create_relation(external, g["endpoint"], relation_type="RELATED_TO",
                                assertion_text="跨来源合成关系", evidence_revision_id=g["evidence"][0][1])
    _approve("relation", relation)
    pair = _publish()
    assert not _ids(_search(exclusive, pair, [g["sources"][0].source_id]), "relation")
    assert _ids(_search(exclusive, pair, [s.source_id for s in g["sources"]]), "relation") == {
        g["evidence"][0][1],
    }


def test_formula_fields_resolve_only_reviewed_published_revision(tmp_path, monkeypatch):
    path = tmp_path / "formula.txt"
    path.write_text("合成檢索湯方：\n\n桂枝三兩；芍藥三兩。\n\n右二味，以水七升，煮取三升，分溫再服。",
                    encoding="utf-8")
    imported, _ = _segment_text(path, ContentAddressedStore(tmp_path / "store"),
                                SourceMetadata(source_type="OTHER", title="合成方剂检索"), monkeypatch)
    batch = extract_source_candidates(imported.source_revision_id)
    formula, = batch["formulas"]
    proof, revision = UUID(formula["evidence_revision_id"]), UUID(formula["formula_revision_id"])
    _approve("evidence_revision", proof)
    old = _publish()
    assert not _ids(_search("合成檢索湯", old, [imported.source_id]), "structured")
    _approve("formula_revision", revision)
    pair = _publish()
    for query in ("合成檢索湯", "桂枝", "芍藥"):
        assert _ids(_search(query, pair, [imported.source_id]), "structured") == {proof}
    assert _ids(_search("合成检索汤", pair, [imported.source_id]), "structured") == {proof}
    assert not _ids(_search("合成檢索湯", old, [imported.source_id]), "structured")


def test_historical_synonym_uses_own_anchors_not_comparison_proof(tmp_path, monkeypatch):
    _, source_concept, source = _batch(tmp_path, monkeypatch, era="合成时代甲")
    _, _, comparison = _batch(tmp_path, monkeypatch, era="合成时代乙")
    for spec in (source, comparison):
        _approve("evidence_revision", spec.evidence_revision_id)
    comparison_concept = create_concept("合成比較詞", concept_type="CONDITION",
                                         evidence_revision_id=comparison.evidence_revision_id,
                                         era="合成时代乙")
    _approve("concept", comparison_concept)
    resolved = _decide(source_concept, source, decision="HISTORICAL_SYNONYM",
                       related_concept_id=comparison_concept, sources=(source, comparison))
    _approve("concept", resolved)
    pair = _publish()
    with SessionLocal() as session:
        source_id = session.scalar(select(Evidence.source_id).join(
            EvidenceRevision, EvidenceRevision.evidence_id == Evidence.id,
        ).where(EvidenceRevision.id == source.evidence_revision_id))
        comparison_source_id = session.scalar(select(Evidence.source_id).join(
            EvidenceRevision, EvidenceRevision.evidence_id == Evidence.id,
        ).where(EvidenceRevision.id == comparison.evidence_revision_id))
    assert _ids(_search("合成原詞", pair, [source_id]), "structured") == {source.evidence_revision_id}
    assert not _ids(_search("合成原詞", pair, [comparison_source_id]), "structured")
    assert _ids(_search("合成比較詞", pair, [source_id]), "structured") == {source.evidence_revision_id}


def test_research_pool_records_new_channels_in_frozen_task_scope(graph):
    g = graph
    query = f"  {g['alias']}  "
    task = create_research_task(query, source_ids=[g["sources"][0].source_id])
    start_research_task(task, model_version="test/structured-planner")
    save_research_plan(task, {"subquestions": [g["alias"]]})
    _approve("concept", g["draft"])
    _approve("relation", g["draft_relation"])
    _publish()
    assert retrieve_for_task(task, embedder=FakeEmbedder()) == 3
    with SessionLocal() as session:
        events = list(session.scalars(select(EvidenceRetrievalEvent).where(
            EvidenceRetrievalEvent.task_id == task,
        )))
    assert {e.evidence_revision_id for e in events} == set(g["evidence"][0])
    assert all("structured" not in e.channels and "relation" not in e.channels
               for e in events if e.evidence_revision_id == g["evidence"][0][2])
    assert any("structured" in e.channels for e in events)
    assert any("relation" in e.channels for e in events)
