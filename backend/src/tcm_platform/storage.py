import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from tcm_platform.ids import new_id
from tcm_platform.models import Artifact, BlobObject


@dataclass(frozen=True)
class StoredBlob:
    sha256: str
    size_bytes: int
    path: Path


class ContentAddressedStore:
    def __init__(self, root: Path):
        self.root = root

    def path_for(self, sha256: str) -> Path:
        if len(sha256) != 64 or any(c not in "0123456789abcdef" for c in sha256):
            raise ValueError("invalid SHA-256 digest")
        return self.root / "objects" / "sha256" / sha256[:2] / sha256[2:4] / sha256

    def put(self, source: BinaryIO, *, max_bytes: int | None = None) -> StoredBlob:
        staging = self.root / "staging"
        staging.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        size = 0
        fd, temp_name = tempfile.mkstemp(prefix="blob-", dir=staging)
        temp = Path(temp_name)
        try:
            with os.fdopen(fd, "wb") as output:
                while chunk := source.read(1024 * 1024):
                    size += len(chunk)
                    if max_bytes is not None and size > max_bytes:
                        raise ValueError("file exceeds configured size limit")
                    digest.update(chunk)
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
            sha256 = digest.hexdigest()
            target = self.path_for(sha256)
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                # Hard link creation is atomic and refuses to replace an immutable blob.
                os.link(temp, target)
            except FileExistsError:
                self._verify(target, sha256, size)
            return StoredBlob(sha256, size, target)
        finally:
            temp.unlink(missing_ok=True)

    def _verify(self, path: Path, sha256: str, size: int) -> None:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            actual_size = 0
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
                actual_size += len(chunk)
        if actual_size != size or digest.hexdigest() != sha256:
            raise OSError("existing content-addressed blob is corrupt")

    def register(
        self,
        session: Session,
        blob: StoredBlob,
        *,
        artifact_type: str,
        retention_class: str,
        original_name: str | None = None,
    ) -> Artifact:
        # The caller commits this row together with the business reference and EventLog.
        self._verify(blob.path, blob.sha256, blob.size_bytes)
        session.execute(
            insert(BlobObject)
            .values(sha256=blob.sha256, size_bytes=blob.size_bytes)
            .on_conflict_do_nothing(index_elements=["sha256"])
        )
        existing = session.get(BlobObject, blob.sha256)
        if existing is None or existing.size_bytes != blob.size_bytes:
            raise ValueError("blob metadata conflicts with on-disk content")
        artifact = Artifact(
            id=new_id(),
            blob_sha256=blob.sha256,
            artifact_type=artifact_type,
            retention_class=retention_class,
            original_name=original_name,
        )
        session.add(artifact)
        session.flush()
        return artifact

