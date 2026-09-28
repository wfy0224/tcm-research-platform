"""Fail-closed authorization for every remote model operation."""

import hashlib
import json
import os
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select

from tcm_platform.audit import append_event
from tcm_platform.db import SessionLocal
from tcm_platform.models import (
    Evidence,
    EvidenceRevision,
    KnowledgeVersionItem,
    SourceDocument,
)

POLICY_VERSION = "outbound-policy/v1"
_permit: ContextVar["OutboundPermit | None"] = ContextVar("model_outbound_permit", default=None)


@dataclass(frozen=True)
class OutboundPermit:
    operation: str
    model_version: str
    source_ids: tuple[UUID, ...]
    policy_hash: str
    task_id: UUID | None = None


def current_mode() -> str:
    mode = os.getenv("TCM_OUTBOUND_MODE", "LOCAL_ONLY").upper()
    if mode not in {"LOCAL_ONLY", "CLOUD_ALLOWED"}:
        raise ValueError("TCM_OUTBOUND_MODE must be LOCAL_ONLY or CLOUD_ALLOWED")
    return mode


def version_source_ids(session, version_id: UUID) -> tuple[UUID, ...]:
    ids = session.scalars(
        select(Evidence.source_id)
        .join(EvidenceRevision, EvidenceRevision.evidence_id == Evidence.id)
        .join(KnowledgeVersionItem,
              KnowledgeVersionItem.evidence_revision_id == EvidenceRevision.id)
        .where(KnowledgeVersionItem.knowledge_version_id == version_id)
    ).all()
    return tuple(sorted(set(ids), key=str))


@contextmanager
def authorize_outbound(
    operation: str, model_version: str, source_ids: Iterable[UUID], *,
    frozen_mode: str | None = None,
    frozen_policy_version: str | None = None,
    task_id: UUID | None = None,
) -> Iterator[OutboundPermit]:
    if operation not in {"complete", "embed", "rerank"}:
        raise ValueError("unknown outbound operation")
    if (current_mode() != "CLOUD_ALLOWED" or frozen_mode != "CLOUD_ALLOWED"
            or frozen_policy_version != POLICY_VERSION):
        raise PermissionError("remote model use is disabled by outbound policy")
    ids = tuple(sorted(set(source_ids), key=str))
    if not ids:
        raise PermissionError("remote model use requires an explicit source scope")
    with SessionLocal() as session:
        sources = session.scalars(select(SourceDocument).where(SourceDocument.id.in_(ids))).all()
        if len(sources) != len(ids) or any(
            source.data_level != "PUBLIC" or not source.outbound_authorized
            for source in sources
        ):
            raise PermissionError("source data level or authorization forbids remote model use")
    fingerprint = hashlib.sha256(json.dumps({
        "version": POLICY_VERSION, "operation": operation, "model": model_version,
        "sources": [str(item) for item in ids], "mode": frozen_mode,
    }, sort_keys=True).encode()).hexdigest()
    permit = OutboundPermit(operation, model_version, ids, fingerprint, task_id)
    token = _permit.set(permit)
    try:
        yield permit
    finally:
        _permit.reset(token)


def require_outbound(operation: str, model_version: str) -> OutboundPermit:
    permit = _permit.get()
    if (permit is None or permit.operation != operation
            or permit.model_version != model_version or current_mode() != "CLOUD_ALLOWED"):
        raise PermissionError("remote model call has no matching outbound authorization")
    return permit


def current_permit() -> OutboundPermit:
    permit = _permit.get()
    if permit is None:
        raise PermissionError("remote model call has no outbound authorization")
    return require_outbound(permit.operation, permit.model_version)


def set_source_outbound_policy(
    source_id: UUID, *, data_level: str, authorized: bool,
    reason: str, actor_id: str,
) -> None:
    if data_level not in {"PUBLIC", "RESTRICTED", "SENSITIVE"}:
        raise ValueError("unsupported data level")
    if authorized and data_level != "PUBLIC":
        raise ValueError("only explicitly reviewed public sources can be authorized")
    if not reason.strip() or not actor_id.strip():
        raise ValueError("policy change requires actor and reason")
    with SessionLocal.begin() as session:
        source = session.scalar(select(SourceDocument).where(
            SourceDocument.id == source_id
        ).with_for_update())
        if source is None:
            raise ValueError("source does not exist")
        source.data_level = data_level
        source.outbound_authorized = authorized
        append_event(session, event_type="source.outbound_policy_changed",
                     actor_id=actor_id, aggregate_id=source_id,
                     payload={"data_level": data_level, "authorized": authorized,
                              "reason": reason, "policy_version": POLICY_VERSION})
