"""Read-only public projections of persisted research decisions."""

import hashlib
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from tcm_platform.models import (
    AgentRun,
    AuditResult,
    CanonicalClaim,
    CanonicalClaimMember,
    Claim,
    ClaimEvidence,
    Critique,
    Dispute,
    Evidence,
    EvidenceGap,
    EvidenceRequest,
    EvidenceRetrievalEvent,
    EvidenceRevision,
    HumanReviewRequest,
    Rebuttal,
    ResearchSubquestion,
    StopEvaluation,
    TaskEvidenceRef,
)


def public_ref(kind: str, value: UUID | None) -> str | None:
    if value is None:
        return None
    digest = hashlib.sha256(f"research-view-v1:{kind}:{value}".encode()).hexdigest()[:24]
    return f"{kind}-{digest}"


def evidence_ref(session: Session, revision_id: UUID) -> dict:
    revision = session.get(EvidenceRevision, revision_id)
    evidence = session.get(Evidence, revision.evidence_id)
    return {"evidence_id": evidence.public_id, "revision_no": revision.revision_no}


def task_details(session: Session, task_id: UUID) -> dict:
    def rows(model):
        return session.scalars(select(model).where(model.task_id == task_id)
                               .order_by(model.created_at, model.id)).all()

    claims = rows(Claim)
    audits = rows(AuditResult)
    critiques = rows(Critique)
    requests = rows(EvidenceRequest)
    retrievals = rows(EvidenceRetrievalEvent)
    rebuttals = rows(Rebuttal)
    disputes = rows(Dispute)
    gaps = rows(EvidenceGap)
    reviews = rows(HumanReviewRequest)
    stops = rows(StopEvaluation)
    runs = rows(AgentRun)
    canonical_claims = rows(CanonicalClaim)
    members = session.scalars(select(CanonicalClaimMember).where(
        CanonicalClaimMember.canonical_claim_id.in_(
            [row.id for row in canonical_claims]))).all() if canonical_claims else []
    canonical_members: dict[UUID, list[dict]] = {row.id: [] for row in canonical_claims}
    for member in members:
        canonical_members[member.canonical_claim_id].append({
            "claim_id": public_ref("CLM", member.claim_id),
            "audit_id": public_ref("AUD", member.audit_result_id),
        })
    subquestions = session.scalars(select(ResearchSubquestion).where(
        ResearchSubquestion.task_id == task_id).order_by(
        ResearchSubquestion.sequence_no)).all()
    refs = session.scalars(select(TaskEvidenceRef).where(
        TaskEvidenceRef.task_id == task_id)).all()
    ref_by_id = {ref.id: ref.evidence_revision_id for ref in refs}
    claim_evidence = session.scalars(select(ClaimEvidence).where(
        ClaimEvidence.claim_id.in_([claim.id for claim in claims]))).all() if claims else []
    evidence_by_claim: dict[UUID, list[dict]] = {claim.id: [] for claim in claims}
    for link in claim_evidence:
        evidence_by_claim[link.claim_id].append(
            evidence_ref(session, ref_by_id[link.task_evidence_ref_id]))

    return {
        "subquestions": [{"sequence_no": row.sequence_no, "question": row.question_text}
                         for row in subquestions],
        "evidence": [evidence_ref(session, ref.evidence_revision_id) for ref in refs],
        "agent_runs": [{"id": public_ref("RUN", row.id), "role": row.role,
                        "round_no": row.round_no, "status": row.status,
                        "model_version": row.model_version,
                        "review_summary": (row.output or {}).get("review_summary")
                        if row.role == "Critic" else None} for row in runs],
        "claims": [{"id": public_ref("CLM", row.id),
                    "parent_claim_id": public_ref("CLM", row.parent_claim_id),
                    "agent_run_id": public_ref("RUN", row.agent_run_id),
                    "agent_role": row.agent_role, "claim_type": row.claim_type,
                    "assertion_text": row.assertion_text,
                    "rationale_summary": row.rationale_summary,
                    "status": row.status, "audit_status": row.audit_status,
                    "evidence": evidence_by_claim[row.id]} for row in claims],
        "audits": [{"id": public_ref("AUD", row.id),
                    "claim_id": public_ref("CLM", row.claim_id),
                    "sequence_no": row.sequence_no, "stage": row.stage,
                    "verdict": row.verdict, "rationale_summary": row.rationale_summary,
                    "evidence": [evidence_ref(session, UUID(value))
                                 for value in row.evidence_revision_ids]}
                   for row in audits],
        "canonical_claims": [{"id": public_ref("CAN", row.id),
                              "claim_type": row.claim_type,
                              "assertion_text": row.assertion_text,
                              "members": canonical_members[row.id]}
                             for row in canonical_claims],
        "debate": {
            "critiques": [{"id": public_ref("CRT", row.id),
                           "target_claim_id": public_ref("CLM", row.target_claim_id),
                           "agent_run_id": public_ref("RUN", row.agent_run_id),
                           "issue_type": row.issue_type,
                           "rationale_summary": row.rationale_summary,
                           "status": row.status} for row in critiques],
            "evidence_requests": [{"id": public_ref("REQ", row.id),
                                   "critique_id": public_ref("CRT", row.critique_id),
                                   "query_text": row.query_text, "status": row.status,
                                   "result_count": row.result_count} for row in requests],
            "retrievals": [{"request_id": public_ref("REQ", row.evidence_request_id),
                            "evidence": evidence_ref(session, row.evidence_revision_id),
                            "rank": row.rank, "channels": row.channels}
                           for row in retrievals if row.evidence_request_id is not None],
            "rebuttals": [{"id": public_ref("REB", row.id),
                           "critique_id": public_ref("CRT", row.critique_id),
                           "round_no": row.round_no, "action": row.action,
                           "rationale_summary": row.rationale_summary,
                           "revised_claim_id": public_ref("CLM", row.revised_claim_id)}
                          for row in rebuttals],
        },
        "disputes": [{"id": public_ref("DSP", row.id),
                      "target_claim_id": public_ref("CLM", row.target_claim_id),
                      "competing_claim_id": public_ref("CLM", row.competing_claim_id),
                      "critique_id": public_ref("CRT", row.critique_id),
                      "audit_id": public_ref("AUD", row.audit_result_id),
                      "reason_code": row.reason_code,
                      "rationale_summary": row.rationale_summary, "status": row.status,
                      "supporting_evidence": [evidence_ref(session, UUID(value))
                                              for value in row.supporting_evidence_ids],
                      "opposing_evidence": [evidence_ref(session, UUID(value))
                                            for value in row.opposing_evidence_ids]}
                     for row in disputes],
        "evidence_gaps": [{"id": public_ref("GAP", row.id),
                           "claim_id": public_ref("CLM", row.claim_id),
                           "critique_id": public_ref("CRT", row.critique_id),
                           "audit_id": public_ref("AUD", row.audit_result_id),
                           "reason_code": row.reason_code,
                           "rationale_summary": row.rationale_summary,
                           "status": row.status,
                           "evidence": [evidence_ref(session, UUID(value))
                                        for value in row.cited_evidence_ids]}
                          for row in gaps],
        "stop_evaluations": [{"id": public_ref("STP", row.id),
                              "round_no": row.round_no, "decision": row.decision,
                              "reason_code": row.reason_code} for row in stops],
        "human_reviews": [{"id": public_ref("HREV", row.id),
                            "status": row.status, "reason_code": row.reason_code,
                            "interrupted_stage": row.interrupted_stage,
                            "resume_stage": row.resume_stage,
                            "resolution_note": row.resolution_note,
                            "resolved_by": row.resolved_by} for row in reviews],
    }
