import hashlib
import io
from datetime import UTC, datetime
from uuid import UUID

import pytest

from tcm_platform.audit import GENESIS_HASH, event_digest
from tcm_platform.ids import new_id
from tcm_platform.storage import ContentAddressedStore


def test_uuid_v7_layout_and_uniqueness():
    ids = [new_id() for _ in range(100)]
    assert all(isinstance(value, UUID) and value.version == 7 for value in ids)
    assert len(set(ids)) == len(ids)


def test_content_addressed_store_deduplicates_and_rejects_corruption(tmp_path):
    store = ContentAddressedStore(tmp_path)
    payload = b"source text\n" * 100
    first = store.put(io.BytesIO(payload))
    second = store.put(io.BytesIO(payload))
    assert first == second
    assert first.sha256 == hashlib.sha256(payload).hexdigest()
    assert first.path.read_bytes() == payload
    assert list((tmp_path / "staging").iterdir()) == []

    first.path.write_bytes(b"tampered")
    with pytest.raises(OSError, match="corrupt"):
        store.put(io.BytesIO(payload))


def test_event_hash_is_canonical_and_links_predecessor():
    occurred_at = datetime(2026, 9, 27, tzinfo=UTC)
    one = event_digest(1, GENESIS_HASH, "source.imported", "user", "source-1", {"b": 2, "a": 1}, occurred_at)
    reordered = event_digest(1, GENESIS_HASH, "source.imported", "user", "source-1", {"a": 1, "b": 2}, occurred_at)
    assert one == reordered
    assert event_digest(2, one, "source.parsed", "worker", "source-1", {}, occurred_at) != one
    assert event_digest(2, GENESIS_HASH, "source.parsed", "worker", "source-1", {}, occurred_at) != one

