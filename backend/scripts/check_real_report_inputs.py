"""Verify compact narrative inputs against the real frozen synthesis, without writes."""

import json
import os

from sqlalchemy import select
from sqlalchemy.engine.url import make_url

os.environ["TCM_DATABASE_URL"] = make_url(os.environ["TCM_DATABASE_URL"]).set(
    database="tcm_vib62_workspace_test").render_as_string(hide_password=False)

from tcm_platform.db import SessionLocal
from tcm_platform.models import AgentRun, ResearchSynthesis, ResearchTask
from tcm_platform.report_narrative import reviewer_input, validate_narrative, writer_input

with SessionLocal() as session:
    task = session.scalar(select(ResearchTask).where(
        ResearchTask.public_id == "RT-01a0f788-b1a8-7cee-9e52-7cee5d555a58"))
    synthesis = session.scalar(select(ResearchSynthesis).where(ResearchSynthesis.task_id == task.id))
    legacy = session.scalar(select(AgentRun).where(
        AgentRun.task_id == task.id, AgentRun.role == "ReportReviewer", AgentRun.round_no == 2))
    snapshot = synthesis.input_snapshot
    candidate = legacy.input_snapshot["candidate"]
    old_input = legacy.input_snapshot
payload = writer_input(snapshot, legacy.output["issues"])
review = reviewer_input(payload, candidate)
assert "feedback" not in review
assert review["candidate"] == candidate
validate_narrative(candidate, snapshot)
original = {c["claim_id"]: c for c in snapshot["claims"]}
assert {c["claim_id"] for c in review["claims"]} == {
    key for p in candidate["paragraphs"] for key in p["claim_ids"]}
for claim in payload["claims"]:
    assert claim["assertion_text"] == original[claim["claim_id"]]["assertion_text"]
    assert claim["allowed_category"] == original[claim["claim_id"]]["allowed_category"]
    assert [(e["evidence_revision_id"], e["quote_text"]) for e in claim["evidence"]] == [
        (e["evidence_revision_id"], e["quote_text"]) for e in original[claim["claim_id"]]["evidence"]]
size = lambda data: len(json.dumps(data, ensure_ascii=False).encode())
assert size(review) < size(old_input)
print(json.dumps({"task": task.public_id, "old_review_bytes": size(old_input),
                  "focused_review_bytes": size(review), "old_feedback_excluded": True,
                  "exact_claims_and_quotes_preserved": True, "no_writes": True}))
