from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

from tcm_platform import cloud_models
from tcm_platform.db import SessionLocal, engine
from tcm_platform.models import ModelInvocation, ResearchTask, SourceDocument
from tcm_platform.outbound_policy import (
    POLICY_VERSION,
    authorize_outbound,
    require_outbound,
    set_source_outbound_policy,
)
from tcm_platform.research_runtime import recorded_complete


def test_source_grant_revocation_and_frozen_local_only(monkeypatch):
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT outbound_authorized FROM source.source_document LIMIT 1"))
    except SQLAlchemyError:
        pytest.skip("VIB-58 migration is not available")

    source_id = uuid4()
    with SessionLocal.begin() as session:
        session.add(SourceDocument(
            id=source_id, public_id=f"SRC-{uuid4()}", source_type="CLASSIC",
            title="外发策略测试", language="zh", copyright_status="UNKNOWN",
            data_level="RESTRICTED", outbound_authorized=False, status="DRAFT",
        ))
    model = "siliconflow/BAAI/bge-m3"
    monkeypatch.setenv("TCM_OUTBOUND_MODE", "CLOUD_ALLOWED")
    with (pytest.raises(PermissionError, match="data level or authorization"),
          authorize_outbound("embed", model, [source_id], frozen_mode="CLOUD_ALLOWED",
                             frozen_policy_version=POLICY_VERSION)):
        pass


    set_source_outbound_policy(source_id, data_level="PUBLIC",
                               authorized=True, reason="reviewed public test text",
                               actor_id="test-curator")
    with (pytest.raises(PermissionError, match="disabled"),
          authorize_outbound("embed", model, [source_id], frozen_mode="LOCAL_ONLY",
                             frozen_policy_version=POLICY_VERSION)):
        pass
    with (pytest.raises(PermissionError, match="disabled"),
          authorize_outbound("embed", model, [source_id], frozen_mode="CLOUD_ALLOWED",
                             frozen_policy_version=None)):
        pass
    with authorize_outbound("embed", model, [source_id],
                            frozen_mode="CLOUD_ALLOWED",
                            frozen_policy_version=POLICY_VERSION) as permit:
        assert permit.source_ids == (source_id,)
        assert require_outbound("embed", model) == permit
        with pytest.raises(PermissionError, match="matching"):
            require_outbound("rerank", model)

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self, limit):
                return b'{"data":[]}'

        class Opener:
            def open(self, request, timeout):
                return Response()

        monkeypatch.setattr(cloud_models, "build_opener", lambda handler: Opener())
        assert cloud_models._post_json(
            "https://api.siliconflow.cn/v1/embeddings", "unit-test-key",
            {"model": "BAAI/bge-m3", "input": ["public test text"]},
        ) == {"data": []}
        with SessionLocal() as session:
            row = session.scalar(select(ModelInvocation).where(
                ModelInvocation.policy_hash == permit.policy_hash,
                ModelInvocation.purpose == "embed",
            ).order_by(ModelInvocation.created_at.desc()))
            assert row is not None and row.status == "COMPLETED"
            assert row.task_id is None and row.policy_version == POLICY_VERSION
            assert row.request_hash and row.output_hash
    with pytest.raises(PermissionError, match="matching"):
        require_outbound("embed", model)

    set_source_outbound_policy(source_id, data_level="RESTRICTED",
                               authorized=False, reason="revoke", actor_id="test-curator")
    with (pytest.raises(PermissionError, match="data level or authorization"),
          authorize_outbound("embed", model, [source_id], frozen_mode="CLOUD_ALLOWED",
                             frozen_policy_version=POLICY_VERSION)):
        pass


def test_remote_research_uses_frozen_prompt_and_redacted_invocation(monkeypatch):
    source_id, task_id = uuid4(), uuid4()
    model_version = "siliconflow/Qwen/Qwen3-8B"
    with SessionLocal.begin() as session:
        session.add(SourceDocument(
            id=source_id, public_id=f"SRC-{uuid4()}", source_type="CLASSIC",
            title="公开文本", language="zh", copyright_status="PUBLIC_DOMAIN",
            data_level="PUBLIC", outbound_authorized=True, status="DRAFT",
        ))
        session.add(ResearchTask(
            id=task_id, public_id=f"RT-{uuid4()}", question="公开研究问题",
            status="PLANNING", control_state="ACTIVE", draft_scope={"source_ids": []},
            execution_context={
                "generation_model": model_version, "outbound_mode": "CLOUD_ALLOWED",
                "outbound_policy_version": POLICY_VERSION,
                "outbound_source_ids": [str(source_id)],
                "question_outbound_authorized": True,
                "frozen_prompts": {"Planner": "frozen prompt"},
            },
        ))
    monkeypatch.setenv("TCM_OUTBOUND_MODE", "CLOUD_ALLOWED")

    class RemoteModel:
        is_remote = True
        model_version = "siliconflow/Qwen/Qwen3-8B"
        api_key = "unit-test-key"
        endpoint = "https://api.siliconflow.cn/v1/chat/completions"
        received = None

        def complete_json_with_metadata(self, system_prompt, input_payload):
            self.received = system_prompt
            return {"subquestions": []}, {"total_tokens": 4}

    model = RemoteModel()
    assert recorded_complete(task_id, None, "Planner", model, "changed prompt",
                             {"question": "公开研究问题"}) == {"subquestions": []}
    assert model.received == "frozen prompt"
    with SessionLocal() as session:
        invocation = session.scalar(select(ModelInvocation).where(
            ModelInvocation.task_id == task_id,
            ModelInvocation.purpose == "Planner",
        ))
        assert invocation is not None and invocation.status == "COMPLETED"
        assert invocation.policy_hash and invocation.policy_version == POLICY_VERSION
        assert invocation.request_hash and "公开研究问题" not in str(invocation.__dict__)
