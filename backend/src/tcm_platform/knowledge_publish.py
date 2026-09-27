"""Human review, frozen knowledge snapshots, and the atomic publish barrier."""

import hashlib
import json
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tcm_platform.audit import append_event
from tcm_platform.db import SessionLocal
from tcm_platform.ids import new_id
from tcm_platform.knowledge_service import trace_evidence, trace_knowledge
from tcm_platform.models import (
    Concept,
    ConceptEvidence,
    EvidenceRevision,
    FormulaEvidence,
    FormulaRevision,
    Herb,
    HerbEvidence,
    HumanReview,
    IndexBuild,
    KnowledgeRelation,
    KnowledgeRuntimeState,
    KnowledgeVersion,
    KnowledgeVersionItem,
    QualityIssue,
    RelationEvidence,
    SourceRevision,
    TextSegmentRevision,
    utc_now,
)

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
) -> UUID:
    if severity not in ISSUE_SEVERITIES:
        raise ValueError("invalid quality issue severity")
    if not issue_type.strip() or not description.strip():
        raise ValueError("quality issue requires type and description")
    if kind not in ISSUE_TARGETS:
        raise ValueError("unsupported quality issue target kind")
    with SessionLocal.begin() as session:
        if session.get(ISSUE_TARGETS[kind], object_id) is None:
            raise ValueError("quality issue target does not exist")
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
            items[kind] = list(session.scalars(select(model.id).where(model.status == "REVIEWED")))
    return items


def _manifest(items: dict[str, list[UUID]]) -> str:
    canonical = json.dumps(
        {kind: sorted(str(item_id) for item_id in ids) for kind, ids in sorted(items.items())},
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
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
        version_no = (session.scalar(select(func.max(KnowledgeVersion.version_no))) or 0) + 1
        version_id = new_id()
        manifest = _manifest(items)
        session.add(KnowledgeVersion(
            id=version_id, public_id=f"KV-{version_no:06d}", version_no=version_no,
            status="PRE_PUBLISH_SNAPSHOT", manifest_hash=manifest,
        ))
        session.flush()
        session.add_all([
            KnowledgeVersionItem(
                knowledge_version_id=version_id,
                **{REVIEW_TARGETS[kind][1]: object_id},
            )
            for kind, ids in items.items() for object_id in ids
        ])
        append_event(
            session, event_type="knowledge_version.snapshotted", actor_id=actor_id,
            aggregate_id=version_id,
            payload={"manifest_hash": manifest, "item_count": sum(map(len, items.values()))},
        )
        return version_id


def create_index_build(
    version_id: UUID, *, configuration: dict, actor_id: str = "local-curator"
) -> UUID:
    """Register a derivation request; E6 must verify both real indexes."""
    with SessionLocal.begin() as session:
        version = session.get(KnowledgeVersion, version_id)
        if version is None or version.status not in {"PRE_PUBLISH_SNAPSHOT", "INDEXING"}:
            raise ValueError("knowledge version is not ready for index build")
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
    version_id: UUID, build_id: UUID, *, actor_id: str = "local-curator"
) -> None:
    """Switch both active pointers only after content and both index gates pass."""
    with SessionLocal.begin() as session:
        runtime = session.scalar(
            select(KnowledgeRuntimeState).where(KnowledgeRuntimeState.id == 1).with_for_update()
        )
        version = session.scalar(
            select(KnowledgeVersion).where(KnowledgeVersion.id == version_id).with_for_update()
        )
        build = session.scalar(select(IndexBuild).where(IndexBuild.id == build_id).with_for_update())
        if version is None or build is None or build.knowledge_version_id != version_id:
            raise ValueError("index build does not belong to knowledge version")
        if version.status not in {"INDEXING", "VALIDATING", "READY"}:
            raise ValueError("knowledge version has not reached index validation")
        if (
            build.status != "READY" or build.fts_status != "READY"
            or build.vector_status != "READY" or build.validated_at is None
            or build.manifest_hash != version.manifest_hash
        ):
            raise ValueError("FTS and vector index builds must both be validated")
        items = _version_items(session, version_id)
        if _manifest(items) != version.manifest_hash:
            raise ValueError("knowledge version snapshot manifest differs")
        if _open_blockers(session):
            raise ValueError("open blocking quality issues prevent activation")
        for kind, ids in items.items():
            model = REVIEW_TARGETS[kind][0]
            if any(session.get(model, object_id).status != "REVIEWED" for object_id in ids):
                raise ValueError("snapshot contains an object without human approval")
        if not items["evidence_revision"]:
            raise ValueError("snapshot has no evidence")
        version.status = "READY"
        version.ready_at = version.ready_at or utc_now()
        runtime.active_knowledge_version_id = version_id
        runtime.active_index_build_id = build_id
        runtime.updated_at = utc_now()
        append_event(
            session, event_type="knowledge_version.activated", actor_id=actor_id,
            aggregate_id=version_id, payload={"index_build_id": str(build_id)},
        )


def compare_knowledge_versions(left_id: UUID, right_id: UUID) -> dict:
    with SessionLocal() as session:
        if session.get(KnowledgeVersion, left_id) is None:
            raise ValueError("left knowledge version does not exist")
        if session.get(KnowledgeVersion, right_id) is None:
            raise ValueError("right knowledge version does not exist")
        left, right = _version_items(session, left_id), _version_items(session, right_id)
        return {
            kind: {
                "added": sorted(str(item) for item in set(right[kind]) - set(left[kind])),
                "removed": sorted(str(item) for item in set(left[kind]) - set(right[kind])),
            }
            for kind in REVIEW_TARGETS
        }
