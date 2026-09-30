"""VIB-45 real text sample and incomplete-PDF publication boundaries."""

import hashlib
import json
from pathlib import Path
from uuid import uuid4

import pytest
from pdf_samples import pdf_with_pages
from sqlalchemy import select, text

from tcm_platform import segment_service, source_import
from tcm_platform.db import SessionLocal
from tcm_platform.jobs import acquire_job
from tcm_platform.knowledge_publish import create_knowledge_version, review_object
from tcm_platform.knowledge_service import create_evidence, trace_evidence
from tcm_platform.models import (
    EvidenceRevision,
    ImportJob,
    KnowledgeRuntimeState,
    KnowledgeVersionItem,
    PipelineStepExecution,
    SourceRevision,
    TaskJob,
    TextSegmentRevision,
)
from tcm_platform.segment_service import process_next_segment
from tcm_platform.source_import import SourceMetadata, import_file, process_next_import
from tcm_platform.storage import ContentAddressedStore

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


@pytest.fixture(autouse=True)
def isolated_database():
    with SessionLocal() as session:
        database = session.scalar(text("SELECT current_database()"))
        assert database.startswith("tcm_") and database.endswith("_test"), database
        session.execute(text("SELECT 1 FROM governance.knowledge_version LIMIT 1"))


def _process_target(imported, store, monkeypatch, *, segment=False):
    module = segment_service if segment else source_import
    job_type = "source.segment" if segment else "source.parse"
    process = process_next_segment if segment else process_next_import
    # Keep the real queue lease/commit path while excluding other tests' jobs.
    with monkeypatch.context() as patch:
        patch.setattr(module, "acquire_job", lambda session, **kwargs: acquire_job(
            session, **kwargs, idempotency_key=f"{job_type}:{imported.import_job_id}",
        ))
        return process(store=store)


def _segment_text(path, store, metadata, monkeypatch):
    imported = import_file(path, metadata, request_key=f"vib45:{uuid4()}", store=store)
    parsed = _process_target(imported, store, monkeypatch)
    assert parsed is not None and parsed.import_job_id == imported.import_job_id
    assert parsed.status == "PARSED"
    segmented = _process_target(imported, store, monkeypatch, segment=True)
    assert segmented is not None and segmented.import_job_id == imported.import_job_id
    assert segmented.status == "SEGMENTED"
    with SessionLocal() as session:
        segments = list(session.scalars(select(TextSegmentRevision).where(
            TextSegmentRevision.source_revision_id == imported.source_revision_id,
            TextSegmentRevision.segment_type == "PARAGRAPH",
        ).order_by(TextSegmentRevision.sequence_no)))
    return imported, segments


def test_pinned_initial_corpus_preserves_all_quotes_and_remains_draft(tmp_path, monkeypatch):
    manifest = json.loads((FIXTURES / "initial_corpus.json").read_text(encoding="utf-8"))
    candidate = manifest["sources"][0]
    original = (FIXTURES / candidate["file"]).read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(original).hexdigest() == candidate["canonical_sha256"]
    paragraphs = [value.strip() for value in original.decode("utf-8").split("\n\n") if value.strip()]
    assert len(paragraphs) == candidate["expected_paragraphs"] == 29
    path = tmp_path / candidate["file"]
    path.write_bytes(original)
    store = ContentAddressedStore(tmp_path / "store")
    imported, segments = _segment_text(
        path, store, SourceMetadata.model_validate(candidate["source_metadata"]), monkeypatch,
    )
    assert [segment.original_text for segment in segments] == paragraphs
    assert len({json.dumps(segment.structural_locator, sort_keys=True) for segment in segments}) == 29
    assert all(segment.page_no == 1 for segment in segments)
    evidence_ids = [create_evidence([segment.id], strength="DIRECT") for segment in segments]
    for evidence_id, paragraph in zip(evidence_ids, paragraphs, strict=True):
        trace = trace_evidence(evidence_id)
        assert trace["quote_text"] == paragraph
    baseline = tmp_path / "synthetic.txt"
    baseline.write_text("合成快照基线。", encoding="utf-8")
    _, baseline_segments = _segment_text(
        baseline, store, SourceMetadata(source_type="OTHER", title="合成快照基线"), monkeypatch,
    )
    baseline_evidence = create_evidence([baseline_segments[0].id], strength="DIRECT")
    review_object("evidence_revision", baseline_evidence, reviewer_id="test-curator",
                  decision="APPROVE", note="Synthetic test only, not corpus expert approval")
    version_id = create_knowledge_version()
    with SessionLocal() as session:
        assert session.get(SourceRevision, imported.source_revision_id).file_sha256 == (
            candidate["canonical_sha256"]
        )
        assert {session.get(EvidenceRevision, evidence_id).status for evidence_id in evidence_ids} == {
            "DRAFT",
        }
        assert session.scalar(select(KnowledgeVersionItem.id).where(
            KnowledgeVersionItem.evidence_revision_id.in_(evidence_ids),
        ).limit(1)) is None
        assert session.scalar(select(KnowledgeVersionItem.id).where(
            KnowledgeVersionItem.knowledge_version_id == version_id,
            KnowledgeVersionItem.evidence_revision_id == baseline_evidence,
        )) is not None


@pytest.mark.parametrize("pages", [(None,), ("Text cover", None), (None, "Text body")])
def test_incomplete_pdf_cannot_enter_knowledge_snapshot(tmp_path, pages, monkeypatch):
    store = ContentAddressedStore(tmp_path / "store")
    baseline = tmp_path / "reviewed.txt"
    baseline.write_text("合成审核测试文本。", encoding="utf-8")
    _, baseline_segments = _segment_text(
        baseline, store, SourceMetadata(source_type="OTHER", title="VIB-45 合成基线"), monkeypatch,
    )
    baseline_evidence = create_evidence([baseline_segments[0].id], strength="DIRECT")
    review_object("evidence_revision", baseline_evidence, reviewer_id="test-curator",
                  decision="APPROVE", note="Synthetic test only, not corpus expert approval")
    with SessionLocal() as session:
        runtime = session.get(KnowledgeRuntimeState, 1)
        active_before = (runtime.active_knowledge_version_id, runtime.active_index_build_id)
    path = tmp_path / "incomplete.pdf"
    path.write_bytes(pdf_with_pages(*pages))
    imported = import_file(
        path, SourceMetadata(source_type="OTHER", title="VIB-45 无文字页边界"),
        request_key=f"vib45-pdf:{uuid4()}", store=store,
    )
    finished = _process_target(imported, store, monkeypatch)
    assert finished is not None and finished.import_job_id == imported.import_job_id
    assert finished.status == "OCR_REQUIRED"
    assert _process_target(imported, store, monkeypatch, segment=True) is None
    version_id = create_knowledge_version()
    with SessionLocal() as session:
        job = session.get(ImportJob, imported.import_job_id)
        revision = session.get(SourceRevision, imported.source_revision_id)
        assert job.parsed_artifact_id is None and job.error_code == "OCR_REQUIRED"
        assert store.path_for(revision.file_sha256).read_bytes() == path.read_bytes()
        parse_step = session.scalar(select(PipelineStepExecution).where(
            PipelineStepExecution.import_job_id == job.id,
            PipelineStepExecution.step == "PARSE",
        ))
        assert parse_step.status == "BLOCKED" and parse_step.output_artifact_id is None
        assert session.scalar(select(TaskJob.id).where(
            TaskJob.job_type == "source.segment",
            TaskJob.payload["import_job_id"].astext == str(job.id),
        ).limit(1)) is None
        assert session.scalar(select(TextSegmentRevision.id).where(
            TextSegmentRevision.source_revision_id == revision.id,
        ).limit(1)) is None
        assert session.scalar(select(EvidenceRevision.id).where(
            EvidenceRevision.source_revision_id == revision.id,
        ).limit(1)) is None
        evidence_ids = list(session.scalars(select(KnowledgeVersionItem.evidence_revision_id).where(
            KnowledgeVersionItem.knowledge_version_id == version_id,
            KnowledgeVersionItem.evidence_revision_id.is_not(None),
        )))
        assert baseline_evidence in evidence_ids
        assert all(session.get(EvidenceRevision, item).source_revision_id != revision.id
                   for item in evidence_ids)
        assert all(session.get(EvidenceRevision, item).status == "REVIEWED" for item in evidence_ids)
        runtime = session.get(KnowledgeRuntimeState, 1)
        assert (runtime.active_knowledge_version_id, runtime.active_index_build_id) == active_before
