"""Recover the real rejected report without any invented model response."""

from copy import deepcopy
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from tcm_platform import (
    judge_service,
    report_export,
    report_narrative,
    research_runtime,
    research_service,
    research_worker,
)
from tcm_platform.db import engine
from tcm_platform.models import AgentRun, EventLog, ResearchTask, StructuredReport, TaskJob
from tcm_platform.research_api import _task_response


def test_cached_rejected_drafts_save_a_report_and_allow_an_explicit_revision(monkeypatch):
    assert engine.url.database == "tcm_debate_repair_6dca_test"
    with engine.connect() as connection:
        transaction = connection.begin()
        factory = sessionmaker(bind=connection, expire_on_commit=False,
                               join_transaction_mode="create_savepoint")
        for module in (judge_service, report_export, report_narrative,
                       research_runtime, research_service, research_worker):
            monkeypatch.setattr(module, "SessionLocal", factory)
        with factory() as session:
            task = session.scalar(select(ResearchTask).where(
                ResearchTask.public_id == "RT-01a0f7c4-ab9c-767d-ad0a-bd59b05bc940"))
            assert task.status == "REPORTING"
            task_id = task.id
            context = deepcopy(task.execution_context)
            run_count = len(list(session.scalars(select(AgentRun.id).where(
                AgentRun.task_id == task_id))))

        class NoModelCalls:
            model_version = context["generation_model"]

            def complete_json(self, *args):
                raise AssertionError("cached report recovery must not call a model")

        class NoEmbeddingCalls:
            model_version = context["embedding_model"]

            def embed(self, *args):
                raise AssertionError("report recovery must not retrieve")

        class NoRerankingCalls:
            model_version = context["rerank_model"]

            def rerank(self, *args):
                raise AssertionError("report recovery must not retrieve")

        research_service.retry_research_task(task_id, actor_id="test-real-recovery",
                                             idempotency_key=str(uuid4()))
        job_id = research_worker.run_next_research_job(
            worker_id="test-cached-report", task_id=task_id, model=NoModelCalls(),
            embedder=NoEmbeddingCalls(), reranker=NoRerankingCalls())
        with factory() as session:
            task = session.get(ResearchTask, task_id)
            job = session.get(TaskJob, job_id)
            assert (task.status, job.status) == ("REPORT_REVIEW_REQUIRED", "COMPLETED"), job.last_error
            response = _task_response(session, task)
            assert response.report_available and "export" in response.allowed_actions
            assert "revise_report" in response.allowed_actions
            report = session.scalar(select(StructuredReport).where(
                StructuredReport.task_id == task_id))
            saved_id, saved_hash, saved_content = report.id, report.content_hash, deepcopy(report.content)
            assert report.revision_no == 1 and report.content["review_status"] == "NEEDS_REVISION"
            assert report.content["counts"]["HIGH_CONFIDENCE"] == 7
            assert report.content["counts"]["UNRESOLVED"] == 2
            assert report.content["answer"]["review_issues"]
            assert len(list(session.scalars(select(AgentRun.id).where(
                AgentRun.task_id == task_id)))) == run_count
            markdown = report_export.render_markdown(report.content, report_export._process_snapshot(
                session, task_id)).decode()
            assert "草稿未通过复核" in markdown and "待修订" in markdown
            assert "未解决问题：2 条" in markdown

        key = str(uuid4())
        for _ in range(2):
            research_service.revise_research_report(task_id, actor_id="test-real-recovery",
                                                    idempotency_key=key)
        with factory() as session:
            requests = list(session.scalars(select(EventLog).where(
                EventLog.aggregate_id == str(task_id),
                EventLog.event_type == "research_task.report_revision_requested")))
            assert len(requests) == 1 and requests[0].payload["start_attempt"] == 3
            assert session.get(ResearchTask, task_id).status == "REPORTING"
            assert session.get(TaskJob, job_id).status == "PENDING"
            assert _task_response(session, session.get(ResearchTask, task_id)).report_available

        # The explicit request prepares a fresh draft rather than replaying the exhausted batch.
        with pytest.raises(AssertionError, match="must not call a model"):
            report_narrative.execute_report_narrative(task_id, model=NoModelCalls())
        with factory() as session:
            fresh = session.scalar(select(AgentRun).where(
                AgentRun.task_id == task_id, AgentRun.role == "ReportWriter", AgentRun.round_no == 3))
            assert fresh is not None and fresh.status == "PENDING"
            assert fresh.input_snapshot["feedback"] == saved_content["answer"]["review_issues"]
            original = session.get(StructuredReport, saved_id)
            assert original.content_hash == saved_hash and original.content == saved_content
            assert session.get(ResearchTask, task_id).execution_context == context
        transaction.rollback()
