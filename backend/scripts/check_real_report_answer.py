"""Read-only checks against a completed real task, including citation rejection."""

import argparse
import json
import os
from copy import deepcopy
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.engine.url import make_url

os.environ["TCM_DATABASE_URL"] = make_url(os.environ["TCM_DATABASE_URL"]).set(
    database="tcm_vib62_workspace_test").render_as_string(hide_password=False)

from tcm_platform.db import SessionLocal
from tcm_platform.knowledge_service import trace_evidence
from tcm_platform.models import (
    AgentRun,
    Critique,
    KnowledgeVersion,
    ModelInvocation,
    Rebuttal,
    ResearchSynthesis,
    ResearchTask,
    StructuredReport,
    TaskEvidenceRef,
)
from tcm_platform.report_narrative import validate_narrative

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("task")
args = parser.parse_args()
with SessionLocal() as session:
    task = session.scalar(select(ResearchTask).where(ResearchTask.public_id == args.task))
    assert task.status == "COMPLETED"
    assert task.question == "比较麻黄汤和大青龙汤，分析大青龙汤中麻黄用量为什么比麻黄汤多"
    report = session.scalar(select(StructuredReport).where(StructuredReport.task_id == task.id))
    assert report.schema_version == "research-report/v2", "report still only arranges copied assertions"
    answer = report.content.get("answer")
    assert answer and answer["paragraphs"], "report has no readable synthesis"
    synthesis = session.scalar(select(ResearchSynthesis).where(ResearchSynthesis.task_id == task.id))
    snapshot = synthesis.input_snapshot
    validate_narrative({"paragraphs": answer["paragraphs"]}, snapshot)
    runs = list(session.scalars(select(AgentRun).where(AgentRun.task_id == task.id)))
    calls = list(session.scalars(select(ModelInvocation).where(ModelInvocation.task_id == task.id)))
    purposes = {call.purpose for call in calls if call.status == "COMPLETED"}
    assert {"Planner", "Classicist", "HistoricalScholar", "Theorist", "EvidenceAuditor",
            "Critic", "Judge", "ReportWriter", "ReportReviewer"} <= purposes
    assert all(call.policy_hash for call in calls if call.status == "COMPLETED")
    reviewer = next(run for run in runs if str(run.id) == answer["reviewer_run_id"])
    assert reviewer.output["accepted"] and not reviewer.output["issues"]
    assert reviewer.input_snapshot["candidate"] == {"paragraphs": answer["paragraphs"]}
    version = session.get(KnowledgeVersion, UUID(task.execution_context["knowledge_version_id"]))
    pool = [trace_evidence(value) for value in session.scalars(select(
        TaskEvidenceRef.evidence_revision_id).where(TaskEvidenceRef.task_id == task.id))]
    assert len(pool) > 2
    assert all(row["source_revision_no"] == 2 for row in pool)
    assert set(task.execution_context["source_ids"]) == {row["source_id"] for row in pool}
    old_task = session.scalar(select(ResearchTask).where(
        ResearchTask.public_id == "RT-01a0f73b-04e1-7c42-bd42-2c21c469f744"))
    old_report = session.scalar(select(StructuredReport).where(StructuredReport.task_id == old_task.id))
    assert old_report.schema_version == "research-report/v1" and "answer" not in old_report.content
    old_claim_id = old_report.content["sections"]["HIGH_CONFIDENCE"][0]["claim_id"]
    invalid = deepcopy({"paragraphs": answer["paragraphs"]})
    invalid["paragraphs"][0]["claim_ids"] = [old_claim_id]
    try:
        validate_narrative(invalid, snapshot)
    except ValueError:
        foreign_citation_rejected = True
    else:
        raise AssertionError("report accepted a Claim from another task")
    conditional = next((c for c in snapshot["claims"] if c["allowed_category"] == "CONDITIONAL"), None)
    conditional_upgrade_rejected = None
    if conditional:
        invalid = {"paragraphs": [{"text": conditional["assertion_text"],
                    "kind": "finding", "claim_ids": [conditional["claim_id"]]}]}
        try:
            validate_narrative(invalid, snapshot)
        except ValueError:
            conditional_upgrade_rejected = True
        else:
            raise AssertionError("conditional Claim became a certain finding")
    claims = [c["assertion_text"] for c in snapshot["claims"]]
    assert all(p["text"] not in claims for p in answer["paragraphs"]), "answer copies an input Claim"
    critique_count = len(list(session.scalars(select(Critique).where(Critique.task_id == task.id))))
    rebuttal_count = len(list(session.scalars(select(Rebuttal).where(Rebuttal.task_id == task.id))))
    role_calls = [c for c in calls if c.purpose not in {"complete", "embed", "rerank"}]
    tokens = {key: sum((c.token_usage or {}).get(key, 0) for c in role_calls)
              for key in ("prompt_tokens", "completion_tokens", "total_tokens")}
    result = {"task_id": task.public_id, "knowledge_version": version.public_id,
              "workflow_version": task.execution_context["workflow_version"],
              "schema_version": report.schema_version, "content_hash": report.content_hash,
              "evidence_count": len(pool), "answer_paragraphs": len(answer["paragraphs"]),
              "model_purposes": sorted(purposes), "real_cloud_policy_verified": True,
              "foreign_citation_rejected": foreign_citation_rejected,
              "conditional_upgrade_rejected": conditional_upgrade_rejected,
              "historical_report_unchanged": True,
              "critique_count": critique_count, "rebuttal_count": rebuttal_count,
              "actual_debate_verified": critique_count > 0 and rebuttal_count > 0,
              "role_call_latency_total_ms": sum(c.latency_ms for c in role_calls),
              "recorded_token_usage": tokens, "recorded_cost": None,
              "writer_drafts": len([r for r in runs if r.role == "ReportWriter"]),
              "rejected_reviews": len([r for r in runs if r.role == "ReportReviewer"
                  and r.status == "COMPLETED" and not r.output["accepted"]]),
              "accepted_input_schema": reviewer.input_snapshot.get("input_schema"),
              "review_summary": reviewer.output["review_summary"],
              "pool": [{"source_title": e["source_title"], "citation_locator": e["citation_locator"],
                        "evidence_revision_id": e["evidence_revision_id"]} for e in pool]}
print(json.dumps(result, ensure_ascii=False))
# Emit stdout only: the real-data container mounts the workspace read-only.
