import hashlib
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

from tcm_platform.db import SessionLocal, engine
from tcm_platform.models import SegmentAlignment, TextSegmentRevision
from tcm_platform.segment_service import process_next_segment
from tcm_platform.source_import import SourceMetadata, import_file, process_next_import
from tcm_platform.storage import ContentAddressedStore


@pytest.fixture(autouse=True)
def migrated_postgres():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1 FROM source.text_segment_revision LIMIT 1"))
    except SQLAlchemyError:
        pytest.skip("E3 migration is not available")


def _finish_segment(import_job_id, store):
    for _ in range(100):
        result = process_next_segment(store=store)
        if result is None:
            break
        if result.import_job_id == import_job_id:
            assert result.status == "SEGMENTED"
            return result
    pytest.fail("target segment job did not complete")


def test_structure_and_cross_revision_identity(tmp_path):
    store = ContentAddressedStore(tmp_path / "store")
    first_path = tmp_path / "first.txt"
    second_path = tmp_path / "second.txt"
    first_path.write_text("卷一\n第一章\n第一条：太阳之为病。\n第二条：脉浮。", encoding="utf-8")
    second_path.write_text("卷一\n第一章\n第一条：太阳之为病。\n第二条：脉浮而紧。", encoding="utf-8")
    metadata = SourceMetadata(source_type="CLASSIC", title="测试古籍")
    first = import_file(
        first_path, metadata, request_key=f"segment:first:{uuid4()}", store=store
    )
    assert process_next_import(store=store).status == "PARSED"
    assert _finish_segment(first.import_job_id, store).segment_count >= 7

    second = import_file(
        second_path, metadata, source_id=first.source_id,
        request_key=f"segment:second:{uuid4()}", store=store,
    )
    assert process_next_import(store=store).status == "PARSED"
    _finish_segment(second.import_job_id, store)

    with SessionLocal() as session:
        first_rows = list(session.scalars(select(TextSegmentRevision).where(
            TextSegmentRevision.source_revision_id == first.source_revision_id
        )))
        second_rows = list(session.scalars(select(TextSegmentRevision).where(
            TextSegmentRevision.source_revision_id == second.source_revision_id
        )))
        alignments = list(session.scalars(select(SegmentAlignment).where(
            SegmentAlignment.to_source_revision_id == second.source_revision_id
        )))
        assert {row.segment_type for row in first_rows} >= {
            "BOOK", "VOLUME", "CHAPTER", "CLAUSE", "SENTENCE"
        }
        original = next(row for row in first_rows if row.original_text == "第一条：太阳之为病。")
        unchanged = next(row for row in second_rows if row.original_text == original.original_text)
        assert unchanged.segment_id == original.segment_id
        assert unchanged.parent_segment_id is not None
        assert unchanged.checksum == hashlib.sha256(original.original_text.encode()).hexdigest()
        edited_old = next(row for row in first_rows if row.original_text == "第二条：脉浮。")
        edited_new = next(row for row in second_rows if row.original_text == "第二条：脉浮而紧。")
        assert edited_new.segment_id == edited_old.segment_id
        assert {row.status for row in alignments} >= {"UNCHANGED", "MODIFIED"}
