import json
import zipfile
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

from tcm_platform.audit import verify_chain
from tcm_platform.db import SessionLocal, engine
from tcm_platform.models import (
    Artifact,
    FileAsset,
    ImportJob,
    PipelineStepExecution,
    SourceRevision,
)
from tcm_platform.source_import import SourceMetadata, import_file, process_next_import
from tcm_platform.storage import ContentAddressedStore


@pytest.fixture(autouse=True)
def migrated_postgres():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1 FROM source.import_job LIMIT 1"))
    except SQLAlchemyError:
        pytest.skip("E2 migration is not available")


def test_source_import_parse_and_replay(tmp_path):
    store = ContentAddressedStore(tmp_path / "store")
    source_file = tmp_path / "sample.txt"
    source_file.write_text("第一条：太阳之为病。\n第二条：脉浮。", encoding="utf-8")
    metadata = SourceMetadata(source_type="CLASSIC", title="测试古籍", edition="测试版")
    request_key = f"source-import:{uuid4()}"

    registered = import_file(source_file, metadata, request_key=request_key, store=store)
    replay = import_file(source_file, metadata, request_key=request_key, store=store)
    assert registered == replay
    assert registered.status == "REGISTERED"
    assert registered.task_job_id is not None

    finished = process_next_import(store=store)
    assert finished is not None and finished.import_job_id == registered.import_job_id
    assert finished.status == "PARSED"

    with SessionLocal() as session:
        import_job = session.get(ImportJob, registered.import_job_id)
        revision = session.get(SourceRevision, registered.source_revision_id)
        original = session.scalar(
            select(FileAsset).where(FileAsset.source_revision_id == revision.id)
        )
        parsed_artifact = session.get(Artifact, import_job.parsed_artifact_id)
        parsed = json.loads(store.path_for(parsed_artifact.blob_sha256).read_bytes())
        steps = list(
            session.scalars(
                select(PipelineStepExecution)
                .where(PipelineStepExecution.import_job_id == import_job.id)
                .order_by(PipelineStepExecution.started_at)
            )
        )
        assert original.role == "ORIGINAL"
        assert parsed["text"] == "第一条：太阳之为病。\n第二条：脉浮。"
        assert {step.step: step.status for step in steps} == {
            "REGISTER": "COMPLETED",
            "VALIDATE_FILE": "COMPLETED",
            "PARSE": "COMPLETED",
        }
        assert verify_chain(session)


def test_invalid_pdf_is_retained_with_failure_reason(tmp_path):
    store = ContentAddressedStore(tmp_path / "store")
    bad_file = tmp_path / "bad.pdf"
    bad_file.write_bytes(b"not a PDF")
    result = import_file(
        bad_file,
        SourceMetadata(source_type="OTHER", title="待修复资料"),
        request_key=f"invalid-pdf:{uuid4()}",
        store=store,
    )
    assert result.status == "FAILED"
    assert result.task_job_id is None
    with SessionLocal() as session:
        import_job = session.get(ImportJob, result.import_job_id)
        revision = session.get(SourceRevision, result.source_revision_id)
        assert import_job.error_code == "INVALID_FILE"
        assert store.path_for(revision.file_sha256).read_bytes() == b"not a PDF"


def test_docx_import_reaches_parsed_artifact(tmp_path):
    store = ContentAddressedStore(tmp_path / "store")
    docx = tmp_path / "classic.docx"
    xml = (
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body><w:p><w:r><w:t>伤寒论原文</w:t></w:r></w:p></w:body></w:document>"
    )
    with zipfile.ZipFile(docx, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", xml)
    registered = import_file(
        docx,
        SourceMetadata(source_type="CLASSIC", title="测试 DOCX"),
        request_key=f"docx:{uuid4()}",
        store=store,
    )
    finished = process_next_import(store=store)
    assert finished.import_job_id == registered.import_job_id
    assert finished.status == "PARSED"
    with SessionLocal() as session:
        import_job = session.get(ImportJob, registered.import_job_id)
        artifact = session.get(Artifact, import_job.parsed_artifact_id)
        assert json.loads(store.path_for(artifact.blob_sha256).read_bytes())["text"] == "伤寒论原文"


def test_scanned_pdf_waits_for_ocr_without_losing_original(tmp_path):
    from pypdf import PdfWriter

    store = ContentAddressedStore(tmp_path / "store")
    pdf = tmp_path / "scan.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    with pdf.open("wb") as output:
        writer.write(output)
    registered = import_file(
        pdf,
        SourceMetadata(source_type="OTHER", title="扫描件"),
        request_key=f"scan:{uuid4()}",
        store=store,
    )
    finished = process_next_import(store=store)
    assert finished.import_job_id == registered.import_job_id
    assert finished.status == "OCR_REQUIRED"
    with SessionLocal() as session:
        import_job = session.get(ImportJob, registered.import_job_id)
        revision = session.get(SourceRevision, registered.source_revision_id)
        assert import_job.error_code == "OCR_REQUIRED"
        assert import_job.parsed_artifact_id is None
        assert store.path_for(revision.file_sha256).read_bytes() == pdf.read_bytes()


def test_new_edition_creates_revision_without_changing_old_one(tmp_path):
    store = ContentAddressedStore(tmp_path / "store")
    first_file = tmp_path / "edition-one.txt"
    second_file = tmp_path / "edition-two.txt"
    first_file.write_text("初版原文", encoding="utf-8")
    second_file.write_text("修订版原文", encoding="utf-8")
    first = import_file(
        first_file,
        SourceMetadata(source_type="CLASSIC", title="同一著作", edition="初版"),
        request_key=f"edition-one:{uuid4()}",
        store=store,
    )
    assert process_next_import(store=store).status == "PARSED"
    second = import_file(
        second_file,
        SourceMetadata(source_type="CLASSIC", title="同一著作", edition="修订版"),
        source_id=first.source_id,
        request_key=f"edition-two:{uuid4()}",
        store=store,
    )
    assert process_next_import(store=store).status == "PARSED"
    with SessionLocal() as session:
        old_revision = session.get(SourceRevision, first.source_revision_id)
        new_revision = session.get(SourceRevision, second.source_revision_id)
        assert old_revision.source_id == new_revision.source_id == first.source_id
        assert (old_revision.revision_no, new_revision.revision_no) == (1, 2)
        assert old_revision.metadata_snapshot["edition"] == "初版"
        assert new_revision.metadata_snapshot["edition"] == "修订版"
        assert store.path_for(old_revision.file_sha256).read_bytes() == first_file.read_bytes()
        assert store.path_for(new_revision.file_sha256).read_bytes() == second_file.read_bytes()

