"""Deterministic stopping from frozen policy and persisted research facts."""

import hashlib
import json
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from tcm_platform.audit import append_event
from tcm_platform.db import SessionLocal
from tcm_platform.enums import JobStatus
from tcm_platform.ids import new_id
from tcm_platform.models import (
    AgentRun,
    AuditResult,
    Claim,
    Critique,
    Dispute,
    EvidenceGap,
    HumanReviewRequest,
    ResearchTask,
    StopEvaluation,
    TaskJob,
    utc_now,
)


class WorkflowConfig(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    min_debate_rounds: int = Field(default=1, ge=1, le=5)
    max_debate_rounds: int = Field(default=1, ge=1, le=5)
    min_supported_claims: int = Field(default=1, ge=0, le=100)
    max_open_disputes: int = Field(default=0, ge=0, le=100)
    max_open_gaps: int = Field(default=0, ge=0, le=100)
    mandatory_human_review: bool = False
    review_on_open_dispute: bool = False

    @model_validator(mode="after")
    def valid_rounds(self) -> "WorkflowConfig":
        if self.min_debate_rounds > self.max_debate_rounds:
            raise ValueError("minimum debate rounds exceed maximum")
        return self


def evaluate_snapshot(snapshot: dict) -> tuple[str, str]:
    """Pure decision function; the stored snapshot is enough to replay it."""
    policy = WorkflowConfig.model_validate(snapshot["workflow_config"])
    if snapshot["first_round_claim_count"] == 0:
        return "STOP", "NO_FIRST_ROUND_CLAIMS"
    if snapshot["round_no"] >= 2:
        reason = ("MANDATORY_REVIEW" if policy.mandatory_human_review else
                  "OPEN_DISPUTE_REVIEW" if policy.review_on_open_dispute
                  and snapshot["open_dispute_ids"] else None)
        if reason and reason not in snapshot["resolved_review_reasons"]:
            return "WAITING_HUMAN", reason
        if snapshot["current_critique_count"] == 0:
            return "STOP", "NO_CRITIQUES"
        debate_rounds = snapshot["round_no"] - 1
        if debate_rounds < policy.min_debate_rounds:
            return "CONTINUE", "MIN_ROUNDS"
        if (snapshot["new_claim_count"] == 0
                and snapshot["supported_claim_count"] >= policy.min_supported_claims
                and len(snapshot["open_dispute_ids"]) <= policy.max_open_disputes
                and len(snapshot["open_gap_ids"]) <= policy.max_open_gaps):
            return "STOP", "STABLE_EVIDENCE"
        if debate_rounds >= policy.max_debate_rounds:
            return "STOP", "ROUND_LIMIT"
        return "CONTINUE", "MORE_EVIDENCE_NEEDED"
    return "CONTINUE", "FIRST_DEBATE_REQUIRED"


def evaluate_stop(session: Session, task_id: UUID, round_no: int) -> StopEvaluation:
    task = session.get(ResearchTask, task_id)
    if task is None or task.execution_context is None:
        raise ValueError("research task has no frozen workflow")
    claims = list(session.scalars(select(Claim).where(Claim.task_id == task_id)
                                  .order_by(Claim.id)))
    audits = list(session.scalars(select(AuditResult).where(AuditResult.task_id == task_id)
                                  .order_by(AuditResult.claim_id, AuditResult.sequence_no)))
    latest = {audit.claim_id: audit for audit in audits}
    disputes = list(session.scalars(select(Dispute).where(
        Dispute.task_id == task_id, Dispute.status == "OPEN").order_by(Dispute.id)))
    gaps = list(session.scalars(select(EvidenceGap).where(
        EvidenceGap.task_id == task_id, EvidenceGap.status == "OPEN").order_by(EvidenceGap.id)))
    critic = session.scalar(select(AgentRun).where(
        AgentRun.task_id == task_id, AgentRun.role == "Critic", AgentRun.round_no == round_no))
    critique_count = 0 if critic is None else len(list(session.scalars(select(Critique.id).where(
        Critique.agent_run_id == critic.id))))
    rebuttal = session.scalar(select(AgentRun).where(
        AgentRun.task_id == task_id, AgentRun.role == "Rebuttal", AgentRun.round_no == round_no))
    new_claims = [claim for claim in claims if rebuttal and claim.agent_run_id == rebuttal.id]
    reviews = list(session.scalars(select(HumanReviewRequest).where(
        HumanReviewRequest.task_id == task_id,
        HumanReviewRequest.status == "RESOLVED")))
    snapshot = {
        "workflow_config": task.execution_context.get("workflow_config", WorkflowConfig().model_dump()),
        "round_no": round_no,
        "first_round_claim_count": sum(claim.parent_claim_id is None for claim in claims),
        "current_critique_count": critique_count,
        "new_claim_count": len(new_claims),
        "supported_claim_count": sum(audit.verdict == "SUPPORTED" for audit in latest.values()),
        "audit_results": [{"id": str(audit.id), "claim_id": str(audit.claim_id),
                           "verdict": audit.verdict} for audit in sorted(latest.values(), key=lambda a: str(a.id))],
        "open_dispute_ids": [str(item.id) for item in disputes],
        "open_gap_ids": [str(item.id) for item in gaps],
        "resolved_review_reasons": sorted({item.reason_code for item in reviews
                                           if item.source_key.startswith(f"{round_no}:")}),
    }
    decision, reason = evaluate_snapshot(snapshot)
    digest = hashlib.sha256(json.dumps(snapshot, sort_keys=True, ensure_ascii=False)
                            .encode("utf-8")).hexdigest()
    existing = session.scalar(select(StopEvaluation).where(
        StopEvaluation.task_id == task_id, StopEvaluation.round_no == round_no,
        StopEvaluation.input_hash == digest))
    if existing is not None:
        return existing
    evaluation = StopEvaluation(id=new_id(), task_id=task_id, round_no=round_no,
                                input_hash=digest, input_snapshot=snapshot,
                                decision=decision, reason_code=reason)
    session.add(evaluation)
    session.flush()
    append_event(session, event_type="research_task.stop_evaluated", actor_id="stop-evaluator",
                 aggregate_id=task_id, payload={"round_no": round_no,
                                                "decision": decision, "reason_code": reason,
                                                "input_hash": digest})
    return evaluation


def resolve_human_review(request_id: UUID, *, reviewer_id: str, note: str) -> UUID:
    if not reviewer_id.strip() or not note.strip():
        raise ValueError("reviewer and resolution note are required")
    with SessionLocal.begin() as session:
        review = session.scalar(select(HumanReviewRequest).where(
            HumanReviewRequest.id == request_id).with_for_update())
        if review is None or review.status != "PENDING":
            raise ValueError("human review request is not pending")
        task = session.scalar(select(ResearchTask).where(
            ResearchTask.id == review.task_id).with_for_update())
        job = session.scalar(select(TaskJob).where(
            TaskJob.idempotency_key == f"research:{review.task_id}:run:v1"
        ).with_for_update())
        if (task is None or task.status != "WAITING_HUMAN" or job is None
                or job.status != JobStatus.COMPLETED.value or job.lease_owner is not None
                or task.resume_stage != review.resume_stage):
            raise ValueError("research task is not ready to resume")
        review.status = "RESOLVED"
        review.resolution_note = note.strip()
        review.resolved_by = reviewer_id.strip()
        review.resolved_at = utc_now()
        task.status = review.resume_stage
        task.interrupted_stage = None
        task.resume_stage = None
        task.waiting_reason_code = None
        job.status = JobStatus.PENDING.value
        job.attempts = 0
        job.available_at = utc_now()
        job.updated_at = utc_now()
        append_event(session, event_type="research_task.human_review_resolved",
                     actor_id=reviewer_id, aggregate_id=task.id,
                     payload={"request_id": str(request_id), "resume_stage": task.status})
        return task.id
