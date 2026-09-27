"""Development CLI for the E2 import pipeline."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

from tcm_platform.db import SessionLocal
from tcm_platform.ids import new_id
from tcm_platform.models import ImportJob, PipelineStepExecution, SourceRevision
from tcm_platform.source_import import SourceMetadata, import_file, process_next_import


def main() -> None:
    parser = argparse.ArgumentParser(prog="tcm-platform")
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("import-source", help="register and queue one local source file")
    create.add_argument("file", type=Path)
    create.add_argument("--title", required=True)
    create.add_argument("--source-type", default="OTHER")
    create.add_argument("--author")
    create.add_argument("--era")
    create.add_argument("--school")
    create.add_argument("--edition")
    create.add_argument("--publisher")
    create.add_argument("--publication-year", type=int)
    create.add_argument("--language", default="zh")
    create.add_argument("--copyright-status", default="UNKNOWN")
    create.add_argument("--request-key")
    create.add_argument("--source-id", type=UUID, help="append an immutable revision to an existing source")

    commands.add_parser("parse-next", help="process one queued source.parse job")
    show = commands.add_parser("show-import", help="show import and pipeline status")
    show.add_argument("import_job_id", type=UUID)

    args = parser.parse_args()
    if args.command == "import-source":
        metadata = SourceMetadata(
            source_type=args.source_type,
            title=args.title,
            author=args.author,
            era=args.era,
            school=args.school,
            edition=args.edition,
            publisher=args.publisher,
            publication_year=args.publication_year,
            language=args.language,
            copyright_status=args.copyright_status,
        )
        result = import_file(
            args.file,
            metadata,
            request_key=args.request_key or str(new_id()),
            source_id=args.source_id,
        )
        print(json.dumps(asdict(result), default=str, ensure_ascii=False))
    elif args.command == "parse-next":
        result = process_next_import()
        print(json.dumps(asdict(result) if result else None, default=str, ensure_ascii=False))
    else:
        with SessionLocal() as session:
            import_job = session.get(ImportJob, args.import_job_id)
            if import_job is None:
                parser.error("import job not found")
            revision = session.get(SourceRevision, import_job.source_revision_id)
            steps = session.scalars(
                select(PipelineStepExecution)
                .where(PipelineStepExecution.import_job_id == import_job.id)
                .order_by(PipelineStepExecution.started_at, PipelineStepExecution.attempt)
            )
            print(
                json.dumps(
                    {
                        "import_job_id": str(import_job.id),
                        "source_revision_id": str(revision.id),
                        "file_sha256": revision.file_sha256,
                        "status": import_job.status,
                        "error_code": import_job.error_code,
                        "error_message": import_job.error_message,
                        "parsed_artifact_id": (
                            str(import_job.parsed_artifact_id)
                            if import_job.parsed_artifact_id else None
                        ),
                        "steps": [
                            {
                                "step": step.step,
                                "attempt": step.attempt,
                                "status": step.status,
                                "error_code": step.error_code,
                            }
                            for step in steps
                        ],
                    },
                    ensure_ascii=False,
                )
            )


if __name__ == "__main__":
    main()

