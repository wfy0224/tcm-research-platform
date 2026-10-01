"""Replay the user's real stopping snapshot with today's default, without writes."""

import json
import os
from copy import deepcopy

from sqlalchemy import select
from sqlalchemy.engine.url import make_url

os.environ["TCM_DATABASE_URL"] = make_url(os.environ["TCM_DATABASE_URL"]).set(
    database="tcm_vib62_workspace_test").render_as_string(hide_password=False)

from tcm_platform.db import SessionLocal
from tcm_platform.models import ResearchTask, StopEvaluation
from tcm_platform.stop_service import WorkflowConfig, evaluate_snapshot

with SessionLocal() as session:
    task = session.scalar(select(ResearchTask).where(
        ResearchTask.public_id == "RT-01a0f7c4-ab9c-767d-ad0a-bd59b05bc940"))
    stop = session.scalar(select(StopEvaluation).where(
        StopEvaluation.task_id == task.id, StopEvaluation.round_no == 2))
    snapshot = deepcopy(stop.input_snapshot)
    assert stop.reason_code == "ROUND_LIMIT"
    assert len(snapshot["open_gap_ids"]) == 2
    assert snapshot["current_critique_count"] == 5
    frozen_config = deepcopy(task.execution_context["workflow_config"])

snapshot["workflow_config"] = WorkflowConfig().model_dump(mode="json")
decision, reason = evaluate_snapshot(snapshot)
print(json.dumps({"original_reason": stop.reason_code, "open_gaps": 2,
                  "default_config": snapshot["workflow_config"],
                  "decision": decision, "reason": reason}, ensure_ascii=False))
assert decision == "CONTINUE", "five replies with two open gaps must receive follow-up review"
assert frozen_config["max_debate_rounds"] == 1, "historical policy must remain intact"
