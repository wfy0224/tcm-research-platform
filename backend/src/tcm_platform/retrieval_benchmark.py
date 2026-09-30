"""Human-labeled retrieval queries and reproducible published-index metrics."""

import math
from collections.abc import Mapping, Sequence
from uuid import UUID

from sqlalchemy import select

from tcm_platform.audit import append_event
from tcm_platform.db import SessionLocal
from tcm_platform.ids import new_id
from tcm_platform.models import (
    EvidenceRevision,
    KnowledgeRuntimeState,
    RetrievalBenchmarkRun,
    RetrievalGoldenJudgment,
    RetrievalGoldenQuery,
)
from tcm_platform.retrieval import Embedder, Reranker, search_published
from tcm_platform.retrieval_diversity import DIVERSITY_POLICY
from tcm_platform.retrieval_query import QUERY_POLICY, query_metadata

GRADES = {"GOLD": 3, "COUNTER": 2, "OPTIONAL": 1, "HARD_NEGATIVE": 0}


def create_golden_query(
    query: str, judgments: Mapping[UUID, str], *,
    source_ids: Sequence[UUID] = (), actor_id: str = "local-curator",
) -> UUID:
    query = query.strip()
    if not 1 <= len(query) <= 2_000:
        raise ValueError("golden query must be 1-2000 characters")
    if not judgments or not any(label in {"GOLD", "COUNTER"} for label in judgments.values()):
        raise ValueError("golden query requires at least one GOLD or COUNTER judgment")
    if any(label not in GRADES for label in judgments.values()):
        raise ValueError("unknown retrieval judgment category")
    with SessionLocal.begin() as session:
        for evidence_id in judgments:
            revision = session.get(EvidenceRevision, evidence_id)
            if revision is None or revision.status != "REVIEWED":
                raise ValueError("golden judgment must reference reviewed EvidenceRevision")
        query_id = new_id()
        session.add(RetrievalGoldenQuery(
            id=query_id, public_id=f"RGQ-{query_id}", query_text=query,
            source_scope=[str(source_id) for source_id in source_ids],
        ))
        session.flush()
        session.add_all([
            RetrievalGoldenJudgment(
                id=new_id(), query_id=query_id,
                evidence_revision_id=evidence_id, category=label,
            )
            for evidence_id, label in judgments.items()
        ])
        append_event(
            session, event_type="retrieval_golden_query.created", actor_id=actor_id,
            aggregate_id=query_id, payload={"judgment_count": len(judgments)},
        )
        return query_id


def score_ranked(
    ranked_ids: Sequence[UUID], judgments: Mapping[UUID, str], *, k: int,
    resolved_ids: set[UUID] | None = None,
) -> dict[str, float]:
    """Score one query; GOLD and COUNTER are essential, OPTIONAL is relevant."""
    if k < 1 or any(label not in GRADES for label in judgments.values()):
        raise ValueError("invalid benchmark k or judgment")
    ranked = list(ranked_ids[:k])
    if len(set(ranked)) != len(ranked):
        raise ValueError("retrieval results contain duplicate EvidenceRevision IDs")
    essential = {item for item, label in judgments.items() if label in {"GOLD", "COUNTER"}}
    counter = {item for item, label in judgments.items() if label == "COUNTER"}
    relevant = {item for item, label in judgments.items() if label != "HARD_NEGATIVE"}
    if not essential:
        raise ValueError("benchmark query has no essential judgments")
    first_relevant = next((rank for rank, item in enumerate(ranked, 1) if item in relevant), None)
    dcg = sum((2 ** GRADES[judgments.get(item, "HARD_NEGATIVE")] - 1)
              / math.log2(rank + 1) for rank, item in enumerate(ranked, 1))
    ideal = sorted((GRADES[label] for label in judgments.values()), reverse=True)[:k]
    idcg = sum((2 ** grade - 1) / math.log2(rank + 1)
               for rank, grade in enumerate(ideal, 1))
    resolved = set(ranked) if resolved_ids is None else resolved_ids
    return {
        "precision_at_k": len(set(ranked) & relevant) / k,
        "recall_at_k": len(set(ranked) & essential) / len(essential),
        "mrr": 1 / first_relevant if first_relevant else 0.0,
        "ndcg_at_k": dcg / idcg if idcg else 0.0,
        "counter_evidence_recall_at_k": len(set(ranked) & counter) / len(counter) if counter else 0.0,
        "evidence_resolution_rate": len(set(ranked) & resolved) / len(ranked) if ranked else 0.0,
    }


def run_benchmark(
    *, embedder: Embedder, reranker: Reranker | None = None,
    k: int = 10, actor_id: str = "local-benchmark",
    query_outbound_authorized: bool = False,
) -> dict:
    if not 1 <= k <= 100:
        raise ValueError("benchmark k must be 1-100")
    with SessionLocal() as session:
        runtime = session.get(KnowledgeRuntimeState, 1)
        if runtime is None or runtime.active_knowledge_version_id is None:
            raise ValueError("no published knowledge version is active")
        version_id = runtime.active_knowledge_version_id
        build_id = runtime.active_index_build_id
        queries = list(session.scalars(select(RetrievalGoldenQuery).order_by(RetrievalGoldenQuery.public_id)))
        if not queries:
            raise ValueError("retrieval golden set is empty")
        inputs = [
            (
                item.id, item.query_text, [UUID(value) for value in item.source_scope],
                {row.evidence_revision_id: row.category for row in session.scalars(
                    select(RetrievalGoldenJudgment).where(RetrievalGoldenJudgment.query_id == item.id)
                )},
            )
            for item in queries
        ]
    per_query = []
    for query_id, query_text, source_ids, judgments in inputs:
        results = search_published(
            query_text, embedder=embedder, reranker=reranker,
            limit=k, source_ids=source_ids or None,
            knowledge_version_id=version_id, index_build_id=build_id,
            query_outbound_authorized=query_outbound_authorized,
        )
        ids = [UUID(result["evidence_revision_id"]) for result in results]
        resolved = {
            UUID(result["evidence_revision_id"]) for result in results
            if result.get("source_revision_id") and result.get("segment_revision_ids")
            and result.get("quote_text") and result.get("citation_locator")
        }
        per_query.append({"query_id": str(query_id),
                          "query_text": query_text, "query_expansion": query_metadata(query_text),
                          "ranking": [{"evidence_revision_id": result["evidence_revision_id"],
                                       **result["diversity"]} for result in results],
                          **score_ranked(
            ids, judgments, k=k, resolved_ids=resolved,
        )})
    keys = [key for key in per_query[0]
            if key not in {"query_id", "query_text", "query_expansion", "ranking"}]
    aggregate = {key: sum(row[key] for row in per_query) / len(per_query) for key in keys}
    metrics = {"aggregate": aggregate, "queries": per_query, "ranking_policy": DIVERSITY_POLICY,
               "query_policy": QUERY_POLICY}
    with SessionLocal.begin() as session:
        runtime = session.get(KnowledgeRuntimeState, 1)
        if (runtime.active_knowledge_version_id != version_id
                or runtime.active_index_build_id != build_id):
            raise ValueError("published index changed during benchmark")
        run_id = new_id()
        session.add(RetrievalBenchmarkRun(
            id=run_id, knowledge_version_id=version_id, index_build_id=build_id,
            k=k, query_count=len(inputs), metrics=metrics,
        ))
        append_event(
            session, event_type="retrieval_benchmark.completed", actor_id=actor_id,
            aggregate_id=run_id,
            payload={"knowledge_version_id": str(version_id), "index_build_id": str(build_id),
                     "query_count": len(inputs), "k": k},
        )
    return {"run_id": str(run_id), "knowledge_version_id": str(version_id),
            "index_build_id": str(build_id), "k": k, **metrics}
