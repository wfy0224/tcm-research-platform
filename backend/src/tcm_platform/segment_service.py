"""Persist source structure and align immutable revisions in a leased job."""

import hashlib
import json
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select

from tcm_platform.audit import append_event
from tcm_platform.config import settings
from tcm_platform.db import SessionLocal
from tcm_platform.enums import JobStatus
from tcm_platform.ids import new_id
from tcm_platform.jobs import acquire_job, complete_job, fail_job
from tcm_platform.models import (
    Artifact,
    ImportJob,
    PipelineStepExecution,
    SegmentAlignment,
    SourceDocument,
    SourceRevision,
    TaskJob,
    TextSegment,
    TextSegmentRevision,
    utc_now,
)
from tcm_platform.parsing import ParsedDocument, ParsedPage
from tcm_platform.segmentation import (
    RESOLVER_VERSION,
    PreviousSegment,
    align_revisions,
    detect_split_merge,
    resolve_structure,
)
from tcm_platform.storage import ContentAddressedStore

MAX_PARSED_BYTES = 100 * 1024 * 1024
MAX_SEGMENTS = 200_000


@dataclass(frozen=True)
class SegmentResult:
    import_job_id: UUID
    source_revision_id: UUID
    segment_count: int
    status: str


def _load_parsed(store: ContentAddressedStore, digest: str) -> ParsedDocument:
    with store.path_for(digest).open("rb") as stream:
        payload = stream.read(MAX_PARSED_BYTES + 1)
    if len(payload) > MAX_PARSED_BYTES or hashlib.sha256(payload).hexdigest() != digest:
        raise ValueError("parsed artifact exceeds limit or checksum differs")
    data = json.loads(payload)
    pages = [ParsedPage(page_no=int(p["page_no"]), text=str(p["text"]),
                        paragraph_starts=p.get("paragraph_starts")) for p in data["pages"]]
    if not pages or any(page.page_no < 1 for page in pages):
        raise ValueError("parsed artifact has no valid pages")
    return ParsedDocument(
        file_format=data["file_format"],
        pages=pages,
        encoding=data.get("encoding"),
        warnings=data.get("warnings", []),
        parser_version=data["parser_version"],
    )


def process_next_segment(
    *, worker_id: str = "local-segmenter", store: ContentAddressedStore | None = None
) -> SegmentResult | None:
    store = store or ContentAddressedStore(settings.data_root)
    with SessionLocal.begin() as session:
        job = acquire_job(
            session, worker_id=worker_id, lease_seconds=900, job_types=("source.segment",)
        )
        if job is None:
            return None
        import_job_id = UUID(job.payload["import_job_id"])
        import_job = session.get(ImportJob, import_job_id)
        if import_job is None or import_job.parsed_artifact_id is None:
            raise RuntimeError("segment job has no parsed import")
        revision = session.get(SourceRevision, import_job.source_revision_id)
        source = session.get(SourceDocument, revision.source_id)
        artifact = session.get(Artifact, import_job.parsed_artifact_id)
        if source is None or artifact is None:
            raise RuntimeError("segment job references missing source or artifact")
        job_id, generation, attempt = job.id, job.execution_generation, job.attempts
        revision_id, source_id, revision_no = revision.id, source.id, revision.revision_no
        title, digest = source.title, artifact.blob_sha256
        import_job.status = "SEGMENTING"
        import_job.updated_at = utc_now()
        session.add(
            PipelineStepExecution(
                import_job_id=import_job_id,
                step="SEGMENT",
                attempt=attempt,
                status="RUNNING",
                input_hash=digest,
                tool_version=RESOLVER_VERSION,
                parameters={},
            )
        )

    try:
        drafts = resolve_structure(_load_parsed(store, digest), title=title)
        if len(drafts) > MAX_SEGMENTS:
            raise ValueError("parsed document exceeds segment limit")
        with SessionLocal.begin() as session:
            import_job = session.scalar(
                select(ImportJob).where(ImportJob.id == import_job_id).with_for_update()
            )
            prior = session.scalar(
                select(SourceRevision).where(
                    SourceRevision.source_id == source_id,
                    SourceRevision.revision_no == revision_no - 1,
                )
            )
            previous: list[PreviousSegment] = []
            if prior is not None:
                prior_import = session.scalar(
                    select(ImportJob).where(ImportJob.source_revision_id == prior.id)
                )
                if prior_import is None or prior_import.status != "SEGMENTED":
                    raise RuntimeError("previous source revision is not segmented yet")
                rows = session.scalars(
                    select(TextSegmentRevision)
                    .where(TextSegmentRevision.source_revision_id == prior.id)
                    .order_by(TextSegmentRevision.sequence_no)
                )
                previous = [
                    PreviousSegment(
                        revision_id=row.id,
                        segment_id=row.segment_id,
                        segment_type=row.segment_type,
                        original_text=row.original_text,
                        normalized_text=row.normalized_text,
                        checksum=row.checksum,
                        structural_locator=row.structural_locator,
                    )
                    for row in rows
                ]
            decisions, deleted = align_revisions(drafts, previous)
            structural_changes, reflow_new, reflow_old = detect_split_merge(
                drafts, decisions, deleted
            )
            identities: list[UUID] = []
            for draft, decision in zip(drafts, decisions, strict=True):
                if decision.old is None:
                    segment_id = new_id()
                    session.add(
                        TextSegment(
                            id=segment_id,
                            public_id=f"SEG-{segment_id}",
                            source_id=source_id,
                            segment_type=draft.segment_type,
                        )
                    )
                else:
                    segment_id = decision.old.segment_id
                identities.append(segment_id)
            session.flush()
            revisions: list[TextSegmentRevision] = []
            for draft, segment_id in zip(drafts, identities, strict=True):
                row = TextSegmentRevision(
                    id=new_id(),
                    segment_id=segment_id,
                    source_revision_id=revision_id,
                    parent_segment_id=(
                        identities[draft.parent_index]
                        if draft.parent_index is not None else None
                    ),
                    segment_type=draft.segment_type,
                    sequence_no=draft.sequence_no,
                    original_text=draft.original_text,
                    normalized_text=draft.normalized_text,
                    context_before=draft.context_before,
                    context_after=draft.context_after,
                    page_no=draft.page_no,
                    chapter_no=draft.chapter_no,
                    paragraph_no=draft.paragraph_no,
                    structural_locator=draft.structural_locator,
                    checksum=draft.checksum,
                )
                session.add(row)
                revisions.append(row)
            session.flush()
            if prior is not None:
                for index, (row, decision) in enumerate(zip(revisions, decisions, strict=True)):
                    if index in reflow_new:
                        continue
                    session.add(
                        SegmentAlignment(
                            from_source_revision_id=prior.id,
                            to_source_revision_id=revision_id,
                            old_revision_id=(decision.old.revision_id if decision.old else None),
                            new_revision_id=row.id,
                            status=decision.status,
                        )
                    )
                for old in deleted:
                    if old.revision_id in reflow_old:
                        continue
                    session.add(
                        SegmentAlignment(
                            from_source_revision_id=prior.id,
                            to_source_revision_id=revision_id,
                            old_revision_id=old.revision_id,
                            new_revision_id=None,
                            status="DELETED",
                        )
                    )
                for change in structural_changes:
                    session.add(
                        SegmentAlignment(
                            from_source_revision_id=prior.id,
                            to_source_revision_id=revision_id,
                            old_revision_id=change.old_revision_id,
                            new_revision_id=revisions[change.new_index].id,
                            status=change.status,
                        )
                    )
            complete_job(
                session,
                job_id=job_id,
                worker_id=worker_id,
                generation=generation,
                result={"status": "SEGMENTED", "segment_count": len(drafts)},
            )
            step = session.scalar(
                select(PipelineStepExecution).where(
                    PipelineStepExecution.import_job_id == import_job_id,
                    PipelineStepExecution.step == "SEGMENT",
                    PipelineStepExecution.attempt == attempt,
                )
            )
            step.status = "COMPLETED"
            step.finished_at = utc_now()
            import_job.status = "SEGMENTED"
            import_job.error_code = None
            import_job.error_message = None
            import_job.updated_at = utc_now()
            append_event(
                session,
                event_type="source.segmented",
                actor_id=worker_id,
                aggregate_id=revision_id,
                payload={"segment_count": len(drafts), "resolver_version": RESOLVER_VERSION},
            )
        return SegmentResult(import_job_id, revision_id, len(drafts), "SEGMENTED")
    except Exception as exc:  # noqa: BLE001 - persist unexpected worker errors for retry.
        with SessionLocal.begin() as session:
            fail_job(
                session,
                job_id=job_id,
                worker_id=worker_id,
                generation=generation,
                error=str(exc),
            )
            import_job = session.get(ImportJob, import_job_id)
            current_job = session.get(TaskJob, job_id)
            import_job.status = (
                "RETRY_WAIT" if current_job.status == JobStatus.RETRY_WAIT.value else "FAILED"
            )
            import_job.error_code = "SEGMENT_FAILED"
            import_job.error_message = str(exc)[:4000]
            import_job.updated_at = utc_now()
            step = session.scalar(
                select(PipelineStepExecution).where(
                    PipelineStepExecution.import_job_id == import_job_id,
                    PipelineStepExecution.step == "SEGMENT",
                    PipelineStepExecution.attempt == attempt,
                )
            )
            step.status = "FAILED"
            step.error_code = "SEGMENT_FAILED"
            step.error_message = str(exc)[:4000]
            step.finished_at = utc_now()
            status = import_job.status
        return SegmentResult(import_job_id, revision_id, 0, status)
