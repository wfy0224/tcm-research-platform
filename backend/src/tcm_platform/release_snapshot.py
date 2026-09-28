"""Local release rollback manifests; portable database backup is a separate concern."""

import hashlib
import io
import json
from uuid import UUID

from sqlalchemy.orm import Session

from tcm_platform.config import settings
from tcm_platform.db import SessionLocal
from tcm_platform.ids import new_id
from tcm_platform.models import Artifact, IndexBuild, KnowledgeVersion, ReleaseSnapshot
from tcm_platform.storage import ContentAddressedStore


def _side(session: Session, version_id: UUID, build_id: UUID) -> dict:
    version = session.get(KnowledgeVersion, version_id)
    build = session.get(IndexBuild, build_id)
    if version is None or build is None or build.knowledge_version_id != version_id:
        raise ValueError("release snapshot knowledge/index pair is inconsistent")
    configuration = json.dumps(
        build.configuration, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return {
        "knowledge_version_id": str(version_id),
        "index_build_id": str(build_id),
        "knowledge_manifest_hash": version.manifest_hash,
        "reference_manifest_hash": version.reference_manifest_hash,
        "index_manifest_hash": build.manifest_hash,
        "index_configuration_hash": hashlib.sha256(configuration).hexdigest(),
    }


def _content(
    session: Session, snapshot_id: UUID, source_version_id: UUID,
    source_build_id: UUID, target_version_id: UUID, target_build_id: UUID,
) -> bytes:
    return json.dumps({
        "format": "release-snapshot/v1",
        "snapshot_id": str(snapshot_id),
        "source": _side(session, source_version_id, source_build_id),
        "target": _side(session, target_version_id, target_build_id),
    }, sort_keys=True, separators=(",", ":")).encode("utf-8")


def create_release_snapshot(
    session: Session, source_version_id: UUID, source_build_id: UUID,
    target_version_id: UUID, target_build_id: UUID,
) -> ReleaseSnapshot:
    """Freeze the last active pair in CAS within the release transaction."""
    snapshot_id = new_id()
    content = _content(session, snapshot_id, source_version_id, source_build_id,
                       target_version_id, target_build_id)
    store = ContentAddressedStore(settings.data_root)
    blob = store.put(io.BytesIO(content), max_bytes=1024 * 1024)
    artifact = store.register(
        session, blob, artifact_type="RELEASE_SNAPSHOT",
        retention_class="PERMANENT", original_name=f"{snapshot_id}.json",
    )
    snapshot = ReleaseSnapshot(
        id=snapshot_id, source_knowledge_version_id=source_version_id,
        source_index_build_id=source_build_id,
        target_knowledge_version_id=target_version_id,
        target_index_build_id=target_build_id,
        artifact_id=artifact.id, manifest_sha256=blob.sha256,
    )
    session.add(snapshot)
    session.flush()
    return snapshot


def validate_release_snapshot(
    session: Session, snapshot_id: UUID, *,
    source_version_id: UUID, source_build_id: UUID,
    target_version_id: UUID, target_build_id: UUID,
) -> ReleaseSnapshot:
    """Verify the immutable manifest before returning to the former active pair."""
    snapshot = session.get(ReleaseSnapshot, snapshot_id)
    if (snapshot is None
            or snapshot.source_knowledge_version_id != source_version_id
            or snapshot.source_index_build_id != source_build_id
            or snapshot.target_knowledge_version_id != target_version_id
            or snapshot.target_index_build_id != target_build_id):
        raise ValueError("release snapshot does not match this version switch")
    artifact = session.get(Artifact, snapshot.artifact_id)
    if (artifact is None or artifact.artifact_type != "RELEASE_SNAPSHOT"
            or artifact.blob_sha256 != snapshot.manifest_sha256):
        raise ValueError("release snapshot artifact is missing or inconsistent")
    expected = _content(session, snapshot.id, source_version_id, source_build_id,
                        target_version_id, target_build_id)
    path = ContentAddressedStore(settings.data_root).path_for(snapshot.manifest_sha256)
    try:
        actual = path.read_bytes()
    except OSError as exc:
        raise ValueError("release snapshot artifact is unavailable") from exc
    if (hashlib.sha256(actual).hexdigest() != snapshot.manifest_sha256
            or actual != expected):
        raise ValueError("release snapshot artifact differs from frozen versions")
    return snapshot


def restore_release_snapshot(
    snapshot_id: UUID, *, actor_id: str = "local-curator"
) -> None:
    """Re-activate the former pair through the normal publication gates."""
    with SessionLocal() as session:
        snapshot = session.get(ReleaseSnapshot, snapshot_id)
        if snapshot is None:
            raise ValueError("release snapshot does not exist")
        version_id = snapshot.source_knowledge_version_id
        build_id = snapshot.source_index_build_id
    from tcm_platform.knowledge_publish import activate_knowledge_version

    activate_knowledge_version(
        version_id, build_id, actor_id=actor_id, restore_snapshot_id=snapshot_id
    )
