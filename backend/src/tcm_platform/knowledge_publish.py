"""Human review, frozen knowledge snapshots, and the atomic publish barrier."""

import hashlib
import json
from contextlib import nullcontext
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tcm_platform.audit import append_event
from tcm_platform.db import SessionLocal
from tcm_platform.ids import new_id
from tcm_platform.knowledge_formula_provenance import validate_formula_field_sources
from tcm_platform.knowledge_service import trace_evidence, trace_knowledge
from tcm_platform.knowledge_terms import validate_term_resolution
from tcm_platform.models import (
    Concept,
    ConceptEvidence,
    EmbeddingRecord,
    EvidenceRevision,
    FormulaEvidence,
    FormulaIngredient,
    FormulaRevision,
    Herb,
    HerbEvidence,
    HumanReview,
    IndexBuild,
    KnowledgeRelation,
    KnowledgeRuntimeState,
    KnowledgeSupersession,
    KnowledgeVersion,
    KnowledgeVersionItem,
    KnowledgeVersionReference,
    QualityIssue,
    RelationEvidence,
    RetrievalChunk,
    SourceRevision,
    TextSegmentRevision,
    utc_now,
)
from tcm_platform.release_snapshot import create_release_snapshot, validate_release_snapshot

REVIEW_TARGETS = {
    "evidence_revision": (EvidenceRevision, "evidence_revision_id"),
    "concept": (Concept, "concept_id"),
    "relation": (KnowledgeRelation, "relation_id"),
    "herb": (Herb, "herb_id"),
    "formula_revision": (FormulaRevision, "formula_revision_id"),
}
ISSUE_SEVERITIES = frozenset({"BLOCKER", "WARNING", "INFO"})
ISSUE_TARGETS = {
    **{kind: model for kind, (model, _) in REVIEW_TARGETS.items()},
    "source_revision": SourceRevision,
    "text_segment_revision": TextSegmentRevision,
    "index_build": IndexBuild,
}


def _target(session: Session, kind: str, object_id: UUID, *, lock: bool = False):
    if kind not in REVIEW_TARGETS:
        raise ValueError("unsupported review target kind")
    model = REVIEW_TARGETS[kind][0]
    statement = select(model).where(model.id == object_id)
    if lock:
        statement = statement.with_for_update()
    obj = session.scalar(statement)
    if obj is None:
        raise ValueError("review target does not exist")
    return obj


def _open_blockers(session: Session, kind: str | None = None, object_id: UUID | None = None) -> int:
    query = select(func.count()).select_from(QualityIssue).where(
        QualityIssue.status == "OPEN", QualityIssue.severity == "BLOCKER"
    )
    if kind is not None:
        query = query.where(QualityIssue.target_kind == kind, QualityIssue.target_id == object_id)
    return session.scalar(query) or 0


def open_quality_issue(
    kind: str,
    object_id: UUID,
    *,
    issue_type: str,
    severity: str,
    description: str,
    actor_id: str = "local-curator",
    _session: Session | None = None,
    deduplicate: bool = False,
) -> UUID:
    if severity not in ISSUE_SEVERITIES:
        raise ValueError("invalid quality issue severity")
    if not issue_type.strip() or not description.strip():
        raise ValueError("quality issue requires type and description")
    if kind not in ISSUE_TARGETS:
        raise ValueError("unsupported quality issue target kind")
    with nullcontext(_session) if _session is not None else SessionLocal.begin() as session:
        target = select(ISSUE_TARGETS[kind]).where(ISSUE_TARGETS[kind].id == object_id)
        if deduplicate:
            target = target.with_for_update()
        if session.scalar(target) is None:
            raise ValueError("quality issue target does not exist")
        if deduplicate:
            # Serialize on the target; closed issues remain a human decision.
            existing = session.scalar(select(QualityIssue.id).where(
                QualityIssue.target_kind == kind, QualityIssue.target_id == object_id,
                QualityIssue.issue_type == issue_type.strip(),
            ).order_by(QualityIssue.created_at, QualityIssue.id).limit(1))
            if existing is not None:
                return existing
        issue_id = new_id()
        session.add(QualityIssue(
            id=issue_id, issue_type=issue_type.strip(), severity=severity,
            target_kind=kind, target_id=object_id,
            description=description.strip(), status="OPEN",
        ))
        append_event(
            session, event_type="quality_issue.opened", actor_id=actor_id,
            aggregate_id=issue_id, payload={"target_kind": kind, "target_id": str(object_id)},
        )
        return issue_id


def resolve_quality_issue(
    issue_id: UUID, *, reviewer_id: str, note: str, waive: bool = False
) -> None:
    if not reviewer_id.strip() or not note.strip():
        raise ValueError("resolution requires reviewer and note")
    with SessionLocal.begin() as session:
        issue = session.scalar(select(QualityIssue).where(QualityIssue.id == issue_id).with_for_update())
        if issue is None or issue.status != "OPEN":
            raise ValueError("quality issue is missing or already resolved")
        issue.status = "WAIVED" if waive else "RESOLVED"
        issue.resolution_note = note.strip()
        issue.resolved_by = reviewer_id.strip()
        issue.resolved_at = utc_now()
        append_event(
            session, event_type="quality_issue.waived" if waive else "quality_issue.resolved",
            actor_id=reviewer_id, aggregate_id=issue.id,
            payload={"target_kind": issue.target_kind, "target_id": str(issue.target_id)},
        )


def review_object(
    kind: str,
    object_id: UUID,
    *,
    reviewer_id: str,
    decision: str,
    note: str,
) -> UUID:
    """Record every human decision; a published object's review state is frozen."""
    if decision not in {"APPROVE", "REJECT"}:
        raise ValueError("review decision must be APPROVE or REJECT")
    if not reviewer_id.strip() or not note.strip():
        raise ValueError("human review requires reviewer and note")
    if decision == "APPROVE":
        if kind == "evidence_revision":
            trace_evidence(object_id)
        else:
            trace_knowledge(kind, object_id)
    with SessionLocal.begin() as session:
        obj = _target(session, kind, object_id, lock=True)
        item_field = getattr(KnowledgeVersionItem, REVIEW_TARGETS[kind][1])
        published = session.scalar(
            select(KnowledgeVersionItem.id)
            .join(KnowledgeVersion)
            .where(item_field == object_id, KnowledgeVersion.status == "READY")
            .limit(1)
        )
        if published is not None:
            raise ValueError("published knowledge cannot be reviewed in place")
        if kind in {"concept", "relation", "herb"} and session.scalar(
            select(KnowledgeSupersession.id).where(
                KnowledgeSupersession.target_kind == kind,
                KnowledgeSupersession.new_object_id == object_id,
            ).limit(1)
        ) is not None:
            raise ValueError("linked knowledge revision cannot be reviewed in place")
        if decision == "APPROVE" and _open_blockers(session, kind, object_id):
            raise ValueError("open blocker prevents approval")
        if decision == "APPROVE" and kind != "evidence_revision":
            links = {
                "concept": (ConceptEvidence, ConceptEvidence.concept_id),
                "relation": (RelationEvidence, RelationEvidence.relation_id),
                "herb": (HerbEvidence, HerbEvidence.herb_id),
                "formula_revision": (FormulaEvidence, FormulaEvidence.formula_revision_id),
            }
            link_model, foreign_key = links[kind]
            evidence_ids = list(session.scalars(
                select(link_model.evidence_revision_id).where(foreign_key == object_id)
            ))
            if not evidence_ids or any(
                session.get(EvidenceRevision, revision_id).status != "REVIEWED"
                for revision_id in evidence_ids
            ):
                raise ValueError("cited evidence must be reviewed first")
        if decision == "APPROVE" and kind == "formula_revision":
            if obj.provenance_version == 0:
                raise ValueError("legacy formula draft requires a new revision with field sources")
            validate_formula_field_sources(session, object_id, require_complete=True)
        if decision == "APPROVE" and kind == "concept":
            validate_term_resolution(session, object_id, require_resolved=True)
        obj.status = "REVIEWED" if decision == "APPROVE" else "REJECTED"
        review_id = new_id()
        session.add(HumanReview(
            id=review_id, target_kind=kind, target_id=object_id,
            reviewer_id=reviewer_id.strip(), decision=decision, note=note.strip(),
        ))
        append_event(
            session, event_type="knowledge.reviewed", actor_id=reviewer_id,
            aggregate_id=object_id, payload={"kind": kind, "decision": decision},
        )
        return review_id


REVISION_TARGETS = frozenset({"concept", "relation", "herb"})


def supersede_reviewed_object(
    kind: str, old_id: UUID, replacement_id: UUID, *, actor_id: str = "local-curator"
) -> int:
    """Link a reviewed replacement to a published row without editing either row."""
    if kind not in REVISION_TARGETS or old_id == replacement_id:
        raise ValueError("unsupported or identical knowledge replacement")
    if not actor_id.strip():
        raise ValueError("actor is required")
    model, field_name = REVIEW_TARGETS[kind]
    with SessionLocal.begin() as session:
        runtime = session.scalar(select(KnowledgeRuntimeState).where(
            KnowledgeRuntimeState.id == 1
        ).with_for_update())
        if runtime is None:
            raise RuntimeError("knowledge runtime state is not initialized")
        old = session.scalar(select(model).where(model.id == old_id).with_for_update())
        new = session.scalar(select(model).where(model.id == replacement_id).with_for_update())
        if old is None or new is None or old.status != "REVIEWED" or new.status != "REVIEWED":
            raise ValueError("both knowledge revisions must be reviewed")
        item_field = getattr(KnowledgeVersionItem, field_name)
        published = session.scalar(select(KnowledgeVersionItem.id).join(KnowledgeVersion).where(
            item_field == old_id, KnowledgeVersion.status == "READY"
        ).limit(1))
        if published is None:
            raise ValueError("old knowledge revision must be published")
        already_snapshotted = session.scalar(select(KnowledgeVersionItem.id).where(
            item_field == replacement_id
        ).limit(1))
        if already_snapshotted is not None:
            raise ValueError("replacement was already frozen in a knowledge version")
        if session.scalar(select(KnowledgeSupersession.id).where(
            KnowledgeSupersession.target_kind == kind,
            KnowledgeSupersession.old_object_id == old_id,
        ).limit(1)) is not None:
            raise ValueError("old knowledge revision was already superseded")
        predecessor = session.scalar(select(KnowledgeSupersession).where(
            KnowledgeSupersession.target_kind == kind,
            KnowledgeSupersession.new_object_id == old_id,
        ))
        if session.scalar(select(KnowledgeSupersession.id).where(
            KnowledgeSupersession.target_kind == kind,
            KnowledgeSupersession.new_object_id == replacement_id,
        ).limit(1)) is not None:
            raise ValueError("replacement already belongs to a revision lineage")
        root_id = predecessor.root_object_id if predecessor else old_id
        revision_no = predecessor.revision_no + 1 if predecessor else 2
        session.add(KnowledgeSupersession(
            id=new_id(), target_kind=kind, old_object_id=old_id,
            new_object_id=replacement_id, root_object_id=root_id, revision_no=revision_no,
        ))
        append_event(session, event_type="knowledge.revision_superseded", actor_id=actor_id,
                     aggregate_id=root_id, payload={
                         "kind": kind, "old_object_id": str(old_id),
                         "new_object_id": str(replacement_id), "revision_no": revision_no,
                     })
        return revision_no


def _snapshot_items(session: Session) -> dict[str, list[UUID]]:
    items: dict[str, list[UUID]] = {}
    for kind, (model, _) in REVIEW_TARGETS.items():
        if kind == "evidence_revision":
            rows = list(session.scalars(select(EvidenceRevision).where(
                EvidenceRevision.status == "REVIEWED"
            ).order_by(EvidenceRevision.evidence_id, EvidenceRevision.revision_no.desc())))
            seen = set()
            items[kind] = []
            for row in rows:
                if row.evidence_id not in seen:
                    items[kind].append(row.id)
                    seen.add(row.evidence_id)
        elif kind == "formula_revision":
            rows = list(session.scalars(select(FormulaRevision).where(
                FormulaRevision.status == "REVIEWED"
            ).order_by(FormulaRevision.formula_id, FormulaRevision.revision_no.desc())))
            seen = set()
            items[kind] = []
            for row in rows:
                if row.formula_id not in seen:
                    items[kind].append(row.id)
                    seen.add(row.formula_id)
        else:
            excluded = select(KnowledgeSupersession.old_object_id).where(
                KnowledgeSupersession.target_kind == kind
            )
            items[kind] = list(session.scalars(select(model.id).where(
                model.status == "REVIEWED", model.id.not_in(excluded)
            )))
    return items


def _validate_replacement_references(session: Session, items: dict[str, list[UUID]]) -> None:
    """Newly linked revisions must cite evidence and objects selected in this snapshot."""
    for kind, link_model, object_field in (
        ("concept", ConceptEvidence, ConceptEvidence.concept_id),
        ("relation", RelationEvidence, RelationEvidence.relation_id),
        ("herb", HerbEvidence, HerbEvidence.herb_id),
    ):
        replacements = set(session.scalars(select(KnowledgeSupersession.new_object_id).where(
            KnowledgeSupersession.target_kind == kind,
            KnowledgeSupersession.new_object_id.in_(items[kind]),
        )))
        if not replacements:
            continue
        stale = session.scalar(select(link_model.evidence_revision_id).where(
            object_field.in_(replacements),
            link_model.evidence_revision_id.not_in(items["evidence_revision"]),
        ).limit(1))
        if stale is not None:
            raise ValueError("replacement cites evidence outside the new snapshot")
    replaced_concepts = select(KnowledgeSupersession.old_object_id).where(
        KnowledgeSupersession.target_kind == "concept"
    )
    if session.scalar(select(KnowledgeRelation.id).where(
        KnowledgeRelation.id.in_(items["relation"]),
        (KnowledgeRelation.subject_concept_id.in_(replaced_concepts)
         | KnowledgeRelation.object_concept_id.in_(replaced_concepts)),
    ).limit(1)) is not None:
        raise ValueError("relation still points to a superseded concept")
    replaced_herbs = select(KnowledgeSupersession.old_object_id).where(
        KnowledgeSupersession.target_kind == "herb"
    )
    if session.scalar(select(FormulaIngredient.id).where(
        FormulaIngredient.formula_revision_id.in_(items["formula_revision"]),
        FormulaIngredient.herb_id.in_(replaced_herbs),
    ).limit(1)) is not None:
        raise ValueError("formula still points to a superseded herb")


def _manifest(items: dict[str, list[UUID]]) -> str:
    canonical = json.dumps(
        {kind: sorted(str(item_id) for item_id in ids) for kind, ids in sorted(items.items())},
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _validate_formula_provenance(session: Session, formula_ids: list[UUID]) -> None:
    """Keep old reviewed revisions usable; recheck every new field-level revision."""
    for revision in session.scalars(select(FormulaRevision).where(
        FormulaRevision.id.in_(formula_ids), FormulaRevision.provenance_version != 0,
    )):
        validate_formula_field_sources(session, revision.id, require_complete=True)


def _validate_terms(session: Session, concept_ids: list[UUID]) -> None:
    for concept_id in concept_ids:
        validate_term_resolution(session, concept_id, require_resolved=True)


def _historical_references(
    session: Session, items: dict[str, list[UUID]]
) -> set[tuple[str, UUID, UUID]]:
    active_evidence = set(items["evidence_revision"])
    references = set()
    for kind, link_model, object_field in (
        ("concept", ConceptEvidence, ConceptEvidence.concept_id),
        ("relation", RelationEvidence, RelationEvidence.relation_id),
        ("herb", HerbEvidence, HerbEvidence.herb_id),
        ("formula_revision", FormulaEvidence, FormulaEvidence.formula_revision_id),
    ):
        if not items[kind]:
            continue
        for object_id, evidence_id in session.execute(select(
            object_field, link_model.evidence_revision_id
        ).where(object_field.in_(items[kind]))):
            if evidence_id not in active_evidence:
                if session.get(EvidenceRevision, evidence_id).status != "REVIEWED":
                    raise ValueError("historical reference is not reviewed")
                references.add((kind, object_id, evidence_id))
    return references


def _reference_manifest(references: set[tuple[str, UUID, UUID]]) -> str:
    canonical = json.dumps(sorted(
        [kind, str(object_id), str(evidence_id)]
        for kind, object_id, evidence_id in references
    ), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def create_knowledge_version(*, actor_id: str = "local-curator") -> UUID:
    """Freeze reviewed object IDs; an open blocker stops the snapshot."""
    with SessionLocal.begin() as session:
        runtime = session.scalar(
            select(KnowledgeRuntimeState).where(KnowledgeRuntimeState.id == 1).with_for_update()
        )
        if runtime is None:
            raise RuntimeError("knowledge runtime state is not initialized")
        if _open_blockers(session):
            raise ValueError("open blocking quality issues prevent snapshot")
        items = _snapshot_items(session)
        if not items["evidence_revision"]:
            raise ValueError("knowledge version requires reviewed evidence")
        _validate_replacement_references(session, items)
        _validate_formula_provenance(session, items["formula_revision"])
        _validate_terms(session, items["concept"])
        references = _historical_references(session, items)
        version_no = (session.scalar(select(func.max(KnowledgeVersion.version_no))) or 0) + 1
        version_id = new_id()
        manifest = _manifest(items)
        reference_manifest = _reference_manifest(references)
        session.add(KnowledgeVersion(
            id=version_id, public_id=f"KV-{version_no:06d}", version_no=version_no,
            status="PRE_PUBLISH_SNAPSHOT", manifest_hash=manifest,
            reference_manifest_hash=reference_manifest,
        ))
        session.flush()
        session.add_all([
            KnowledgeVersionItem(
                knowledge_version_id=version_id,
                **{REVIEW_TARGETS[kind][1]: object_id},
            )
            for kind, ids in items.items() for object_id in ids
        ])
        session.add_all([
            KnowledgeVersionReference(
                id=new_id(), knowledge_version_id=version_id,
                target_kind=kind, target_id=object_id, evidence_revision_id=evidence_id,
            ) for kind, object_id, evidence_id in sorted(references)
        ])
        append_event(
            session, event_type="knowledge_version.snapshotted", actor_id=actor_id,
            aggregate_id=version_id,
            payload={"manifest_hash": manifest,
                     "reference_manifest_hash": reference_manifest,
                     "reference_count": len(references),
                     "item_count": sum(map(len, items.values()))},
        )
        return version_id


def create_index_build(
    version_id: UUID, *, configuration: dict, actor_id: str = "local-curator"
) -> UUID:
    """Register a derivation request; E6 must verify both real indexes."""
    from tcm_platform.outbound_policy import POLICY_VERSION, current_mode, version_source_ids

    with SessionLocal.begin() as session:
        version = session.get(KnowledgeVersion, version_id)
        if version is None or version.status not in {"PRE_PUBLISH_SNAPSHOT", "INDEXING"}:
            raise ValueError("knowledge version is not ready for index build")
        if any(key in configuration for key in (
            "outbound_mode", "outbound_source_ids", "outbound_policy_version"
        )):
            raise ValueError("outbound policy is assigned by the service")
        configuration = {**configuration,
                         "outbound_mode": current_mode(),
                         "outbound_policy_version": POLICY_VERSION,
                         "outbound_source_ids": [str(item) for item in
                                                 version_source_ids(session, version_id)]}
        build_id = new_id()
        session.add(IndexBuild(
            id=build_id, knowledge_version_id=version_id,
            status="PENDING", fts_status="PENDING", vector_status="PENDING",
            manifest_hash=version.manifest_hash, configuration=configuration,
        ))
        version.status = "INDEXING"
        append_event(
            session, event_type="index_build.requested", actor_id=actor_id,
            aggregate_id=build_id, payload={"knowledge_version_id": str(version_id)},
        )
        return build_id


def _version_items(session: Session, version_id: UUID) -> dict[str, list[UUID]]:
    rows = list(session.scalars(select(KnowledgeVersionItem).where(
        KnowledgeVersionItem.knowledge_version_id == version_id
    )))
    items = {kind: [] for kind in REVIEW_TARGETS}
    for row in rows:
        for kind, (_, field) in REVIEW_TARGETS.items():
            value = getattr(row, field)
            if value is not None:
                items[kind].append(value)
    return items


def activate_knowledge_version(
    version_id: UUID, build_id: UUID, *, actor_id: str = "local-curator",
    restore_snapshot_id: UUID | None = None,
) -> UUID | None:
    """Switch both pointers only after content and the configured index gates pass."""
    from tcm_platform.publication_config import is_local_configuration, validate_local_configuration

    with SessionLocal.begin() as session:
        runtime = session.scalar(
            select(KnowledgeRuntimeState).where(KnowledgeRuntimeState.id == 1).with_for_update()
        )
        if runtime is None:
            raise RuntimeError("knowledge runtime state is not initialized")
        version = session.scalar(
            select(KnowledgeVersion).where(KnowledgeVersion.id == version_id).with_for_update()
        )
        build = session.scalar(select(IndexBuild).where(IndexBuild.id == build_id).with_for_update())
        if version is None or build is None or build.knowledge_version_id != version_id:
            raise ValueError("index build does not belong to knowledge version")
        if version.status not in {"INDEXING", "VALIDATING", "READY"}:
            raise ValueError("knowledge version has not reached index validation")
        local_index = is_local_configuration(build.configuration)
        if local_index:
            validate_local_configuration(build.configuration)
        if (
            build.status != "READY" or build.fts_status != "READY"
            or build.vector_status != ("NOT_APPLICABLE" if local_index else "READY")
            or build.validated_at is None
            or build.manifest_hash != version.manifest_hash
        ):
            raise ValueError("configured FTS/vector index builds must be validated")
        items = _version_items(session, version_id)
        if _manifest(items) != version.manifest_hash:
            raise ValueError("knowledge version snapshot manifest differs")
        if version.reference_manifest_hash is not None:
            frozen_references = {tuple(row) for row in session.execute(select(
                KnowledgeVersionReference.target_kind,
                KnowledgeVersionReference.target_id,
                KnowledgeVersionReference.evidence_revision_id,
            ).where(KnowledgeVersionReference.knowledge_version_id == version_id))}
            current_references = _historical_references(session, items)
            if (frozen_references != current_references
                    or _reference_manifest(frozen_references)
                    != version.reference_manifest_hash):
                raise ValueError("knowledge version historical references differ")
        if _open_blockers(session):
            raise ValueError("open blocking quality issues prevent activation")
        for kind, ids in items.items():
            model = REVIEW_TARGETS[kind][0]
            if any(session.get(model, object_id).status != "REVIEWED" for object_id in ids):
                raise ValueError("snapshot contains an object without human approval")
        if not items["evidence_revision"]:
            raise ValueError("snapshot has no evidence")
        _validate_formula_provenance(session, items["formula_revision"])
        _validate_terms(session, items["concept"])
        chunks = list(session.execute(select(
            RetrievalChunk.id, RetrievalChunk.evidence_revision_id
        ).where(RetrievalChunk.index_build_id == build_id)))
        indexed_ids = {revision_id for _, revision_id in chunks}
        chunk_ids = {chunk_id for chunk_id, _ in chunks}
        embedded_chunk_ids = set(session.scalars(select(EmbeddingRecord.chunk_id).where(
            EmbeddingRecord.index_build_id == build_id,
            EmbeddingRecord.model_version == build.configuration.get("embedding_model"),
        )))
        if (indexed_ids != set(items["evidence_revision"])
                or len(chunks) != len(indexed_ids)
                or (local_index and session.scalar(select(func.count()).select_from(
                    EmbeddingRecord).where(EmbeddingRecord.index_build_id == build_id)) != 0)
                or (not local_index and embedded_chunk_ids != chunk_ids)):
            raise ValueError("target FTS/vector index is incomplete")
        previous_version_id = runtime.active_knowledge_version_id
        previous_build_id = runtime.active_index_build_id
        if (previous_version_id is None) != (previous_build_id is None):
            raise ValueError("active knowledge/index pointers are inconsistent")
        if restore_snapshot_id is not None:
            if previous_version_id is None or previous_build_id is None:
                raise ValueError("release snapshot cannot restore an empty active pair")
            validate_release_snapshot(
                session, restore_snapshot_id,
                source_version_id=version_id, source_build_id=build_id,
                target_version_id=previous_version_id, target_build_id=previous_build_id,
            )
        release_snapshot = (
            create_release_snapshot(
                session, previous_version_id, previous_build_id, version_id, build_id
            ) if (previous_version_id is not None and previous_build_id is not None
                  and (previous_version_id, previous_build_id) != (version_id, build_id))
            else None
        )
        version.status = "READY"
        version.ready_at = version.ready_at or utc_now()
        runtime.active_knowledge_version_id = version_id
        runtime.active_index_build_id = build_id
        runtime.updated_at = utc_now()
        append_event(
            session, event_type="knowledge_version.activated", actor_id=actor_id,
            aggregate_id=version_id,
            payload={
                "index_build_id": str(build_id),
                "previous_knowledge_version_id": (
                    str(previous_version_id) if previous_version_id else None
                ),
                "previous_index_build_id": str(previous_build_id) if previous_build_id else None,
                "release_snapshot_id": str(release_snapshot.id) if release_snapshot else None,
                "restored_from_snapshot_id": (
                    str(restore_snapshot_id) if restore_snapshot_id else None
                ),
                "historical_switch": previous_version_id is not None
                and version.version_no < session.get(KnowledgeVersion, previous_version_id).version_no,
            },
        )
        return release_snapshot.id if release_snapshot else None


def compare_knowledge_versions(left_id: UUID, right_id: UUID) -> dict:
    with SessionLocal() as session:
        if session.get(KnowledgeVersion, left_id) is None:
            raise ValueError("left knowledge version does not exist")
        if session.get(KnowledgeVersion, right_id) is None:
            raise ValueError("right knowledge version does not exist")
        left, right = _version_items(session, left_id), _version_items(session, right_id)
        difference = {
            kind: {
                "added": sorted(str(item) for item in set(right[kind]) - set(left[kind])),
                "removed": sorted(str(item) for item in set(left[kind]) - set(right[kind])),
            }
            for kind in REVIEW_TARGETS
        }
        revisions = {}
        for kind, model, identity_field in (
            ("evidence_revision", EvidenceRevision, "evidence_id"),
            ("formula_revision", FormulaRevision, "formula_id"),
        ):
            ids = set(left[kind]) | set(right[kind])
            rows = list(session.scalars(select(model).where(model.id.in_(ids))))
            by_id = {row.id: row for row in rows}
            left_by_identity = {getattr(by_id[item], identity_field): item for item in left[kind]}
            right_by_identity = {getattr(by_id[item], identity_field): item for item in right[kind]}
            changes = []
            for identity_id in sorted(set(left_by_identity) & set(right_by_identity)):
                old_id, new_id = left_by_identity[identity_id], right_by_identity[identity_id]
                if old_id == new_id:
                    continue
                change = {
                    "identity_id": str(identity_id),
                    "from_revision_id": str(old_id),
                    "to_revision_id": str(new_id),
                }
                if kind == "evidence_revision":
                    citations = []
                    for target_kind, link_model, field in (
                        ("concept", ConceptEvidence, ConceptEvidence.concept_id),
                        ("relation", RelationEvidence, RelationEvidence.relation_id),
                        ("herb", HerbEvidence, HerbEvidence.herb_id),
                        ("formula_revision", FormulaEvidence,
                         FormulaEvidence.formula_revision_id),
                    ):
                        linked_ids = session.scalars(select(field).where(
                            link_model.evidence_revision_id == old_id
                        ))
                        citations.extend({
                            "kind": target_kind,
                            "object_id": str(linked_id),
                            "retained_in_target": linked_id in right[target_kind],
                        } for linked_id in linked_ids)
                    change["citation_impact"] = sorted(
                        citations, key=lambda item: (item["kind"], item["object_id"])
                    )
                changes.append(change)
            revisions[kind] = changes
        for kind in sorted(REVISION_TARGETS):
            links = list(session.scalars(select(KnowledgeSupersession).where(
                KnowledgeSupersession.target_kind == kind
            )))
            lineage = {link.old_object_id: link.root_object_id for link in links}
            lineage.update({link.new_object_id: link.root_object_id for link in links})
            revision_numbers = {link.new_object_id: link.revision_no for link in links}
            left_by_root = {lineage.get(item, item): item for item in left[kind]}
            right_by_root = {lineage.get(item, item): item for item in right[kind]}
            revisions[kind] = [{
                "identity_id": str(root),
                "from_revision_id": str(left_by_root[root]),
                "to_revision_id": str(right_by_root[root]),
                "revision_no": revision_numbers.get(right_by_root[root], 1),
            } for root in sorted(set(left_by_root) & set(right_by_root))
                if left_by_root[root] != right_by_root[root]]
        difference["revision_changes"] = revisions
        frozen = {}
        for side, version_id in (("left", left_id), ("right", right_id)):
            frozen[side] = {tuple(row) for row in session.execute(select(
                KnowledgeVersionReference.target_kind,
                KnowledgeVersionReference.target_id,
                KnowledgeVersionReference.evidence_revision_id,
            ).where(KnowledgeVersionReference.knowledge_version_id == version_id))}
        difference["historical_reference_changes"] = {
            direction: [
                {"kind": kind, "object_id": str(object_id),
                 "evidence_revision_id": str(evidence_id)}
                for kind, object_id, evidence_id in sorted(rows)
            ]
            for direction, rows in (
                ("added", frozen["right"] - frozen["left"]),
                ("removed", frozen["left"] - frozen["right"]),
            )
        }
        return difference
