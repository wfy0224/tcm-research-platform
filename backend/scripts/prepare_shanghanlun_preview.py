"""Index a pinned public-domain Shanghan Lun excerpt with real cloud models.

This seeds a dedicated preview database. Automated approval here verifies the
retrieval pipeline; it is not an expert review of the historical transcription.
"""

import hashlib
from pathlib import Path

from sqlalchemy import select, text

from tcm_platform.cloud_models import cloud_clients_from_environment
from tcm_platform.db import SessionLocal
from tcm_platform.knowledge_publish import (
    activate_knowledge_version,
    create_index_build,
    create_knowledge_version,
    review_object,
)
from tcm_platform.knowledge_service import create_evidence
from tcm_platform.models import (
    EvidenceRevision,
    ImportJob,
    IndexBuild,
    KnowledgeRuntimeState,
    KnowledgeVersion,
    SourceDocument,
    SourceRevision,
    TextSegmentRevision,
)
from tcm_platform.outbound_policy import (
    POLICY_VERSION,
    current_mode,
    set_source_outbound_policy,
    version_source_ids,
)
from tcm_platform.retrieval import build_retrieval_index
from tcm_platform.segment_service import process_next_segment
from tcm_platform.source_import import SourceMetadata, import_file, process_next_import
from tcm_platform.storage import ContentAddressedStore

SOURCE_PATH = Path("/workspace/backend/fixtures/shanghanlun_taiyang_upper.txt")
STORE_PATH = Path("/tmp/tcm_preview_shanghanlun_store")
SOURCE_SHA256 = "65b83255eeb4f4e300301b1e144e758e0cf38e559d92f227372c9c586a11c4c4"
EXPECTED_PARAGRAPHS = 29


def main() -> None:
    with SessionLocal() as session:
        if session.scalar(text("SELECT current_database()")) != "tcm_preview_shanghanlun":
            raise RuntimeError("seed script requires tcm_preview_shanghanlun database")
    canonical_source = SOURCE_PATH.read_bytes().replace(b"\r\n", b"\n")
    if hashlib.sha256(canonical_source).hexdigest() != SOURCE_SHA256:
        raise RuntimeError("source excerpt differs from pinned Wikisource revision")
    if current_mode() != "CLOUD_ALLOWED":
        raise RuntimeError("set TCM_OUTBOUND_MODE=CLOUD_ALLOWED for governed preview")
    embedder, reranker = cloud_clients_from_environment()

    legacy_configuration = None
    with SessionLocal() as session:
        runtime = session.get(KnowledgeRuntimeState, 1)
        if runtime and runtime.active_index_build_id:
            build = session.get(IndexBuild, runtime.active_index_build_id)
            if (build.configuration.get("embedding_model") != embedder.model_version
                    or build.configuration.get("rerank_model") != reranker.model_version):
                raise RuntimeError("active preview index has different cloud models")
            if (build.configuration.get("outbound_mode") == "CLOUD_ALLOWED"
                    and build.configuration.get("outbound_policy_version") == POLICY_VERSION
                    and build.configuration.get("embedding_endpoint") == embedder.endpoint
                    and build.configuration.get("rerank_endpoint") == reranker.endpoint):
                print("public corpus and governed model index are already active")
                return
            if current_mode() != "CLOUD_ALLOWED":
                raise RuntimeError("set TCM_OUTBOUND_MODE=CLOUD_ALLOWED before reindexing preview")
            source_ids = version_source_ids(session, build.knowledge_version_id)
            if len(source_ids) != 1:
                raise RuntimeError("legacy preview must contain exactly one pinned source")
            source_id = source_ids[0]
            source = session.get(SourceDocument, source_id)
            revisions = list(session.scalars(select(SourceRevision).where(
                SourceRevision.source_id == source_id)))
            if (source is None or source.copyright_status != "PUBLIC_DOMAIN"
                    or not any(row.file_sha256 == SOURCE_SHA256 for row in revisions)):
                raise RuntimeError("legacy preview source does not match the authorized corpus")
            legacy_configuration = build.configuration

    if legacy_configuration is not None:
        set_source_outbound_policy(
            source_id, data_level="PUBLIC", authorized=True,
            reason="User authorized pinned public-domain Shanghan Lun preview corpus",
            actor_id="preview-curator",
        )
        version_id = create_knowledge_version(actor_id="preview-curator")
        build_id = create_index_build(version_id, configuration={
            "strategy": legacy_configuration.get("strategy", "hybrid-rrf-v1"),
            "embedding_model": embedder.model_version,
            "rerank_model": reranker.model_version,
            "embedding_endpoint": embedder.endpoint,
            "rerank_endpoint": reranker.endpoint,
        }, actor_id="preview-curator")
        build_retrieval_index(build_id, embedder=embedder, actor_id="preview-curator")
        activate_knowledge_version(version_id, build_id, actor_id="preview-curator")
        print("legacy preview was reindexed under the governed outbound policy")
        return

    store = ContentAddressedStore(STORE_PATH)
    imported = import_file(
        SOURCE_PATH,
        SourceMetadata(
            source_type="CLASSIC", title="傷寒論（宋本）·辨太陽病脈證並治（上）",
            author="張仲景", era="漢", edition="維基文庫修訂 2607901；非方劑條文摘錄",
            publisher="維基文庫", copyright_status="PUBLIC_DOMAIN", language="zh-Hant",
            data_level="PUBLIC", outbound_authorized=True,
            outbound_reason="User authorized public-domain Shanghan Lun preview corpus",
        ),
        request_key="shanghanlun-taiyang-upper-wikisource-2607901", store=store,
        actor_id="preview-import",
    )
    with SessionLocal() as session:
        status = session.get(ImportJob, imported.import_job_id).status
    if status == "REGISTERED":
        result = process_next_import(store=store)
        if result is None or result.status != "PARSED":
            raise RuntimeError("source parsing did not finish")
        status = "PARSED"
    if status == "PARSED":
        result = process_next_segment(store=store)
        if result is None or result.status != "SEGMENTED":
            raise RuntimeError("source segmentation did not finish")

    with SessionLocal() as session:
        segment_ids = list(session.scalars(select(TextSegmentRevision.id).where(
            TextSegmentRevision.source_revision_id == imported.source_revision_id,
            TextSegmentRevision.segment_type == "PARAGRAPH",
        ).order_by(TextSegmentRevision.sequence_no)))
    if len(segment_ids) != EXPECTED_PARAGRAPHS:
        raise RuntimeError(f"expected {EXPECTED_PARAGRAPHS} source paragraphs, got {len(segment_ids)}")
    for segment_id in segment_ids:
        with SessionLocal() as session:
            revision = session.scalar(select(EvidenceRevision).where(
                EvidenceRevision.anchor_segment_revision_id == segment_id,
            ))
            revision_id = revision.id if revision else None
            revision_status = revision.status if revision else None
        if revision_id is None:
            revision_id = create_evidence([segment_id], strength="DIRECT")
            revision_status = "DRAFT"
        if revision_status == "DRAFT":
            review_object("evidence_revision", revision_id, reviewer_id="preview-import",
                          decision="APPROVE",
                          note="公版原文自动导入；尚未经本项目专家复核")

    with SessionLocal() as session:
        version = session.scalar(select(KnowledgeVersion).order_by(
            KnowledgeVersion.version_no.desc()).limit(1))
        version_id = version.id if version else None
    if version_id is None:
        version_id = create_knowledge_version(actor_id="preview-import")

    with SessionLocal() as session:
        build = session.scalar(select(IndexBuild).where(
            IndexBuild.knowledge_version_id == version_id).limit(1))
        build_id = build.id if build else None
        build_status = build.status if build else None
    if build_id is None:
        build_id = create_index_build(version_id, configuration={
            "strategy": "hybrid-rrf-v1", "embedding_model": embedder.model_version,
            "rerank_model": reranker.model_version,
            "embedding_endpoint": embedder.endpoint,
            "rerank_endpoint": reranker.endpoint,
        }, actor_id="preview-import")
        build_status = "PENDING"
    if build_status == "PENDING":
        count = build_retrieval_index(build_id, embedder=embedder,
                                      actor_id="preview-import")
        print(f"real embedding indexed {count} source passages")
    activate_knowledge_version(version_id, build_id, actor_id="preview-import")
    print(f"active corpus: {EXPECTED_PARAGRAPHS} passages, "
          f"embedding={embedder.model_version}, reranker={reranker.model_version}")


if __name__ == "__main__":
    main()
