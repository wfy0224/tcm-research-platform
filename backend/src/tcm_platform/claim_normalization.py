"""Conservative, replayable normalization of audited research Claims.

Only exact text within the same source-revision context is deduplicated. A
Critique is a reported challenge, not proof that two statements contradict.
"""

import hashlib
import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from tcm_platform.audit import append_event
from tcm_platform.db import SessionLocal
from tcm_platform.ids import new_id
from tcm_platform.models import (
    AuditResult,
    CanonicalClaim,
    CanonicalClaimMember,
    Claim,
    ClaimEvidence,
    Critique,
    Dispute,
    EvidenceGap,
    EvidenceRequest,
    EvidenceRevision,
    Rebuttal,
    ResearchTask,
    SourceRevision,
    TaskEvidenceRef,
)


def _source_context(session: Session, claim_id: UUID) -> tuple[list[dict], list[str]]:
    rows = session.execute(
        select(TaskEvidenceRef, EvidenceRevision, SourceRevision)
        .join(ClaimEvidence, ClaimEvidence.task_evidence_ref_id == TaskEvidenceRef.id)
        .join(EvidenceRevision, EvidenceRevision.id == TaskEvidenceRef.evidence_revision_id)
        .join(SourceRevision, SourceRevision.id == EvidenceRevision.source_revision_id)
        .where(ClaimEvidence.claim_id == claim_id)
    ).all()
    context = {
        row.id: {"source_revision_id": str(row.id),
                 "era": row.metadata_snapshot.get("era"),
                 "school": row.metadata_snapshot.get("school")}
        for _, _, row in rows
    }
    return ([context[key] for key in sorted(context, key=str)],
            sorted({str(ref.evidence_revision_id) for ref, _, _ in rows}))


def _fingerprint(claim: Claim, context: list[dict]) -> str:
    value = {"claim_type": claim.claim_type,
             "assertion_text": " ".join(claim.assertion_text.split()),
             "source_context": context}
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def normalize_task_claims(
    task_id: UUID, *, actor_id: str = "claim-normalizer",
    session: Session | None = None,
) -> dict[str, int]:
    """Add missing projections in one transaction; safe to replay after a crash.

    Worker callers pass their transaction so normalization and its checkpoint
    commit together. The task row serializes concurrent normalizers.
    """
    if session is None:
        with SessionLocal.begin() as owned:
            return normalize_task_claims(task_id, actor_id=actor_id, session=owned)
    task = session.scalar(select(ResearchTask).where(
        ResearchTask.id == task_id
    ).with_for_update())
    if task is None or task.status not in {
        "FIRST_ROUND_COMPLETE", "DEBATING", "STOP_EVALUATION",
        "DEBATE_ROUND_COMPLETE", "COMPLETED",
    } or task.control_state != "ACTIVE":
        raise ValueError("research task is not ready for Claim normalization")

    counts = {"canonical_claims": 0, "members": 0, "disputes": 0, "gaps": 0,
              "superseded": 0}
    claims = list(session.scalars(select(Claim).where(
        Claim.task_id == task_id, Claim.status == "ACTIVE"
    ).order_by(Claim.created_at, Claim.id)))
    latest: dict[UUID, AuditResult] = {}
    member_by_claim: dict[UUID, CanonicalClaimMember] = {}
    citations: dict[UUID, list[str]] = {}
    for claim in claims:
        audit = session.scalar(select(AuditResult).where(
            AuditResult.claim_id == claim.id, AuditResult.task_id == task_id
        ).order_by(AuditResult.sequence_no.desc()).limit(1))
        if audit is None:
            continue
        latest[claim.id] = audit
        for gap in session.scalars(select(EvidenceGap).where(
            EvidenceGap.task_id == task_id, EvidenceGap.claim_id == claim.id,
            EvidenceGap.audit_result_id.is_not(None),
            EvidenceGap.audit_result_id != audit.id, EvidenceGap.status == "OPEN",
        )):
            gap.status = "SUPERSEDED"
            counts["superseded"] += 1
        for dispute in session.scalars(select(Dispute).where(
            Dispute.task_id == task_id, Dispute.target_claim_id == claim.id,
            Dispute.audit_result_id.is_not(None),
            Dispute.audit_result_id != audit.id, Dispute.status == "OPEN",
        )):
            dispute.status = "SUPERSEDED"
            counts["superseded"] += 1
        context, cited_ids = _source_context(session, claim.id)
        citations[claim.id] = cited_ids
        fingerprint = _fingerprint(claim, context)
        canonical = session.scalar(select(CanonicalClaim).where(
            CanonicalClaim.task_id == task_id, CanonicalClaim.fingerprint == fingerprint
        ))
        if canonical is None:
            canonical = CanonicalClaim(
                id=new_id(), task_id=task_id, fingerprint=fingerprint,
                claim_type=claim.claim_type,
                assertion_text=" ".join(claim.assertion_text.split()),
                source_context=context,
            )
            session.add(canonical)
            session.flush()
            counts["canonical_claims"] += 1
        member = session.scalar(select(CanonicalClaimMember).where(
            CanonicalClaimMember.claim_id == claim.id
        ))
        if member is None:
            member = CanonicalClaimMember(
                id=new_id(), canonical_claim_id=canonical.id,
                claim_id=claim.id, audit_result_id=audit.id,
            )
            session.add(member)
            counts["members"] += 1
        elif member.canonical_claim_id != canonical.id:
            raise ValueError("Claim source context changed after normalization")
        elif member.audit_result_id != audit.id:
            member.audit_result_id = audit.id
        member_by_claim[claim.id] = member

        if audit.stage == "MECHANICAL" and audit.verdict == "FAIL":
            _gap(session, task_id, claim.id, f"audit:{audit.id}",
                 "MECHANICAL_FAILURE", audit.rationale_summary, cited_ids,
                 audit_id=audit.id, counts=counts)
        elif audit.stage == "SEMANTIC" and audit.verdict in {
            "PARTIALLY_SUPPORTED", "UNSUPPORTED", "NOT_VERIFIABLE",
        }:
            _gap(session, task_id, claim.id, f"audit:{audit.id}",
                 audit.verdict, audit.rationale_summary,
                 audit.evidence_revision_ids, audit_id=audit.id, counts=counts)
        if audit.stage == "SEMANTIC" and audit.verdict == "CONTRADICTED":
            _dispute(session, task_id, member.canonical_claim_id, claim.id,
                     f"audit:{audit.id}", "AUDIT_CONTRADICTION",
                     audit.rationale_summary, [], audit.evidence_revision_ids,
                     audit_id=audit.id, counts=counts)
            _gap(session, task_id, claim.id, f"support:{audit.id}",
                 "SUPPORTING_EVIDENCE_UNVERIFIED",
                 "The contradicted Claim has no audited supporting evidence",
                 cited_ids, audit_id=audit.id, counts=counts)

    critiques = list(session.scalars(select(Critique).where(
        Critique.task_id == task_id
    ).order_by(Critique.created_at, Critique.id)))
    for critique in critiques:
        claim_id = critique.target_claim_id
        member = member_by_claim.get(claim_id)
        audit = latest.get(claim_id)
        if member is None or audit is None:
            continue
        if critique.issue_type == "CONTRADICTION":
            rebuttal = session.scalar(select(Rebuttal).where(
                Rebuttal.task_id == task_id, Rebuttal.critique_id == critique.id
            ).order_by(Rebuttal.round_no.desc()).limit(1))
            competing_id = rebuttal.revised_claim_id if rebuttal else None
            competing_audit = latest.get(competing_id) if competing_id else None
            if (competing_audit is None or competing_audit.stage != "SEMANTIC"
                    or competing_audit.verdict not in {"SUPPORTED", "PARTIALLY_SUPPORTED"}):
                competing_id = None  # An unverified revision is not a supported alternative.
            support = (audit.evidence_revision_ids
                       if audit.stage == "SEMANTIC" and audit.verdict in {
                           "SUPPORTED", "PARTIALLY_SUPPORTED"} else [])
            opposition = (audit.evidence_revision_ids
                          if audit.stage == "SEMANTIC" and audit.verdict == "CONTRADICTED"
                          else [])
            _dispute(session, task_id, member.canonical_claim_id, claim_id,
                     f"critique:{critique.id}:audit:{audit.id}",
                     "CRITIQUE_CONTRADICTION",
                     critique.rationale_summary, support, opposition,
                     critique_id=critique.id, audit_id=audit.id,
                     competing_id=competing_id, counts=counts)
            if not opposition:
                _gap(session, task_id, claim_id,
                     f"opposition:{critique.id}:audit:{audit.id}",
                     "OPPOSING_EVIDENCE_UNVERIFIED",
                     "The contradiction critique has no audited opposing evidence",
                     citations[claim_id], critique_id=critique.id,
                     audit_id=audit.id, counts=counts)
        if critique.issue_type == "EVIDENCE_GAP":
            _gap(session, task_id, claim_id, f"critique:{critique.id}",
                 "CRITIQUE_EVIDENCE_GAP", critique.rationale_summary,
                 citations[claim_id], critique_id=critique.id, counts=counts)
        requests = list(session.scalars(select(EvidenceRequest).where(
            EvidenceRequest.critique_id == critique.id,
            EvidenceRequest.task_id == task_id,
            EvidenceRequest.status == "NO_RESULT",
        )))
        for request in requests:
            _gap(session, task_id, claim_id, f"request:{request.id}",
                 "RETRIEVAL_NO_RESULT", request.query_text, [],
                 critique_id=critique.id, counts=counts)

    if any(counts.values()):
        append_event(session, event_type="research_task.claims_normalized",
                     actor_id=actor_id, aggregate_id=task_id, payload=counts)
    return counts


def _gap(session: Session, task_id: UUID, claim_id: UUID, source_key: str,
         reason_code: str, rationale: str, cited_ids: list[str],
         *, critique_id: UUID | None = None, audit_id: UUID | None = None,
         counts: dict[str, int]) -> None:
    if session.scalar(select(EvidenceGap.id).where(
        EvidenceGap.task_id == task_id, EvidenceGap.source_key == source_key
    )) is not None:
        return
    session.add(EvidenceGap(
        id=new_id(), task_id=task_id, source_key=source_key,
        claim_id=claim_id, critique_id=critique_id, audit_result_id=audit_id,
        reason_code=reason_code, rationale_summary=rationale,
        cited_evidence_ids=cited_ids, status="OPEN",
    ))
    counts["gaps"] += 1


def _dispute(session: Session, task_id: UUID, canonical_id: UUID, claim_id: UUID,
             source_key: str, reason_code: str, rationale: str,
             support: list[str], opposition: list[str],
             *, critique_id: UUID | None = None, audit_id: UUID | None = None,
             competing_id: UUID | None = None, counts: dict[str, int]) -> None:
    if session.scalar(select(Dispute.id).where(
        Dispute.task_id == task_id, Dispute.source_key == source_key
    )) is not None:
        return
    session.add(Dispute(
        id=new_id(), task_id=task_id, source_key=source_key,
        canonical_claim_id=canonical_id, target_claim_id=claim_id,
        competing_claim_id=competing_id, critique_id=critique_id,
        audit_result_id=audit_id, reason_code=reason_code,
        rationale_summary=rationale, supporting_evidence_ids=support,
        opposing_evidence_ids=opposition, status="OPEN",
    ))
    counts["disputes"] += 1
