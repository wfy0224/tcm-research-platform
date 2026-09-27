"""Development CLI for the source import and segmentation pipeline."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

from tcm_platform.db import SessionLocal
from tcm_platform.ids import new_id
from tcm_platform.knowledge_service import (
    IngredientSpec,
    create_concept,
    create_entity_mention,
    create_evidence,
    create_formula,
    create_herb,
    create_relation,
    trace_evidence,
    trace_knowledge,
)
from tcm_platform.models import (
    ImportJob,
    PipelineStepExecution,
    SourceRevision,
    TextSegmentRevision,
)
from tcm_platform.segment_service import process_next_segment
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
    commands.add_parser("segment-next", help="process one queued source.segment job")
    show = commands.add_parser("show-import", help="show import and pipeline status")
    show.add_argument("import_job_id", type=UUID)
    segments = commands.add_parser("show-segments", help="list segment locators for a source revision")
    segments.add_argument("source_revision_id", type=UUID)
    evidence = commands.add_parser("create-evidence", help="cite a contiguous segment revision range")
    evidence.add_argument("segment_revision_ids", nargs="+", type=UUID)
    evidence.add_argument("--strength", required=True)
    evidence.add_argument("--evidence-id", type=UUID, help="append a new revision to existing evidence")
    trace = commands.add_parser("trace-evidence", help="show exact source provenance")
    trace.add_argument("evidence_revision_id", type=UUID)
    knowledge_trace = commands.add_parser("trace-knowledge", help="trace a draft object to source")
    knowledge_trace.add_argument("kind", choices=["concept", "relation", "herb", "formula_revision"])
    knowledge_trace.add_argument("object_id", type=UUID)
    mention = commands.add_parser("create-mention", help="record a source-anchored entity mention")
    mention.add_argument("segment_revision_id", type=UUID)
    mention.add_argument("start_offset", type=int)
    mention.add_argument("end_offset", type=int)
    mention.add_argument("--type", required=True)
    concept = commands.add_parser("create-concept", help="create a draft concept")
    concept.add_argument("name")
    concept.add_argument("--type", required=True)
    concept.add_argument("--evidence", required=True, type=UUID)
    concept.add_argument("--term", action="append", default=[])
    concept.add_argument("--mention", action="append", default=[], type=UUID)
    concept.add_argument("--era")
    concept.add_argument("--school")
    relation = commands.add_parser("create-relation", help="create a draft concept relation")
    relation.add_argument("subject_concept_id", type=UUID)
    relation.add_argument("object_concept_id", type=UUID)
    relation.add_argument("--type", required=True)
    relation.add_argument("--assertion", required=True)
    relation.add_argument("--evidence", required=True, type=UUID)
    herb = commands.add_parser("create-herb", help="create a draft herb")
    herb.add_argument("name")
    herb.add_argument("--evidence", required=True, type=UUID)
    herb.add_argument("--term", action="append", default=[])
    formula = commands.add_parser("create-formula", help="create a draft formula revision")
    formula.add_argument("name")
    formula.add_argument("--evidence", required=True, type=UUID)
    formula.add_argument("--ingredient", action="append", required=True)
    formula.add_argument("--formula-id", type=UUID)
    formula.add_argument("--era")
    formula.add_argument("--school")
    formula.add_argument("--indications")
    formula.add_argument("--effects")

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
    elif args.command == "segment-next":
        result = process_next_segment()
        print(json.dumps(asdict(result) if result else None, default=str, ensure_ascii=False))
    elif args.command == "create-evidence":
        revision_id = create_evidence(
            args.segment_revision_ids, strength=args.strength, evidence_id=args.evidence_id
        )
        print(json.dumps({"evidence_revision_id": str(revision_id)}))
    elif args.command == "trace-evidence":
        print(json.dumps(trace_evidence(args.evidence_revision_id), ensure_ascii=False))
    elif args.command == "trace-knowledge":
        print(json.dumps(trace_knowledge(args.kind, args.object_id), ensure_ascii=False))
    elif args.command == "create-mention":
        mention_id = create_entity_mention(
            args.segment_revision_id, start_offset=args.start_offset,
            end_offset=args.end_offset, entity_type=args.type,
        )
        print(json.dumps({"mention_id": str(mention_id)}))
    elif args.command == "create-concept":
        concept_id = create_concept(
            args.name, concept_type=args.type, evidence_revision_id=args.evidence,
            terms=tuple(args.term), mention_ids=tuple(args.mention),
            era=args.era, school=args.school,
        )
        print(json.dumps({"concept_id": str(concept_id)}))
    elif args.command == "create-relation":
        relation_id = create_relation(
            args.subject_concept_id, args.object_concept_id,
            relation_type=args.type, assertion_text=args.assertion,
            evidence_revision_id=args.evidence,
        )
        print(json.dumps({"relation_id": str(relation_id)}))
    elif args.command == "create-herb":
        herb_id = create_herb(
            args.name, evidence_revision_id=args.evidence, terms=tuple(args.term)
        )
        print(json.dumps({"herb_id": str(herb_id)}))
    elif args.command == "create-formula":
        revision_id = create_formula(
            args.name, evidence_revision_id=args.evidence,
            ingredients=tuple(IngredientSpec(original_name=name) for name in args.ingredient),
            formula_id=args.formula_id, era=args.era, school=args.school,
            indications=args.indications, effects=args.effects,
        )
        print(json.dumps({"formula_revision_id": str(revision_id)}))
    elif args.command == "show-segments":
        with SessionLocal() as session:
            rows = session.scalars(
                select(TextSegmentRevision)
                .where(TextSegmentRevision.source_revision_id == args.source_revision_id)
                .order_by(TextSegmentRevision.sequence_no)
            )
            print(json.dumps([
                {
                    "segment_id": str(row.segment_id),
                    "segment_revision_id": str(row.id),
                    "type": row.segment_type,
                    "locator": row.structural_locator,
                    "text": row.original_text,
                    "checksum": row.checksum,
                }
                for row in rows
            ], ensure_ascii=False))
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

