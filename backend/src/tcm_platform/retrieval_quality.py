"""Local exact-match triage, separate from published proofs and model inputs."""

import json
from uuid import UUID

from sqlalchemy import select, text

from tcm_platform.db import SessionLocal
from tcm_platform.knowledge_publish import ISSUE_TARGETS, REVIEW_TARGETS, open_quality_issue
from tcm_platform.knowledge_service import CITABLE_SEGMENT_TYPES
from tcm_platform.models import (
    EvidenceRevision,
    EvidenceSegmentRef,
    KnowledgeVersion,
    KnowledgeVersionItem,
    TextSegmentRevision,
)

POLICY = "unpublished-exact/v1"
ISSUE_TYPE = "RETRIEVAL_UNPUBLISHED_EXACT_V1"
MAX_MATCHES = 100


def record_unpublished_matches(
    *, query: str, original_query: str, version_id: UUID, build_id: UUID,
    source_ids: list[UUID], task_id: UUID | None = None,
) -> None:
    """Triage literal matches, without claiming calibrated medical relevance.

    Source IDs alone never authorize newer source revisions: only source revisions
    represented by this frozen index are scanned. Previously published identities
    and rejected targets are excluded. The first observation is retained per target
    and policy across queries, versions and human resolution; nothing is reopened.
    """
    if not source_ids:
        return
    common = """
        WITH frozen_sources AS (
            SELECT DISTINCT e.source_revision_id
            FROM knowledge.retrieval_chunk rc
            JOIN knowledge.evidence_revision e ON e.id = rc.evidence_revision_id
            JOIN knowledge.evidence ev ON ev.id = e.evidence_id
            JOIN governance.knowledge_version_item vi ON vi.evidence_revision_id = e.id
                AND vi.knowledge_version_id = :version_id
            WHERE rc.index_build_id = :build_id AND e.status = 'REVIEWED'
                AND ev.source_id = ANY(:source_ids)
        ), scoped_evidence AS (
            SELECT e.* FROM knowledge.evidence_revision e
            JOIN knowledge.evidence ev ON ev.id = e.evidence_id
            JOIN frozen_sources fs ON fs.source_revision_id = e.source_revision_id
            WHERE ev.source_id = ANY(:source_ids) AND e.status IN ('DRAFT', 'REVIEWED')
        ), published AS (
            SELECT vi.* FROM governance.knowledge_version_item vi
            JOIN governance.knowledge_version kv ON kv.id = vi.knowledge_version_id
            WHERE kv.status = 'READY'
        ), matches AS (
            SELECT 'evidence_revision' AS kind, e.id AS target_id, e.id AS evidence_id,
                e.anchor_segment_revision_id AS segment_id, 'quote_exact' AS basis
            FROM scoped_evidence e
            WHERE position(lower(:query) in lower(normalize(e.quote_text, NFKC))) > 0
                AND NOT EXISTS (SELECT 1 FROM published p WHERE p.evidence_revision_id = e.id)
            UNION
            SELECT 'concept', c.id, e.id, e.anchor_segment_revision_id, 'own_term_exact'
            FROM knowledge.concept c
            JOIN knowledge.concept_evidence ce ON ce.concept_id = c.id
            JOIN scoped_evidence e ON e.id = ce.evidence_revision_id
            JOIN knowledge.concept_term ct ON ct.concept_id = c.id
                AND ct.era IS NOT DISTINCT FROM c.era
                AND ct.school IS NOT DISTINCT FROM c.school
            LEFT JOIN knowledge.term_resolution tr ON tr.resolved_concept_id = c.id
            WHERE c.status IN ('DRAFT', 'REVIEWED') AND ct.term <> ''
                AND position(lower(normalize(ct.term, NFKC)) in lower(:query)) > 0
                AND (tr.id IS NULL OR EXISTS (
                    SELECT 1 FROM jsonb_array_elements(tr.provenance->'mentions') anchor
                    WHERE anchor->>'evidence_revision_id' = e.id::text
                ))
                AND NOT EXISTS (SELECT 1 FROM published p WHERE p.concept_id = c.id)
            UNION
            SELECT 'relation', r.id, e.id, e.anchor_segment_revision_id, 'assertion_exact'
            FROM knowledge.relation r
            JOIN knowledge.relation_evidence re ON re.relation_id = r.id
            JOIN scoped_evidence e ON e.id = re.evidence_revision_id
            WHERE r.status IN ('DRAFT', 'REVIEWED')
                AND position(lower(:query) in lower(normalize(r.assertion_text, NFKC))) > 0
                AND NOT EXISTS (SELECT 1 FROM published p WHERE p.relation_id = r.id)
            UNION
            SELECT 'herb', h.id, e.id, e.anchor_segment_revision_id, 'own_term_exact'
            FROM knowledge.herb h
            JOIN knowledge.herb_evidence he ON he.herb_id = h.id
            JOIN scoped_evidence e ON e.id = he.evidence_revision_id
            JOIN knowledge.herb_term ht ON ht.herb_id = h.id
            WHERE h.status IN ('DRAFT', 'REVIEWED') AND ht.term <> ''
                AND position(lower(normalize(ht.term, NFKC)) in lower(:query)) > 0
                AND NOT EXISTS (SELECT 1 FROM published p WHERE p.herb_id = h.id)
            UNION
            SELECT 'formula_revision', f.id, e.id, e.anchor_segment_revision_id, 'formula_exact'
            FROM knowledge.formula_revision f
            JOIN knowledge.formula_evidence fe ON fe.formula_revision_id = f.id
            JOIN scoped_evidence e ON e.id = fe.evidence_revision_id
            WHERE f.status IN ('DRAFT', 'REVIEWED') AND (
                (f.original_name <> ''
                    AND position(lower(normalize(f.original_name, NFKC)) in lower(:query)) > 0)
                OR EXISTS (SELECT 1 FROM knowledge.formula_ingredient i
                    WHERE i.formula_revision_id = f.id AND i.original_name <> ''
                    AND position(lower(normalize(i.original_name, NFKC)) in lower(:query)) > 0)
            ) AND NOT EXISTS (SELECT 1 FROM published p WHERE p.formula_revision_id = f.id)
            UNION
            SELECT 'text_segment_revision', s.id, NULL::uuid, s.id, 'segment_exact'
            FROM source.text_segment_revision s
            JOIN frozen_sources fs ON fs.source_revision_id = s.source_revision_id
            WHERE s.segment_type = ANY(:segment_types)
                AND NOT EXISTS (SELECT 1 FROM source.text_segment_revision parent
                    WHERE parent.source_revision_id = s.source_revision_id
                        AND parent.segment_id = s.parent_segment_id
                        AND parent.segment_type = ANY(:segment_types))
                AND position(lower(:query) in lower(normalize(s.original_text, NFKC))) > 0
                AND NOT EXISTS (SELECT 1 FROM knowledge.evidence_segment_ref ref
                    JOIN source.text_segment_revision cited ON cited.id = ref.segment_revision_id
                    WHERE cited.source_revision_id = s.source_revision_id
                        AND (cited.id = s.id OR cited.parent_segment_id = s.segment_id))
        )
        SELECT DISTINCT ON (kind, target_id) kind, target_id, evidence_id, segment_id, basis
        FROM matches m WHERE NOT EXISTS (
            SELECT 1 FROM governance.quality_issue qi
            WHERE qi.target_kind = m.kind AND qi.target_id = m.target_id
                AND qi.issue_type = :issue_type
        ) ORDER BY kind, target_id, evidence_id, segment_id LIMIT :limit
    """
    with SessionLocal.begin() as session:
        matches = session.execute(text(common), {
            "query": query, "version_id": version_id, "build_id": build_id,
            "source_ids": source_ids, "limit": MAX_MATCHES, "issue_type": ISSUE_TYPE,
            "segment_types": sorted(CITABLE_SEGMENT_TYPES),
        }).all()
        # Acquire every target lock before any append_event takes the global audit
        # head lock. Overlapping batches must not wait on targets while holding it.
        targets = {}
        for kind, target_id, *_ in matches:
            targets[kind, target_id] = session.scalar(select(ISSUE_TARGETS[kind]).where(
                ISSUE_TARGETS[kind].id == target_id,
            ).with_for_update())
        for kind, target_id, evidence_id, segment_id, basis in matches:
            # Approval uses the same target lock. Recheck after waiting for it.
            target = targets[kind, target_id]
            if kind in REVIEW_TARGETS:
                item_field = getattr(KnowledgeVersionItem, REVIEW_TARGETS[kind][1])
                if target.status not in {"DRAFT", "REVIEWED"} or session.scalar(
                    select(KnowledgeVersionItem.id).join(KnowledgeVersion).where(
                        item_field == target_id, KnowledgeVersion.status == "READY",
                    ).limit(1)
                ) is not None:
                    continue
            if evidence_id is not None:
                evidence = session.get(EvidenceRevision, evidence_id)
                segments = list(session.scalars(select(TextSegmentRevision)
                    .join(EvidenceSegmentRef,
                          EvidenceSegmentRef.segment_revision_id == TextSegmentRevision.id)
                    .where(EvidenceSegmentRef.evidence_revision_id == evidence_id)
                    .order_by(EvidenceSegmentRef.sequence_no)))
                if (not segments or evidence.status not in {"DRAFT", "REVIEWED"}
                        or any(s.source_revision_id != evidence.source_revision_id for s in segments)):
                    raise ValueError("unpublished candidate has invalid segment provenance")
            else:
                segments = [session.get(TextSegmentRevision, segment_id)]
            description = json.dumps({
                "policy": POLICY, "match_basis": basis, "requires_human_review": True,
                "query_text": original_query, "normalized_query": query,
                "knowledge_version_id": str(version_id), "index_build_id": str(build_id),
                "task_id": str(task_id) if task_id else None,
                "source_revision_id": str(segments[0].source_revision_id),
                "evidence_revision_id": str(evidence_id) if evidence_id else None,
                "segments": [{"segment_revision_id": str(s.id), "checksum": s.checksum,
                              "locator": s.structural_locator} for s in segments],
            }, ensure_ascii=False, sort_keys=True)
            open_quality_issue(
                kind, target_id, issue_type=ISSUE_TYPE, severity="WARNING",
                description=description, actor_id="retrieval-quality",
                _session=session, deduplicate=True,
            )
