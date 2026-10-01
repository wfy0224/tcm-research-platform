"""Read-only verification of the retained real customer demonstration.

Runs in the Linux test runtime. No model calls, approvals, migrations or writes.
"""

import hashlib
import io
import json
import os
import zipfile
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree

from sqlalchemy import func, select
from sqlalchemy.engine.url import make_url

DEMO_DB = "tcm_vib62_workspace_test"
TASK = "RT-01a0f2f0-f311-7572-9203-2ddd0aaa0edd"
inherited = make_url(os.environ["TCM_DATABASE_URL"])
if not inherited.database.startswith("tcm_") or not inherited.database.endswith("_test"):
    raise RuntimeError("refusing non-test database credentials")
os.environ["TCM_DATABASE_URL"] = inherited.set(database=DEMO_DB).render_as_string(hide_password=False)

from tcm_platform.audit import verify_chain  # noqa: E402
from tcm_platform.db import SessionLocal  # noqa: E402
from tcm_platform.models import (  # noqa: E402
    Artifact,
    AuditResult,
    Claim,
    EmbeddingRecord,
    IndexBuild,
    ModelInvocation,
    ReportExport,
    ResearchTask,
    StructuredReport,
    TaskEvidenceRef,
    TaskJob,
)
from tcm_platform.storage import ContentAddressedStore  # noqa: E402

with SessionLocal() as session:
    task = session.scalar(select(ResearchTask).where(ResearchTask.public_id == TASK))
    assert task is not None and task.status == "COMPLETED"
    context = task.execution_context
    assert context["generation_model"] == "deepseek/deepseek-flash"
    assert context["retrieval_strategy"] == "local-fts-exact-v1"
    build = session.get(IndexBuild, context["index_build_id"])
    assert build.status == "READY" and build.fts_status == "READY"
    assert build.vector_status == "NOT_APPLICABLE"
    assert session.scalar(select(func.count()).select_from(EmbeddingRecord)) == 0
    calls = list(session.scalars(select(ModelInvocation).where(ModelInvocation.task_id == task.id)))
    assert calls and all(call.status == "COMPLETED" for call in calls)
    assert all(call.model_version == "deepseek/deepseek-flash" for call in calls)
    report = session.scalar(select(StructuredReport).where(StructuredReport.task_id == task.id))
    assert report is not None
    exports = list(session.scalars(select(ReportExport).where(ReportExport.task_id == task.id)))
    assert {item.file_format for item in exports} == {"markdown", "docx"}
    files = []
    store = ContentAddressedStore(Path(f"/tmp/{DEMO_DB}_store"))
    for item in exports:
        assert item.completed_at is not None and session.get(TaskJob, item.job_id).status == "COMPLETED"
        artifact = session.get(Artifact, item.artifact_id)
        data = store.path_for(artifact.blob_sha256).read_bytes()
        assert hashlib.sha256(data).hexdigest() == artifact.blob_sha256
        if item.file_format == "markdown":
            rendered = data.decode("utf-8")
        else:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                xml = ElementTree.fromstring(archive.read("word/document.xml"))
                rendered = "\n".join(node.text or "" for node in xml.iter()
                                     if node.tag.endswith("}t"))
        assert "太陽之為病，脈浮，頭項強痛而惡寒。" in rendered
        reference = session.scalar(select(TaskEvidenceRef).where(TaskEvidenceRef.task_id == task.id))
        assert reference is not None and str(reference.evidence_revision_id) in rendered
        files.append({"format": item.file_format, "sha256": artifact.blob_sha256,
                      "bytes": len(data), "quote_and_reference_present": True})
    assert verify_chain(session)
    result = {
        "database": DEMO_DB, "task_id": TASK, "status": task.status,
        "model_doubles": False, "generation_model": context["generation_model"],
        "retrieval_strategy": context["retrieval_strategy"], "embedding_records": 0,
        "real_calls": len(calls), "call_statuses": dict(Counter(call.status for call in calls)),
        "call_purposes": dict(Counter(call.purpose for call in calls)),
        "transport_retries": sum(call.transport_retry_count or 0 for call in calls),
        "format_retries": sum((call.token_usage or {}).get("format_retry_count", 0) for call in calls),
        "tokens": {key: sum((call.token_usage or {}).get(key, 0) for call in calls)
                   for key in ("prompt_tokens", "completion_tokens", "total_tokens")},
        "claims": session.scalar(select(func.count()).select_from(Claim).where(Claim.task_id == task.id)),
        "audits": session.scalar(select(func.count()).select_from(AuditResult).join(
            Claim, Claim.id == AuditResult.claim_id).where(Claim.task_id == task.id)),
        "evidence_pool": session.scalar(select(func.count()).select_from(TaskEvidenceRef).where(
            TaskEvidenceRef.task_id == task.id)),
        "report_hash": report.content_hash, "exports": files, "audit_chain_verified": True,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
