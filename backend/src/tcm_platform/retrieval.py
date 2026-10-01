"""Versioned FTS/pgvector build and published-Evidence retrieval."""

import math
import re
import unicodedata
from collections import defaultdict
from collections.abc import Sequence
from contextlib import nullcontext
from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

from sqlalchemy import func, select, text

from tcm_platform.audit import append_event
from tcm_platform.db import SessionLocal
from tcm_platform.ids import new_id
from tcm_platform.knowledge_service import trace_evidence
from tcm_platform.model_errors import ModelResponseError, ModelUnavailableError
from tcm_platform.models import (
    EmbeddingRecord,
    Evidence,
    EvidenceRevision,
    EvidenceSegmentRef,
    IndexBuild,
    KnowledgeRuntimeState,
    KnowledgeVersion,
    KnowledgeVersionItem,
    RetrievalChunk,
    utc_now,
)
from tcm_platform.outbound_policy import authorize_outbound
from tcm_platform.publication_config import is_local_configuration, validate_local_configuration
from tcm_platform.retrieval_diversity import diversify
from tcm_platform.retrieval_quality import record_unpublished_matches
from tcm_platform.retrieval_query import (
    expanded_fts_query,
    query_metadata,
    spelling_params,
    spelling_sql,
)
from tcm_platform.retrieval_structured import structured_candidates

HAN = re.compile(r"[\u3400-\u9fff]+|[a-zA-Z0-9]+")
MAX_CHUNKS = 20_000
MAX_CHUNK_CHARS = 6_000


@dataclass
class RetrievalExecution:
    """Request-local status, including empty results; never contains provider errors."""

    mode: str = "LOCAL"
    reasons: list[str] = field(default_factory=list)
    channels: list[str] = field(default_factory=lambda: ["exact", "fts", "structured", "relation"])
    knowledge_version_id: UUID | None = None
    index_build_id: UUID | None = None

    def degrade(self, reason: str) -> None:
        self.mode = "DEGRADED"
        if reason not in self.reasons:
            self.reasons.append(reason)


class Embedder(Protocol):
    model_version: str
    max_batch_size: int

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class Reranker(Protocol):
    model_version: str

    def rerank(self, query: str, documents: Sequence[str]) -> list[tuple[int, float]]: ...


def tokenize(text_value: str) -> str:
    """Expose Chinese characters/bigrams and Latin tokens to PostgreSQL simple FTS."""
    normalized = unicodedata.normalize("NFKC", text_value).lower()
    tokens: list[str] = []
    for match in HAN.finditer(normalized):
        word = match.group()
        if all("\u3400" <= char <= "\u9fff" for char in word):
            tokens.extend(word)
            tokens.extend(word[i:i + 2] for i in range(len(word) - 1))
        else:
            tokens.append(word)
    return " ".join(tokens)


def _validated_vectors(vectors: list[list[float]], count: int) -> int:
    if len(vectors) != count:
        raise ValueError("embedder returned a different number of vectors")
    dimensions = len(vectors[0]) if vectors else 0
    if not 2 <= dimensions <= 4_096:
        raise ValueError("embedding dimensions must be 2-4096")
    for vector in vectors:
        if (
            len(vector) != dimensions
            or any(not math.isfinite(float(value)) for value in vector)
            or not any(float(value) != 0 for value in vector)
        ):
            raise ValueError("embedding vectors must have consistent finite nonzero values")
    return dimensions


def build_retrieval_index(
    build_id: UUID, *, embedder: Embedder | None = None, actor_id: str = "local-indexer"
) -> int:
    """Call the model outside DB transactions, then atomically persist and validate indexes."""
    if embedder is not None and not embedder.model_version.strip():
        raise ValueError("embedder model version is required")
    with SessionLocal() as session:
        build = session.get(IndexBuild, build_id)
        if build is None or build.status != "PENDING":
            raise ValueError("index build is missing or not pending")
        version = session.get(KnowledgeVersion, build.knowledge_version_id)
        if version is None or version.status != "INDEXING":
            raise ValueError("knowledge version is not indexing")
        configured_model = build.configuration.get("embedding_model")
        local_index = is_local_configuration(build.configuration)
        if local_index:
            validate_local_configuration(build.configuration)
            if embedder is not None:
                raise ValueError("local index does not accept an embedder")
        elif embedder is None or configured_model != embedder.model_version:
            raise ValueError("embedder does not match the frozen index configuration")
        if (getattr(embedder, "is_remote", False)
                and build.configuration.get("embedding_endpoint") != embedder.endpoint):
            raise ValueError("embedder endpoint differs from frozen index route")
        revisions = list(session.scalars(
            select(EvidenceRevision)
            .join(KnowledgeVersionItem,
                  KnowledgeVersionItem.evidence_revision_id == EvidenceRevision.id)
            .where(KnowledgeVersionItem.knowledge_version_id == version.id)
            .order_by(EvidenceRevision.id)
        ))
        if not revisions or len(revisions) > MAX_CHUNKS:
            raise ValueError("index requires 1-20000 reviewed evidence revisions")
        if any(revision.status != "REVIEWED" for revision in revisions):
            raise ValueError("index snapshot includes evidence without review")
        version_id = version.id
        manifest_hash = version.manifest_hash
        outbound_mode = build.configuration.get("outbound_mode", "LOCAL_ONLY")
        outbound_policy_version = build.configuration.get("outbound_policy_version")
        outbound_sources = [UUID(value) for value in
                            build.configuration.get("outbound_source_ids", [])]
        records = [
            (
                revision.id,
                revision.source_revision_id,
                (revision.quote_text + "\n" + revision.context_before + "\n"
                 + revision.context_after),
                revision.citation_locator,
            )
            for revision in revisions
        ]
        if any(len(record[2]) > MAX_CHUNK_CHARS for record in records):
            raise ValueError("evidence chunk exceeds index limit; shorten it explicitly")

    vectors: list[list[float]] = []
    batch_size = min(32, embedder.max_batch_size) if embedder is not None else len(records)
    if batch_size < 1:
        raise ValueError("embedder batch size must be positive")
    for offset in range(0, len(records), batch_size):
        if local_index:
            break
        texts = [record[2] for record in records[offset:offset + batch_size]]
        scope = (authorize_outbound("embed", embedder.model_version, outbound_sources,
                                    frozen_mode=outbound_mode,
                                    frozen_policy_version=outbound_policy_version)
                 if getattr(embedder, "is_remote", False) else nullcontext())
        with scope:
            vectors.extend(embedder.embed(texts))
    dimensions = _validated_vectors(vectors, len(records)) if not local_index else None

    with SessionLocal.begin() as session:
        build = session.scalar(select(IndexBuild).where(IndexBuild.id == build_id).with_for_update())
        version = session.get(KnowledgeVersion, version_id)
        if (
            build is None or build.status != "PENDING" or version.status != "INDEXING"
            or version.manifest_hash != manifest_hash
        ):
            raise ValueError("index build changed during embedding")
        chunks: list[RetrievalChunk] = []
        for revision_id, source_revision_id, chunk_text, locator in records:
            chunk = RetrievalChunk(
                id=new_id(), index_build_id=build_id, evidence_revision_id=revision_id,
                source_revision_id=source_revision_id, chunk_text=chunk_text,
                token_text=tokenize(chunk_text), locator=locator,
            )
            if not chunk.token_text:
                raise ValueError("evidence text produces no searchable terms")
            chunks.append(chunk)
        session.add_all(chunks)
        session.flush()
        session.add_all([] if local_index else [
            EmbeddingRecord(
                id=new_id(), index_build_id=build_id, chunk_id=chunk.id,
                model_version=embedder.model_version, dimensions=dimensions,
                embedding=vector,
            )
            for chunk, vector in zip(chunks, vectors, strict=True)
        ])
        session.flush()
        chunk_count = session.scalar(select(func.count()).select_from(RetrievalChunk).where(
            RetrievalChunk.index_build_id == build_id
        ))
        vector_count = session.scalar(select(func.count()).select_from(EmbeddingRecord).where(
            EmbeddingRecord.index_build_id == build_id
        ))
        actual_dims = session.execute(text(
            "SELECT DISTINCT vector_dims(embedding) FROM knowledge.embedding_record "
            "WHERE index_build_id = :build_id"
        ), {"build_id": build_id}).scalars().all()
        if (chunk_count != len(records) or (local_index and (vector_count or actual_dims))
                or (not local_index and (vector_count != len(records) or actual_dims != [dimensions]))):
            raise RuntimeError("stored FTS/vector index rows failed validation")
        build.fts_status = "READY"
        build.vector_status = "NOT_APPLICABLE" if local_index else "READY"
        build.status = "READY"
        build.validated_at = utc_now()
        version.status = "VALIDATING"
        append_event(
            session, event_type="index_build.validated", actor_id=actor_id,
            aggregate_id=build_id,
            payload={"count": len(records), "dimensions": dimensions,
                     "embedding_model": embedder.model_version if embedder is not None else None,
                     "strategy": build.configuration.get("strategy"),
                     "vector_status": build.vector_status},
        )
    return len(records)


def search_published(
    query: str,
    *,
    embedder: Embedder | None = None,
    reranker: Reranker | None = None,
    limit: int = 10,
    source_ids: Sequence[UUID] | None = None,
    knowledge_version_id: UUID | None = None,
    index_build_id: UUID | None = None,
    query_outbound_authorized: bool = False,
    task_id: UUID | None = None,
    allow_model_fallback: bool = False,
    execution: RetrievalExecution | None = None,
) -> list[dict]:
    """Fuse frozen proofs. No embedder selects local retrieval; fallback is explicit."""
    execution = execution if execution is not None else RetrievalExecution()
    if embedder is None and reranker is not None:
        raise ValueError("local retrieval cannot use a reranker")
    original_query = query
    query = unicodedata.normalize("NFKC", query).strip()
    if not query or len(query) > 2_000:
        raise ValueError("query must be 1-2000 characters")
    if not 1 <= limit <= 100:
        raise ValueError("limit must be 1-100")
    terms = tokenize(query)
    if not terms:
        raise ValueError("query has no searchable terms")
    if (knowledge_version_id is None) != (index_build_id is None):
        raise ValueError("frozen knowledge and index IDs must be supplied together")
    with SessionLocal() as session:
        if knowledge_version_id is None:
            runtime = session.get(KnowledgeRuntimeState, 1)
            if runtime is None or runtime.active_knowledge_version_id is None:
                raise ValueError("no published knowledge version is active")
            knowledge_version_id = runtime.active_knowledge_version_id
            index_build_id = runtime.active_index_build_id
        version = session.get(KnowledgeVersion, knowledge_version_id)
        build = session.get(IndexBuild, index_build_id)
        if (
            version is None or build is None
            or version.status != "READY" or build.status != "READY"
            or build.fts_status != "READY"
            or build.vector_status != ("NOT_APPLICABLE" if is_local_configuration(
                build.configuration) else "READY")
            or build.knowledge_version_id != version.id
        ):
            raise ValueError("active knowledge/index pair is inconsistent")
        if is_local_configuration(build.configuration):
            validate_local_configuration(build.configuration)
            # Local index selection is independent of permission for cloud generation.
            # There are no vectors to query or candidate scores to rerank in this route.
            embedder, reranker = None, None
            execution.mode = "LOCAL"
            execution.channels = ["exact", "fts", "structured", "relation"]
        if embedder is not None and build.configuration.get("embedding_model") != embedder.model_version:
            raise ValueError("query embedder differs from active index model")
        if (getattr(embedder, "is_remote", False)
                and build.configuration.get("embedding_endpoint") != embedder.endpoint):
            raise ValueError("query embedder endpoint differs from active index route")
        expected_reranker = build.configuration.get("rerank_model")
        if embedder is not None and ((expected_reranker is None) != (reranker is None)
                or (reranker is not None and reranker.model_version != expected_reranker)):
            raise ValueError("query reranker differs from active index model")
        if (reranker is not None and getattr(reranker, "is_remote", False)
                and build.configuration.get("rerank_endpoint") != reranker.endpoint):
            raise ValueError("query reranker endpoint differs from active index route")
        build_id, version_id = build.id, version.id
        execution.knowledge_version_id, execution.index_build_id = version_id, build_id
        outbound_mode = build.configuration.get("outbound_mode", "LOCAL_ONLY")
        outbound_policy_version = build.configuration.get("outbound_policy_version")
        outbound_sources = [UUID(value) for value in
                            build.configuration.get("outbound_source_ids", [])]
        if source_ids is not None and not set(source_ids).issubset(set(outbound_sources)):
            raise PermissionError("source scope exceeds frozen outbound source set")
        scoped_sources = list(outbound_sources if source_ids is None else source_ids)

    if not scoped_sources:
        return []

    query_vector = None
    if embedder is not None:
        try:
            if getattr(embedder, "is_remote", False) and not query_outbound_authorized:
                raise PermissionError("query text requires explicit remote-model authorization")
            embed_scope = (authorize_outbound("embed", embedder.model_version, outbound_sources,
                                              frozen_mode=outbound_mode,
                                              frozen_policy_version=outbound_policy_version,
                                              task_id=task_id)
                           if getattr(embedder, "is_remote", False) else nullcontext())
            with embed_scope:
                candidate_vector = embedder.embed([query])
            try:
                _validated_vectors(candidate_vector, 1)
            except (ValueError, TypeError, OverflowError) as exc:
                raise ModelResponseError("query embedding is invalid") from exc
            query_vector = candidate_vector
            execution.channels.append("vector")
            execution.mode = "HYBRID"
        except PermissionError:
            if not allow_model_fallback:
                raise
            execution.degrade("outbound_policy_blocked" if query_outbound_authorized
                              else "remote_query_not_authorized")
            reranker = None
        except (ModelUnavailableError, ModelResponseError, TimeoutError, ConnectionError):
            if not allow_model_fallback:
                raise
            execution.degrade("embedding_unavailable")
            # Full local fallback avoids a second failing model request.
            reranker = None
    candidate_limit = min(300, max(30, limit * 5))
    # Parameterized SQL keeps query text and vector values out of SQL syntax.
    filters = "AND ev.source_id = ANY(:source_ids)"
    allowed = (
        "JOIN knowledge.evidence_revision e ON e.id = c.evidence_revision_id "
        "JOIN knowledge.evidence ev ON ev.id = e.evidence_id "
        "JOIN governance.knowledge_version_item vi ON vi.evidence_revision_id = e.id "
        "AND vi.knowledge_version_id = :version_id "
        "WHERE c.index_build_id = :build_id AND e.status = 'REVIEWED' " + filters
    )
    params = {
        "build_id": build_id, "version_id": version_id, "limit": candidate_limit,
        "query": query, "expanded_terms": expanded_fts_query(terms.split()),
        **spelling_params(query),
        "source_ids": scoped_sources,
    }
    channels = {
        "exact": (
            "SELECT c.evidence_revision_id FROM knowledge.retrieval_chunk c " + allowed
            + f" AND position(:query_key in {spelling_sql('c.chunk_text')}) > 0 "
            "ORDER BY similarity(c.chunk_text, :query) DESC, c.evidence_revision_id LIMIT :limit"
        ),
        "fts": (
            "SELECT c.evidence_revision_id FROM knowledge.retrieval_chunk c " + allowed
            + " AND c.search_vector @@ to_tsquery('simple', :expanded_terms) "
            "ORDER BY ts_rank_cd(c.search_vector, to_tsquery('simple', :expanded_terms)) DESC, "
            "c.evidence_revision_id LIMIT :limit"
        ),
    }
    if query_vector is not None:
        params["vector"] = "[" + ",".join(str(float(value)) for value in query_vector[0]) + "]"
        channels["vector"] = (
            "SELECT c.evidence_revision_id FROM knowledge.retrieval_chunk c "
            "JOIN knowledge.embedding_record er ON er.chunk_id = c.id " + allowed
            + " AND er.dimensions = vector_dims(CAST(:vector AS vector)) "
            "ORDER BY er.embedding <=> CAST(:vector AS vector), c.evidence_revision_id LIMIT :limit"
        )
    weights = {"exact": 2.0, "fts": 1.5, "vector": 1.0,
               "structured": 1.5, "relation": 1.0}
    scores: dict[UUID, float] = defaultdict(float)
    matched: dict[UUID, list[str]] = defaultdict(list)
    with SessionLocal() as session:
        rankings_by_channel = {
            channel: list(session.scalars(text(sql), params))
            for channel, sql in channels.items()
        }
        rankings_by_channel.update(structured_candidates(
            session, query=query, version_id=version_id, build_id=build_id,
            source_ids=scoped_sources, limit=candidate_limit,
        ))
        for channel, ranked in rankings_by_channel.items():
            for rank, evidence_revision_id in enumerate(dict.fromkeys(ranked), 1):
                scores[evidence_revision_id] += weights[channel] / (60 + rank)
                matched[evidence_revision_id].append(channel)
        # Load only provenance for the bounded channel union, not full traces.
        # Apply diversity before the rerank cap so one source cannot occupy it.
        provenance: dict[UUID, dict] = {}
        if scores:
            for revision_id, source_id, source_revision_id, segment_id in session.execute(
                select(EvidenceRevision.id, Evidence.source_id, EvidenceRevision.source_revision_id,
                       EvidenceSegmentRef.segment_revision_id)
                .join(Evidence, Evidence.id == EvidenceRevision.evidence_id)
                .join(EvidenceSegmentRef,
                      EvidenceSegmentRef.evidence_revision_id == EvidenceRevision.id)
                .where(EvidenceRevision.id.in_(scores))
            ):
                proof = provenance.setdefault(revision_id, {
                    "source_id": str(source_id), "source_revision_id": str(source_revision_id),
                    "segment_revision_ids": [],
                })
                proof["segment_revision_ids"].append(str(segment_id))
        if set(provenance) != set(scores):
            raise ValueError("candidate evidence has no segment provenance")
    ordered, _ = diversify(
        sorted(scores, key=lambda item: (-scores[item], str(item))), scores=scores,
        provenance=provenance, limit=min(100, max(limit * 3, 20)),
    )
    traces = {revision_id: trace_evidence(revision_id) for revision_id in ordered}
    rerank_scores: dict[UUID, float] = {}
    reranked = False
    if reranker and ordered:
        try:
            if getattr(reranker, "is_remote", False) and not query_outbound_authorized:
                raise PermissionError("reranking query requires remote-model authorization")
            rerank_scope = (authorize_outbound("rerank", reranker.model_version, outbound_sources,
                                           frozen_mode=outbound_mode,
                                           frozen_policy_version=outbound_policy_version,
                                           task_id=task_id)
                            if getattr(reranker, "is_remote", False) else nullcontext())
            with rerank_scope:
                rankings = reranker.rerank(query, [traces[item]["quote_text"] for item in ordered])
            if len({index for index, _ in rankings}) != len(rankings) or any(
                type(index) is not int or index < 0 or index >= len(ordered)
                or not math.isfinite(score) for index, score in rankings
            ):
                raise ModelResponseError("reranker returned invalid document indices or scores")
            rerank_scores = {ordered[index]: score for index, score in rankings}
            execution.channels.append("rerank")
            reranked = True
            ordered = sorted(
                ordered, key=lambda item: (-rerank_scores.get(item, float("-inf")),
                                       -scores[item], str(item))
            )
        except PermissionError:
            if not allow_model_fallback:
                raise
            execution.degrade("outbound_policy_blocked")
        except (ModelUnavailableError, ModelResponseError, TimeoutError, ConnectionError):
            if not allow_model_fallback:
                raise
            execution.degrade("rerank_unavailable")
    if not reranked:
        ordered = sorted(ordered, key=lambda item: (-scores[item], str(item)))
    relevance = ({item: 1 / (60 + rank) for rank, item in enumerate(ordered, 1)}
                 if reranked else scores)
    ordered, explanations = diversify(
        ordered, scores=relevance, provenance=provenance, limit=limit,
    )
    record_unpublished_matches(
        query=query, original_query=original_query, version_id=version_id,
        build_id=build_id, source_ids=scoped_sources, task_id=task_id,
    )
    return [
        {**traces[revision_id], "retrieval_score": scores[revision_id],
         "matched_channels": matched[revision_id],
         "query_text": original_query, "normalized_query": query,
         "query_expansion": query_metadata(original_query),
         "rerank_score": rerank_scores.get(revision_id),
         "diversity": explanations[revision_id]}
        for revision_id in ordered[:limit]
    ]
