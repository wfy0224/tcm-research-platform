"""Versioned FTS/pgvector build and published-Evidence retrieval."""

import math
import re
import unicodedata
from collections import defaultdict
from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from sqlalchemy import func, select, text

from tcm_platform.audit import append_event
from tcm_platform.db import SessionLocal
from tcm_platform.ids import new_id
from tcm_platform.knowledge_service import trace_evidence
from tcm_platform.models import (
    EmbeddingRecord,
    EvidenceRevision,
    IndexBuild,
    KnowledgeRuntimeState,
    KnowledgeVersion,
    KnowledgeVersionItem,
    RetrievalChunk,
    utc_now,
)

HAN = re.compile(r"[\u3400-\u9fff]+|[a-zA-Z0-9]+")
MAX_CHUNKS = 20_000
MAX_CHUNK_CHARS = 4_000


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
    build_id: UUID, *, embedder: Embedder, actor_id: str = "local-indexer"
) -> int:
    """Call the model outside DB transactions, then atomically persist and validate indexes."""
    if not embedder.model_version.strip():
        raise ValueError("embedder model version is required")
    with SessionLocal() as session:
        build = session.get(IndexBuild, build_id)
        if build is None or build.status != "PENDING":
            raise ValueError("index build is missing or not pending")
        version = session.get(KnowledgeVersion, build.knowledge_version_id)
        if version is None or version.status != "INDEXING":
            raise ValueError("knowledge version is not indexing")
        configured_model = build.configuration.get("embedding_model")
        if configured_model != embedder.model_version:
            raise ValueError("embedder does not match the frozen index configuration")
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
        records = [
            (
                revision.id,
                revision.source_revision_id,
                (revision.quote_text + "\n" + revision.context_before + "\n"
                 + revision.context_after)[:MAX_CHUNK_CHARS],
                revision.citation_locator,
            )
            for revision in revisions
        ]

    vectors: list[list[float]] = []
    batch_size = min(32, embedder.max_batch_size)
    if batch_size < 1:
        raise ValueError("embedder batch size must be positive")
    for offset in range(0, len(records), batch_size):
        texts = [record[2] for record in records[offset:offset + batch_size]]
        vectors.extend(embedder.embed(texts))
    dimensions = _validated_vectors(vectors, len(records))

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
        session.add_all([
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
        if (
            chunk_count != len(records) or vector_count != len(records)
            or actual_dims != [dimensions]
        ):
            raise RuntimeError("stored FTS/vector index rows failed validation")
        build.fts_status = "READY"
        build.vector_status = "READY"
        build.status = "READY"
        build.validated_at = utc_now()
        version.status = "VALIDATING"
        append_event(
            session, event_type="index_build.validated", actor_id=actor_id,
            aggregate_id=build_id,
            payload={"count": len(records), "dimensions": dimensions,
                     "embedding_model": embedder.model_version},
        )
    return len(records)


def search_published(
    query: str,
    *,
    embedder: Embedder,
    reranker: Reranker | None = None,
    limit: int = 10,
    source_ids: Sequence[UUID] | None = None,
) -> list[dict]:
    """Fuse exact, FTS and vector ranks; return only active published Evidence."""
    query = unicodedata.normalize("NFKC", query).strip()
    if not query or len(query) > 2_000:
        raise ValueError("query must be 1-2000 characters")
    if not 1 <= limit <= 100:
        raise ValueError("limit must be 1-100")
    terms = tokenize(query)
    if not terms:
        raise ValueError("query has no searchable terms")
    with SessionLocal() as session:
        runtime = session.get(KnowledgeRuntimeState, 1)
        if runtime is None or runtime.active_knowledge_version_id is None:
            raise ValueError("no published knowledge version is active")
        version = session.get(KnowledgeVersion, runtime.active_knowledge_version_id)
        build = session.get(IndexBuild, runtime.active_index_build_id)
        if (
            version.status != "READY" or build.status != "READY"
            or build.knowledge_version_id != version.id
        ):
            raise ValueError("active knowledge/index pair is inconsistent")
        if build.configuration.get("embedding_model") != embedder.model_version:
            raise ValueError("query embedder differs from active index model")
        expected_reranker = build.configuration.get("rerank_model")
        if expected_reranker and (
            reranker is None or reranker.model_version != expected_reranker
        ):
            raise ValueError("query reranker differs from active index model")
        build_id, version_id = build.id, version.id

    query_vector = embedder.embed([query])
    _validated_vectors(query_vector, 1)
    candidate_limit = min(300, max(30, limit * 5))
    # Parameterized SQL keeps query text and vector values out of SQL syntax.
    filters = "AND ev.source_id = ANY(:source_ids)" if source_ids else ""
    allowed = (
        "JOIN knowledge.evidence_revision e ON e.id = c.evidence_revision_id "
        "JOIN knowledge.evidence ev ON ev.id = e.evidence_id "
        "JOIN governance.knowledge_version_item vi ON vi.evidence_revision_id = e.id "
        "AND vi.knowledge_version_id = :version_id "
        "WHERE c.index_build_id = :build_id AND e.status = 'REVIEWED' " + filters
    )
    vector_literal = "[" + ",".join(str(float(value)) for value in query_vector[0]) + "]"
    params = {
        "build_id": build_id, "version_id": version_id, "limit": candidate_limit,
        "query": query, "terms": terms, "vector": vector_literal,
    }
    if source_ids:
        params["source_ids"] = list(source_ids)
    channels = {
        "exact": (
            "SELECT c.evidence_revision_id FROM knowledge.retrieval_chunk c " + allowed
            + " AND position(lower(:query) in lower(c.chunk_text)) > 0 "
            "ORDER BY similarity(c.chunk_text, :query) DESC LIMIT :limit"
        ),
        "fts": (
            "SELECT c.evidence_revision_id FROM knowledge.retrieval_chunk c " + allowed
            + " AND c.search_vector @@ plainto_tsquery('simple', :terms) "
            "ORDER BY ts_rank_cd(c.search_vector, plainto_tsquery('simple', :terms)) DESC "
            "LIMIT :limit"
        ),
        "vector": (
            "SELECT c.evidence_revision_id FROM knowledge.retrieval_chunk c "
            "JOIN knowledge.embedding_record er ON er.chunk_id = c.id " + allowed
            + " AND er.dimensions = vector_dims(CAST(:vector AS vector)) "
            "ORDER BY er.embedding <=> CAST(:vector AS vector) LIMIT :limit"
        ),
    }
    weights = {"exact": 2.0, "fts": 1.5, "vector": 1.0}
    scores: dict[UUID, float] = defaultdict(float)
    matched: dict[UUID, list[str]] = defaultdict(list)
    with SessionLocal() as session:
        for channel, sql in channels.items():
            ranked = session.execute(text(sql), params).scalars().all()
            for rank, evidence_revision_id in enumerate(ranked, 1):
                scores[evidence_revision_id] += weights[channel] / (60 + rank)
                matched[evidence_revision_id].append(channel)
    ordered = sorted(scores, key=lambda item: (-scores[item], str(item)))[:min(100, max(limit * 3, 20))]
    traces = {revision_id: trace_evidence(revision_id) for revision_id in ordered}
    rerank_scores: dict[UUID, float] = {}
    if reranker and ordered:
        rankings = reranker.rerank(query, [traces[item]["quote_text"] for item in ordered])
        if len({index for index, _ in rankings}) != len(rankings) or any(
            index < 0 or index >= len(ordered) or not math.isfinite(score)
            for index, score in rankings
        ):
            raise ValueError("reranker returned invalid document indices or scores")
        rerank_scores = {ordered[index]: score for index, score in rankings}
        ordered = sorted(
            ordered, key=lambda item: (-rerank_scores.get(item, float("-inf")),
                                       -scores[item], str(item))
        )
    return [
        {**traces[revision_id], "retrieval_score": scores[revision_id],
         "matched_channels": matched[revision_id],
         "rerank_score": rerank_scores.get(revision_id)}
        for revision_id in ordered[:limit]
    ]
