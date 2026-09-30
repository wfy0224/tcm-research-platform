"""Conservative object-to-Evidence candidates within a frozen publication and scope."""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from tcm_platform.retrieval_query import spelling_params, spelling_sql


def structured_candidates(
    session: Session, *, query: str, version_id: UUID, build_id: UUID,
    source_ids: list[UUID], limit: int,
) -> dict[str, list[UUID]]:
    """Match stored terms without merging identities or traversing synonym/graph edges.

    Every proof must itself be an indexed EvidenceRevision in this exact snapshot.
    Historical references alone never authorize substitution of a newer revision.
    Adjudicated concepts use their own mention anchors, not comparison evidence.
    """
    if not source_ids:
        return {"structured": [], "relation": []}
    common = f"""
        WITH published AS (
            SELECT DISTINCT e.id
            FROM knowledge.evidence_revision e
            JOIN knowledge.evidence ev ON ev.id = e.evidence_id
            JOIN governance.knowledge_version_item vi ON vi.evidence_revision_id = e.id
                AND vi.knowledge_version_id = :version_id
            JOIN knowledge.retrieval_chunk rc ON rc.evidence_revision_id = e.id
                AND rc.index_build_id = :build_id
            WHERE e.status = 'REVIEWED' AND ev.source_id = ANY(:source_ids)
        ), scoped_concepts AS (
            SELECT DISTINCT c.id, ce.evidence_revision_id
            FROM knowledge.concept c
            JOIN governance.knowledge_version_item ci ON ci.concept_id = c.id
                AND ci.knowledge_version_id = :version_id
            JOIN knowledge.concept_term ct ON ct.concept_id = c.id
                AND ct.era IS NOT DISTINCT FROM c.era
                AND ct.school IS NOT DISTINCT FROM c.school
            JOIN knowledge.concept_evidence ce ON ce.concept_id = c.id
            JOIN published p ON p.id = ce.evidence_revision_id
            LEFT JOIN knowledge.term_resolution tr ON tr.resolved_concept_id = c.id
            WHERE c.status = 'REVIEWED' AND ct.term <> ''
                AND position({spelling_sql('ct.term')} in :query_key) > 0
                AND (tr.id IS NULL OR (
                    tr.decision <> 'UNRESOLVED' AND EXISTS (
                        SELECT 1 FROM jsonb_array_elements(tr.provenance->'mentions') anchor
                        WHERE anchor->>'evidence_revision_id' = p.id::text
                    )
                ))
        )
    """
    structured = f"""
        SELECT evidence_revision_id FROM scoped_concepts
        UNION
        SELECT fe.evidence_revision_id
        FROM knowledge.formula_revision f
        JOIN governance.knowledge_version_item fi ON fi.formula_revision_id = f.id
            AND fi.knowledge_version_id = :version_id
        JOIN knowledge.formula_evidence fe ON fe.formula_revision_id = f.id
        JOIN published p ON p.id = fe.evidence_revision_id
        WHERE f.status = 'REVIEWED' AND (
            (position({spelling_sql('f.original_name')} in :query_key) > 0 AND (
                f.provenance_version = 0 OR EXISTS (
                    SELECT 1 FROM knowledge.formula_field_source fs
                    WHERE fs.formula_revision_id = f.id AND fs.field_key = 'original_name'
                        AND fs.evidence_revision_id = p.id
                )
            )) OR EXISTS (
                SELECT 1 FROM knowledge.formula_ingredient i
                WHERE i.formula_revision_id = f.id AND i.original_name <> ''
                    AND position({spelling_sql('i.original_name')} in :query_key) > 0
                    AND (f.provenance_version = 0 OR EXISTS (
                        SELECT 1 FROM knowledge.formula_field_source fs
                        WHERE fs.formula_revision_id = f.id
                            AND fs.field_key = 'ingredients.' || i.sequence_no || '.original_name'
                            AND fs.evidence_revision_id = p.id
                    ))
            )
        )
        ORDER BY evidence_revision_id LIMIT :limit
    """
    relation = """
        SELECT DISTINCT re.evidence_revision_id
        FROM knowledge.relation r
        JOIN governance.knowledge_version_item ri ON ri.relation_id = r.id
            AND ri.knowledge_version_id = :version_id
        JOIN knowledge.concept s ON s.id = r.subject_concept_id AND s.status = 'REVIEWED'
        JOIN knowledge.concept o ON o.id = r.object_concept_id AND o.status = 'REVIEWED'
        JOIN governance.knowledge_version_item si ON si.concept_id = s.id
            AND si.knowledge_version_id = :version_id
        JOIN governance.knowledge_version_item oi ON oi.concept_id = o.id
            AND oi.knowledge_version_id = :version_id
        JOIN knowledge.relation_evidence re ON re.relation_id = r.id
        JOIN published p ON p.id = re.evidence_revision_id
        WHERE r.status = 'REVIEWED' AND EXISTS (
            SELECT 1 FROM scoped_concepts sc
            WHERE sc.id = s.id OR sc.id = o.id
        )
        ORDER BY re.evidence_revision_id LIMIT :limit
    """
    params = {**spelling_params(query), "version_id": version_id, "build_id": build_id,
              "source_ids": source_ids, "limit": limit}
    return {name: list(session.scalars(text(common + sql), params))
            for name, sql in (("structured", structured), ("relation", relation))}
