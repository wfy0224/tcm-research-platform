"""Development CLI for the source import and segmentation pipeline."""

import argparse
import getpass
import hashlib
import json
import time
from dataclasses import asdict
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

from tcm_platform.audit_service import mechanical_audit_claim, semantic_audit_claim
from tcm_platform.claim_normalization import normalize_task_claims
from tcm_platform.cloud_models import (
    cloud_clients_from_environment,
    research_model_for_version,
    research_model_from_environment,
)
from tcm_platform.config import settings
from tcm_platform.db import SessionLocal
from tcm_platform.debate_service import (
    audit_revised_claims,
    execute_critic,
    execute_rebuttal,
    prepare_critic_round,
    prepare_rebuttal_round,
    retrieve_evidence_requests,
)
from tcm_platform.ids import new_id
from tcm_platform.knowledge_publish import (
    activate_knowledge_version,
    compare_knowledge_versions,
    create_index_build,
    create_knowledge_version,
    open_quality_issue,
    resolve_quality_issue,
    review_object,
)
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
from tcm_platform.model_credentials import store_model_key
from tcm_platform.models import (
    AgentRun,
    Artifact,
    Claim,
    HumanReviewRequest,
    ImportJob,
    PipelineStepExecution,
    ReportExport,
    ResearchTask,
    SourceRevision,
    StructuredReport,
    TaskJob,
    TextSegmentRevision,
)
from tcm_platform.outbound_policy import set_source_outbound_policy
from tcm_platform.report_export import process_next_report_export, queue_report_export
from tcm_platform.research_runtime import execute_first_round, execute_planner
from tcm_platform.research_service import (
    cancel_research_task,
    create_research_task,
    prepare_first_round,
    request_research_pause,
    resume_research_task,
    retrieve_for_task,
    start_research_task,
)
from tcm_platform.research_worker import run_next_research_job
from tcm_platform.retrieval import build_retrieval_index, search_published
from tcm_platform.retrieval_benchmark import create_golden_query, run_benchmark
from tcm_platform.segment_service import process_next_segment
from tcm_platform.source_import import SourceMetadata, import_file, process_next_import
from tcm_platform.stop_service import WorkflowConfig, resolve_human_review
from tcm_platform.storage import ContentAddressedStore


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
    create.add_argument("--data-level", choices=["PUBLIC", "RESTRICTED", "SENSITIVE"],
                        default="RESTRICTED")
    create.add_argument("--authorize-outbound", action="store_true")
    create.add_argument("--outbound-reason")
    create.add_argument("--request-key")
    create.add_argument("--source-id", type=UUID, help="append an immutable revision to an existing source")
    policy = commands.add_parser("set-source-outbound-policy", help="audit a source outbound grant")
    policy.add_argument("source_id", type=UUID)
    policy.add_argument("--data-level", required=True,
                        choices=["PUBLIC", "RESTRICTED", "SENSITIVE"])
    policy.add_argument("--authorize", action="store_true")
    policy.add_argument("--reason", required=True)
    policy.add_argument("--actor", required=True)
    key_command = commands.add_parser("set-model-key", help="save a provider key in OS keychain")
    key_command.add_argument("provider", choices=["aliyun", "siliconflow", "deepseek"])

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
    issue = commands.add_parser("open-quality-issue", help="record a quality finding")
    issue.add_argument("kind", choices=[
        "source_revision", "text_segment_revision", "evidence_revision",
        "concept", "relation", "herb", "formula_revision", "index_build",
    ])
    issue.add_argument("object_id", type=UUID)
    issue.add_argument("--type", required=True)
    issue.add_argument("--severity", required=True, choices=["BLOCKER", "WARNING", "INFO"])
    issue.add_argument("--description", required=True)
    resolve_issue = commands.add_parser("resolve-quality-issue", help="resolve or waive a finding")
    resolve_issue.add_argument("issue_id", type=UUID)
    resolve_issue.add_argument("--reviewer", required=True)
    resolve_issue.add_argument("--note", required=True)
    resolve_issue.add_argument("--waive", action="store_true")
    review = commands.add_parser("review-knowledge", help="record a human review decision")
    review.add_argument("kind", choices=["evidence_revision", "concept", "relation", "herb", "formula_revision"])
    review.add_argument("object_id", type=UUID)
    review.add_argument("--reviewer", required=True)
    review.add_argument("--decision", required=True, choices=["APPROVE", "REJECT"])
    review.add_argument("--note", required=True)
    commands.add_parser("snapshot-knowledge", help="freeze reviewed objects into a version")
    index_build = commands.add_parser("create-index-build", help="request FTS and vector indexes")
    index_build.add_argument("knowledge_version_id", type=UUID)
    index_build.add_argument("--configuration", help="JSON retrieval configuration override")
    build_index = commands.add_parser("build-index", help="build FTS and cloud embedding vectors")
    build_index.add_argument("index_build_id", type=UUID)
    search = commands.add_parser("search-published", help="search active published Evidence")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=10)
    search.add_argument("--allow-query-outbound", action="store_true")
    golden = commands.add_parser("add-golden-query", help="add a labeled retrieval query")
    golden.add_argument("query")
    golden.add_argument("--gold", type=UUID, action="append", default=[])
    golden.add_argument("--counter", type=UUID, action="append", default=[])
    golden.add_argument("--optional", type=UUID, action="append", default=[])
    golden.add_argument("--hard-negative", type=UUID, action="append", default=[])
    golden.add_argument("--source-id", type=UUID, action="append", default=[])
    benchmark = commands.add_parser("run-retrieval-benchmark", help="score active index against golden queries")
    benchmark.add_argument("--k", type=int, default=10)
    benchmark.add_argument("--allow-query-outbound", action="store_true")
    research = commands.add_parser("create-research-task", help="create a draft scoped research task")
    research.add_argument("question")
    research.add_argument("--source-id", type=UUID, action="append", default=[])
    start = commands.add_parser("start-research-task", help="freeze knowledge, index and cloud model")
    start.add_argument("task_id", type=UUID)
    start.add_argument("--workflow-config", help="JSON stopping policy frozen with the task")
    start.add_argument("--allow-question-outbound", action="store_true")
    list_reviews = commands.add_parser("list-human-reviews", help="list research reviews")
    list_reviews.add_argument("task_id", type=UUID)
    resolve_review = commands.add_parser("resolve-human-review", help="resolve and requeue a research task")
    resolve_review.add_argument("request_id", type=UUID)
    resolve_review.add_argument("--reviewer", required=True)
    resolve_review.add_argument("--note", required=True)
    show_report = commands.add_parser("show-structured-report", help="show immutable research report")
    show_report.add_argument("task_id", type=UUID)
    queue_export = commands.add_parser("queue-report-export", help="queue derived report artifact")
    queue_export.add_argument("task_id", type=UUID)
    queue_export.add_argument("--format", required=True, choices=["markdown", "docx"])
    run_export = commands.add_parser("run-report-export-next", help="process one export job")
    run_export.add_argument("--export-id", type=UUID)
    run_export.add_argument("--worker-id", default="local-export-worker")
    show_export = commands.add_parser("show-report-export", help="show export job and artifact")
    show_export.add_argument("export_id", type=UUID)
    save_export = commands.add_parser("save-report-export", help="copy a completed export to a file")
    save_export.add_argument("export_id", type=UUID)
    save_export.add_argument("output", type=Path)
    plan = commands.add_parser("plan-research-task", help="run the cloud Planner")
    plan.add_argument("task_id", type=UUID)
    retrieve = commands.add_parser("retrieve-research-task", help="fill version-bound evidence pool")
    retrieve.add_argument("task_id", type=UUID)
    retrieve.add_argument("--limit", type=int, default=10)
    first = commands.add_parser("prepare-first-round", help="freeze independent Agent inputs")
    first.add_argument("task_id", type=UUID)
    run_first = commands.add_parser("run-first-round", help="run cloud Agents into guarded Claim pool")
    run_first.add_argument("task_id", type=UUID)
    next_research = commands.add_parser("run-research-next", help="process one queued research task")
    next_research.add_argument("--worker-id", default="local-research-worker")
    next_research.add_argument("--task-id", type=UUID)
    research_worker = commands.add_parser("run-research-worker", help="poll research task queue")
    research_worker.add_argument("--worker-id", default="local-research-worker")
    research_worker.add_argument("--poll-seconds", type=float, default=2)
    for command in ("pause-research-task", "resume-research-task", "cancel-research-task"):
        control = commands.add_parser(command, help=f"{command} at a safe worker boundary")
        control.add_argument("task_id", type=UUID)
    audit_claim = commands.add_parser("audit-claim-mechanical", help="verify one Claim citation chain")
    audit_claim.add_argument("claim_id", type=UUID)
    audit_semantic = commands.add_parser("audit-claim-semantic", help="judge support using frozen cloud model")
    audit_semantic.add_argument("claim_id", type=UUID)
    prepare_critic = commands.add_parser("prepare-critic", help="freeze the Critic input")
    prepare_critic.add_argument("task_id", type=UUID)
    run_critic = commands.add_parser("run-critic", help="create Claim-targeted critiques")
    run_critic.add_argument("agent_run_id", type=UUID)
    retrieve_requests = commands.add_parser("retrieve-evidence-requests", help="resolve Critic evidence requests")
    retrieve_requests.add_argument("task_id", type=UUID)
    prepare_rebuttal = commands.add_parser(
        "prepare-rebuttal", help="freeze Critiques and visible evidence"
    )
    prepare_rebuttal.add_argument("task_id", type=UUID)
    run_rebuttal = commands.add_parser(
        "run-rebuttal", help="answer Critiques and append Claim revisions"
    )
    run_rebuttal.add_argument("agent_run_id", type=UUID)
    audit_revisions = commands.add_parser(
        "audit-revised-claims", help="audit pending Claim revisions"
    )
    audit_revisions.add_argument("task_id", type=UUID)
    normalize = commands.add_parser(
        "normalize-claims", help="replay audited Claim normalization and dispute detection"
    )
    normalize.add_argument("task_id", type=UUID)
    activate = commands.add_parser("activate-knowledge", help="switch active version after index checks")
    activate.add_argument("knowledge_version_id", type=UUID)
    activate.add_argument("index_build_id", type=UUID)
    compare = commands.add_parser("compare-knowledge", help="compare immutable version memberships")
    compare.add_argument("left_id", type=UUID)
    compare.add_argument("right_id", type=UUID)

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
            data_level=args.data_level,
            outbound_authorized=args.authorize_outbound,
            outbound_reason=args.outbound_reason,
        )
        result = import_file(
            args.file,
            metadata,
            request_key=args.request_key or str(new_id()),
            source_id=args.source_id,
        )
        print(json.dumps(asdict(result), default=str, ensure_ascii=False))
    elif args.command == "set-source-outbound-policy":
        set_source_outbound_policy(args.source_id, data_level=args.data_level,
                                   authorized=args.authorize, reason=args.reason,
                                   actor_id=args.actor)
        print(json.dumps({"source_id": str(args.source_id), "authorized": args.authorize}))
    elif args.command == "set-model-key":
        value = getpass.getpass("Provider API key: ")
        if not value:
            raise ValueError("empty API key")
        store_model_key(args.provider, value)
        print(json.dumps({"provider": args.provider, "stored": True}))
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
    elif args.command == "open-quality-issue":
        issue_id = open_quality_issue(
            args.kind, args.object_id, issue_type=args.type,
            severity=args.severity, description=args.description,
        )
        print(json.dumps({"quality_issue_id": str(issue_id)}))
    elif args.command == "resolve-quality-issue":
        resolve_quality_issue(
            args.issue_id, reviewer_id=args.reviewer,
            note=args.note, waive=args.waive,
        )
        print(json.dumps({"status": "WAIVED" if args.waive else "RESOLVED"}))
    elif args.command == "review-knowledge":
        review_id = review_object(
            args.kind, args.object_id, reviewer_id=args.reviewer,
            decision=args.decision, note=args.note,
        )
        print(json.dumps({"human_review_id": str(review_id)}))
    elif args.command == "snapshot-knowledge":
        version_id = create_knowledge_version()
        print(json.dumps({"knowledge_version_id": str(version_id)}))
    elif args.command == "create-index-build":
        if args.configuration:
            configuration = json.loads(args.configuration)
        else:
            embedder, reranker = cloud_clients_from_environment()
            configuration = {
                "strategy": "hybrid-rrf-v1",
                "embedding_model": embedder.model_version,
                "rerank_model": reranker.model_version,
                "embedding_endpoint": embedder.endpoint,
                "rerank_endpoint": reranker.endpoint,
            }
        build_id = create_index_build(
            args.knowledge_version_id, configuration=configuration
        )
        print(json.dumps({"index_build_id": str(build_id)}))
    elif args.command == "build-index":
        embedder, _ = cloud_clients_from_environment()
        count = build_retrieval_index(args.index_build_id, embedder=embedder)
        print(json.dumps({"status": "READY", "chunk_count": count}))
    elif args.command == "search-published":
        embedder, reranker = cloud_clients_from_environment()
        print(json.dumps(search_published(
            args.query, embedder=embedder, reranker=reranker, limit=args.limit,
            query_outbound_authorized=args.allow_query_outbound,
        ), ensure_ascii=False))
    elif args.command == "add-golden-query":
        pairs = [
            (evidence_id, category)
            for category, ids in (
                ("GOLD", args.gold), ("COUNTER", args.counter),
                ("OPTIONAL", args.optional), ("HARD_NEGATIVE", args.hard_negative),
            )
            for evidence_id in ids
        ]
        if len({evidence_id for evidence_id, _ in pairs}) != len(pairs):
            parser.error("one EvidenceRevision can have only one judgment per query")
        query_id = create_golden_query(
            args.query, dict(pairs), source_ids=args.source_id,
        )
        print(json.dumps({"golden_query_id": str(query_id)}))
    elif args.command == "run-retrieval-benchmark":
        embedder, reranker = cloud_clients_from_environment()
        print(json.dumps(run_benchmark(
            embedder=embedder, reranker=reranker, k=args.k,
            query_outbound_authorized=args.allow_query_outbound,
        ), ensure_ascii=False))
    elif args.command == "create-research-task":
        task_id = create_research_task(args.question, source_ids=args.source_id)
        print(json.dumps({"task_id": str(task_id)}))
    elif args.command == "start-research-task":
        model = research_model_from_environment()
        config = WorkflowConfig.model_validate_json(args.workflow_config) if args.workflow_config else None
        fingerprint = start_research_task(args.task_id, model_version=model.model_version,
                                          workflow_config=config,
                                          question_outbound_authorized=args.allow_question_outbound)
        print(json.dumps({"status": "PLANNING", "run_fingerprint": fingerprint}))
    elif args.command == "list-human-reviews":
        with SessionLocal() as session:
            reviews = list(session.scalars(select(HumanReviewRequest).where(
                HumanReviewRequest.task_id == args.task_id
            ).order_by(HumanReviewRequest.created_at, HumanReviewRequest.id)))
            print(json.dumps([{"request_id": str(item.id), "status": item.status,
                               "reason_code": item.reason_code,
                               "interrupted_stage": item.interrupted_stage,
                               "resume_stage": item.resume_stage} for item in reviews]))
    elif args.command == "resolve-human-review":
        task_id = resolve_human_review(args.request_id, reviewer_id=args.reviewer, note=args.note)
        print(json.dumps({"task_id": str(task_id), "status": "STOP_EVALUATION"}))
    elif args.command == "show-structured-report":
        with SessionLocal() as session:
            report = session.scalar(select(StructuredReport).where(
                StructuredReport.task_id == args.task_id))
            if report is None:
                raise ValueError("research task has no structured report")
            print(json.dumps({"report_id": str(report.id), "content_hash": report.content_hash,
                              "content": report.content}, ensure_ascii=False))
    elif args.command == "queue-report-export":
        export_id = queue_report_export(args.task_id, args.format)
        print(json.dumps({"export_id": str(export_id)}))
    elif args.command == "run-report-export-next":
        export_id = process_next_report_export(worker_id=args.worker_id,
                                               export_id=args.export_id)
        print(json.dumps({"export_id": str(export_id) if export_id else None}))
    elif args.command == "show-report-export":
        with SessionLocal() as session:
            export = session.get(ReportExport, args.export_id)
            if export is None:
                raise ValueError("report export does not exist")
            job = session.get(TaskJob, export.job_id)
            artifact = session.get(Artifact, export.artifact_id) if export.artifact_id else None
            print(json.dumps({"export_id": str(export.id), "task_id": str(export.task_id),
                              "format": export.file_format,
                              "renderer_version": export.renderer_version,
                              "status": job.status, "attempts": job.attempts,
                              "last_error": job.last_error,
                              "artifact_id": str(artifact.id) if artifact else None,
                              "blob_sha256": artifact.blob_sha256 if artifact else None},
                             ensure_ascii=False))
    elif args.command == "save-report-export":
        with SessionLocal() as session:
            export = session.get(ReportExport, args.export_id)
            if export is None or export.artifact_id is None:
                raise ValueError("report export is not completed")
            artifact = session.get(Artifact, export.artifact_id)
            digest = artifact.blob_sha256
        source = ContentAddressedStore(settings.data_root).path_for(digest)
        content = source.read_bytes()
        if hashlib.sha256(content).hexdigest() != digest:
            raise ValueError("report export blob checksum differs from artifact")
        with args.output.open("xb") as stream:
            stream.write(content)
        print(json.dumps({"export_id": str(args.export_id), "output": str(args.output),
                          "blob_sha256": digest, "size_bytes": len(content)}))
    elif args.command == "plan-research-task":
        model = research_model_from_environment()
        ids = execute_planner(args.task_id, model=model)
        print(json.dumps({"status": "RETRIEVING", "subquestion_ids": [str(item) for item in ids]}))
    elif args.command == "retrieve-research-task":
        embedder, reranker = cloud_clients_from_environment()
        count = retrieve_for_task(
            args.task_id, embedder=embedder, reranker=reranker, limit=args.limit
        )
        print(json.dumps({"new_evidence_count": count}))
    elif args.command == "prepare-first-round":
        ids = prepare_first_round(args.task_id)
        print(json.dumps({"status": "RESEARCHING", "agent_run_ids": [str(item) for item in ids]}))
    elif args.command == "run-first-round":
        model = research_model_from_environment()
        ids = execute_first_round(args.task_id, model=model)
        print(json.dumps({"claim_ids": [str(item) for item in ids]}))
    elif args.command == "pause-research-task":
        print(json.dumps({"control_state": request_research_pause(args.task_id)}))
    elif args.command == "resume-research-task":
        print(json.dumps({"phase": resume_research_task(args.task_id)}))
    elif args.command == "cancel-research-task":
        print(json.dumps({"control_state": cancel_research_task(args.task_id)}))
    elif args.command == "audit-claim-mechanical":
        print(json.dumps(mechanical_audit_claim(args.claim_id)))
    elif args.command == "audit-claim-semantic":
        with SessionLocal() as session:
            claim = session.get(Claim, args.claim_id)
            if claim is None:
                raise ValueError("Claim does not exist")
            task = session.get(ResearchTask, claim.task_id)
            model_version = task.execution_context["generation_model"]
        model = research_model_for_version(model_version)
        print(json.dumps(semantic_audit_claim(args.claim_id, model=model), ensure_ascii=False))
    elif args.command == "prepare-critic":
        print(json.dumps({"agent_run_id": str(prepare_critic_round(args.task_id))}))
    elif args.command == "run-critic":
        with SessionLocal() as session:
            run = session.get(AgentRun, args.agent_run_id)
            if run is None:
                raise ValueError("Critic AgentRun does not exist")
            model_version = run.model_version
        model = research_model_for_version(model_version)
        print(json.dumps({"critique_ids": [str(item) for item in execute_critic(
            args.agent_run_id, model=model,
        )]}))
    elif args.command == "retrieve-evidence-requests":
        embedder, reranker = cloud_clients_from_environment()
        count = retrieve_evidence_requests(args.task_id, embedder=embedder,
                                           reranker=reranker)
        print(json.dumps({"new_evidence_count": count}))
    elif args.command == "prepare-rebuttal":
        print(json.dumps({"agent_run_id": str(prepare_rebuttal_round(args.task_id))}))
    elif args.command == "run-rebuttal":
        with SessionLocal() as session:
            run = session.get(AgentRun, args.agent_run_id)
            if run is None or run.role != "Rebuttal":
                raise ValueError("Rebuttal AgentRun does not exist")
            model_version = run.model_version
        model = research_model_for_version(model_version)
        print(json.dumps({"rebuttal_ids": [str(item) for item in execute_rebuttal(
            args.agent_run_id, model=model,
        )]}))
    elif args.command == "audit-revised-claims":
        with SessionLocal() as session:
            task = session.get(ResearchTask, args.task_id)
            if task is None or task.execution_context is None:
                raise ValueError("research task does not exist or has not started")
            model_version = task.execution_context["generation_model"]
        model = research_model_for_version(model_version)
        print(json.dumps({"results": audit_revised_claims(args.task_id, model=model)},
                         ensure_ascii=False))
    elif args.command == "normalize-claims":
        print(json.dumps(normalize_task_claims(args.task_id), ensure_ascii=False))
    elif args.command in {"run-research-next", "run-research-worker"}:
        embedder, reranker = cloud_clients_from_environment()
        if args.command == "run-research-next":
            job_id = run_next_research_job(
                worker_id=args.worker_id,
                embedder=embedder, reranker=reranker, task_id=args.task_id,
            )
            print(json.dumps({"job_id": str(job_id) if job_id else None}))
        else:
            if args.poll_seconds < 0.1:
                parser.error("--poll-seconds must be at least 0.1")
            try:
                while True:
                    job_id = run_next_research_job(
                        worker_id=args.worker_id,
                        embedder=embedder, reranker=reranker,
                    )
                    if job_id is None:
                        time.sleep(args.poll_seconds)
            except KeyboardInterrupt:
                pass
    elif args.command == "activate-knowledge":
        activate_knowledge_version(args.knowledge_version_id, args.index_build_id)
        print(json.dumps({"status": "READY", "knowledge_version_id": str(args.knowledge_version_id)}))
    elif args.command == "compare-knowledge":
        print(json.dumps(compare_knowledge_versions(args.left_id, args.right_id)))
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

