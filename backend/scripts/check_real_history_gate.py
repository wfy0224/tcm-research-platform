"""Exercise the historical Claim gate with real evidence, rolling back every write.

No model calls, fabricated source metadata, or persistent test Claims are used.
"""

import json
import os
from copy import deepcopy
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import sessionmaker

os.environ["TCM_DATABASE_URL"] = make_url(os.environ["TCM_DATABASE_URL"]).set(
    database="tcm_vib62_workspace_test").render_as_string(hide_password=False)

from tcm_platform import research_service
from tcm_platform.db import SessionLocal, engine
from tcm_platform.knowledge_service import trace_evidence
from tcm_platform.models import (
    AgentRun,
    Claim,
    EvidenceRevision,
    KnowledgeVersionItem,
    ResearchTask,
    TaskEvidenceRef,
)

TASK = "RT-01a0f788-b1a8-7cee-9e52-7cee5d555a58"
with SessionLocal() as session:
    task = session.scalar(select(ResearchTask).where(ResearchTask.public_id == TASK))
    assert task is not None
    run = session.scalar(select(AgentRun).where(
        AgentRun.task_id == task.id, AgentRun.role == "HistoricalScholar", AgentRun.round_no == 1))
    refs = list(session.scalars(select(TaskEvidenceRef.evidence_revision_id).where(
        TaskEvidenceRef.task_id == task.id)))
    original_claim_count = session.scalar(select(func.count()).select_from(Claim).where(
        Claim.task_id == task.id))
    original_task_status, original_run_status = task.status, run.status
    unpooled_id = session.scalar(select(KnowledgeVersionItem.evidence_revision_id).where(
        KnowledgeVersionItem.knowledge_version_id == UUID(task.execution_context["knowledge_version_id"]),
        KnowledgeVersionItem.evidence_revision_id.is_not(None),
        KnowledgeVersionItem.evidence_revision_id.not_in(refs)).limit(1))
    assert unpooled_id is not None
    task_id, run_id = task.id, run.id
evidence = next(e for e in map(trace_evidence, refs) if "柯琴" in e["quote_text"])
assert not any(evidence.get(key) for key in (
    "source_author", "source_era", "source_school", "source_edition", "source_publication_year"))
payload = {"claims": [{
    "client_ref": "body-history", "claim_type": "LATER_INTERPRETATION",
    "assertion_text": "教材在大青龙汤相关方论中引述柯琴的解释。",
    "rationale_summary": "仅依据所引正文中的医家署名，不推断成书年代或流派。",
    "evidence_revision_ids": [evidence["evidence_revision_id"]],
}]}
rejected = []
original_factory = research_service.SessionLocal
try:
    with engine.connect() as connection, connection.begin() as transaction:
        factory = sessionmaker(connection, expire_on_commit=False,
                               join_transaction_mode="create_savepoint")
        research_service.SessionLocal = factory
        with factory.begin() as session:
            session.get(ResearchTask, task_id).status = "RESEARCHING"
            session.get(AgentRun, run_id).status = "PENDING"
        with connection.begin_nested() as candidate_transaction:
            claims = research_service.submit_first_round_output(run_id, payload)
            assert len(claims) == 1
            with factory() as session:
                assert session.get(Claim, claims[0]).audit_status == "PENDING"
            candidate_transaction.rollback()

        def reject(candidate, label):
            try:
                research_service.submit_first_round_output(run_id, candidate)
            except ValueError as exc:
                assert "outside visible" in str(exc), str(exc)
                rejected.append(label)
            else:
                raise AssertionError(f"accepted {label}")

        invalid = deepcopy(payload)
        invalid["claims"][0]["evidence_revision_ids"] = [str(uuid4())]
        reject(invalid, "unseen evidence")
        mixed = deepcopy(payload)
        mixed["claims"].append({**invalid["claims"][0], "client_ref": "invalid"})
        reject(mixed, "mixed valid and invalid Claims atomically")
        with factory.begin() as session:
            session.get(AgentRun, run_id).visible_evidence_ids = [str(e) for e in refs] + [str(unpooled_id)]
        invalid["claims"][0]["evidence_revision_ids"] = [str(unpooled_id)]
        reject(invalid, "outside task pool")
        with factory.begin() as session:
            session.get(AgentRun, run_id).visible_evidence_ids = []
        reject(payload, "outside role visibility")
        with factory.begin() as session:
            session.get(AgentRun, run_id).visible_evidence_ids = [str(e) for e in refs]
            frozen_context = deepcopy(session.get(ResearchTask, task_id).execution_context)
            session.get(ResearchTask, task_id).execution_context = {
                **frozen_context, "knowledge_version_id": str(uuid4())}
        reject(payload, "outside frozen version")
        with factory.begin() as session:
            session.get(ResearchTask, task_id).execution_context = frozen_context
            revision = session.get(EvidenceRevision, UUID(evidence["evidence_revision_id"]))
            original_status = revision.status
            revision.status = "DRAFT"
        reject(payload, "unreviewed evidence")
        with factory.begin() as session:
            session.get(EvidenceRevision, UUID(evidence["evidence_revision_id"])).status = original_status
        transaction.rollback()
finally:
    research_service.SessionLocal = original_factory
with SessionLocal() as session:
    assert session.scalar(select(func.count()).select_from(Claim).where(
        Claim.task_id == task_id)) == original_claim_count
    assert session.get(ResearchTask, task_id).status == original_task_status
    assert session.get(AgentRun, run_id).status == original_run_status
print(json.dumps({"task": TASK, "body_history_candidate_accepted": True,
                  "citation_rejections": rejected, "writes_rolled_back": True}))
