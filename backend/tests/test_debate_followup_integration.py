"""Follow-up and failure recovery checks using a separate clone of real user data."""

from copy import deepcopy
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from tcm_platform import debate_service
from tcm_platform.db import SessionLocal, engine
from tcm_platform.models import AgentRun, ResearchTask, TaskJob
from tcm_platform.research_api import _task_response
from tcm_platform.research_service import (
    create_research_task,
    start_research_task,
)
from tcm_platform.stop_service import WorkflowConfig


@pytest.fixture
def real_clone():
    assert engine.url.database == "tcm_debate_repair_6dca_test", "isolated real-data clone required"
    with SessionLocal() as session:
        task = session.scalar(select(ResearchTask).where(
            ResearchTask.public_id == "RT-01a0f7c4-ab9c-767d-ad0a-bd59b05bc940"))
        assert task is not None, "real test scenario must exist; skip is not a pass"
        return task.id


def test_next_critic_sees_frozen_replies_and_open_gaps(real_clone, monkeypatch):
    with engine.connect() as connection:
        transaction = connection.begin()
        factory = sessionmaker(bind=connection, expire_on_commit=False,
                               join_transaction_mode="create_savepoint")
        monkeypatch.setattr(debate_service, "SessionLocal", factory)
        with factory.begin() as session:
            task = session.get(ResearchTask, real_clone)
            task.status = "FIRST_ROUND_COMPLETE"
            task.execution_context = {**task.execution_context,
                                      "workflow_config": WorkflowConfig().model_dump()}
            previous = session.scalar(select(AgentRun).where(
                AgentRun.task_id == real_clone, AgentRun.role == "Rebuttal",
                AgentRun.round_no == 2))
            previous_output = deepcopy(previous.output)
            previous_id = previous.id
        run_id = debate_service.prepare_critic_round(real_clone)
        payload = debate_service.critic_visible_context(run_id)
        assert len(payload["debate_history"]) == 5
        assert len(payload["open_gaps"]) == 2
        assert {item["round_no"] for item in payload["debate_history"]} == {2}
        expected = {item["critique_id"]: item for item in previous_output["rebuttals"]}
        for item in payload["debate_history"]:
            assert item["response"] == expected[item["critique"]["critique_id"]]
        with factory.begin() as session:
            run = session.get(AgentRun, run_id)
            assert run.round_no == 3
            assert all(set(item["response"]["evidence_revision_ids"]) <=
                       set(run.visible_evidence_ids) for item in payload["debate_history"])
            # The prepared input is frozen; later records cannot rewrite this history.
            session.get(AgentRun, previous_id).output = {"rebuttals": []}
        assert debate_service.critic_visible_context(run_id) == payload
        transaction.rollback()


def test_exhausted_report_is_not_advertised_as_retryable(real_clone):
    with SessionLocal() as session:
        task = session.get(ResearchTask, real_clone)
        job = session.scalar(select(TaskJob).where(
            TaskJob.idempotency_key == f"research:{real_clone}:run:v1"))
        assert job.status == "FAILED" and job.attempts == 3
        response = _task_response(session, task)
        assert response.job_status == "FAILED"
        assert "retry" not in response.allowed_actions
        assert "recover_report" in response.allowed_actions
    with SessionLocal() as session:
        job = session.scalar(select(TaskJob).where(
            TaskJob.idempotency_key == f"research:{real_clone}:run:v1"))
        assert job.status == "FAILED" and job.attempts == 3


def test_new_task_freezes_followup_policy_without_modifying_original(real_clone):
    with SessionLocal() as session:
        original = session.get(ResearchTask, real_clone)
        frozen = deepcopy(original.execution_context)
        question = original.question
        sources = [UUID(value) for value in original.draft_scope["source_ids"]]
    new_id = create_research_task(question, source_ids=sources,
                                  actor_id="test-followup-policy", idempotency_key=str(uuid4()))
    start_research_task(new_id, model_version=frozen["generation_model"],
                        question_outbound_authorized=frozen["question_outbound_authorized"])
    with SessionLocal() as session:
        task = session.get(ResearchTask, new_id)
        assert task.status == "PLANNING"
        assert task.execution_context["workflow_version"] == "research-v3"
        assert task.execution_context["workflow_config"]["max_debate_rounds"] == 3
        assert task.execution_context["workflow_config"]["review_replies"] is True
        assert "debate_history" in task.execution_context["frozen_prompts"]["Critic"]
        assert session.get(ResearchTask, real_clone).execution_context == frozen
