"""One-use desktop bootstrap and persistent local session service."""

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from tcm_platform.api_contract import Actor, ApiError, require_if_match
from tcm_platform.audit import append_event
from tcm_platform.config import settings
from tcm_platform.db import SessionLocal
from tcm_platform.ids import new_id
from tcm_platform.models import LocalBootstrapGrant, LocalSession, utc_now

BOOTSTRAP_STARTED_AT = utc_now()
SESSION_CAPABILITIES = (
    "knowledge.read", "knowledge.write", "research.read", "research.write",
    "jobs.read", "jobs.write", "session.manage", "settings.manage",
)
COOKIE_NAME = "tcm_local_session"


@dataclass(frozen=True)
class IssuedSession:
    cookie_token: str
    csrf_token: str
    public_id: str
    actor_id: str
    capabilities: tuple[str, ...]
    expires_at: datetime


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _issue_session(session: Session, *, development: bool = False) -> IssuedSession:
    token = secrets.token_urlsafe(32)
    csrf = _hash("development-csrf:" + token) if development else secrets.token_urlsafe(32)
    expires = utc_now() + timedelta(seconds=settings.session_ttl_seconds)
    local_session = LocalSession(id=new_id(), public_id=f"LS-{new_id()}",
                                 token_hash=_hash(token), csrf_hash=_hash(csrf),
                                 actor_id="local-owner", capabilities=list(SESSION_CAPABILITIES),
                                 row_version=1, expires_at=expires)
    session.add(local_session)
    session.flush()
    append_event(session, event_type="local_session.started", actor_id="local-owner",
                 aggregate_id=local_session.id,
                 payload={"session_public_id": local_session.public_id})
    return IssuedSession(token, csrf, local_session.public_id, local_session.actor_id,
                         SESSION_CAPABILITIES, expires)


def development_local_session(cookie_token: str | None) -> IssuedSession:
    if not settings.development_auto_session:
        raise ApiError("DEVELOPMENT_SESSION_DISABLED", status=404, category="configuration",
                       detail="development auto-session is disabled")
    if cookie_token:
        try:
            actor = current_actor(cookie_token)
        except ApiError as exc:
            if exc.code != "SESSION_REQUIRED":
                raise
        else:
            # Recover the same tab-independent CSRF token without invalidating other tabs.
            csrf = _hash("development-csrf:" + cookie_token)
            if hmac.compare_digest(actor.csrf_hash, _hash(csrf)):
                return IssuedSession(cookie_token, csrf, actor.session_public_id, actor.actor_id,
                                     tuple(sorted(actor.capabilities)), actor.expires_at)
    with SessionLocal.begin() as session:
        return _issue_session(session, development=True)


def bootstrap_local_session(submitted_secret: str) -> IssuedSession:
    configured = settings.bootstrap_secret
    if configured is None:
        raise ApiError("BOOTSTRAP_UNAVAILABLE", status=503, category="configuration",
                       detail="desktop bootstrap is not configured", retryable=True)
    raw_secret = configured.get_secret_value()
    if len(raw_secret) < 32:
        raise ApiError("BOOTSTRAP_UNAVAILABLE", status=503, category="configuration",
                       detail="desktop bootstrap secret is too short")
    configured_hash = _hash(raw_secret)
    if not hmac.compare_digest(configured_hash, _hash(submitted_secret)):
        raise ApiError("INVALID_BOOTSTRAP", status=401, category="authentication",
                       detail="bootstrap secret is invalid or expired")
    now = utc_now()
    with SessionLocal.begin() as session:
        session.execute(insert(LocalBootstrapGrant).values(
            secret_hash=configured_hash,
            expires_at=BOOTSTRAP_STARTED_AT + timedelta(seconds=settings.bootstrap_ttl_seconds),
            created_at=BOOTSTRAP_STARTED_AT,
        ).on_conflict_do_nothing(index_elements=["secret_hash"]))
        grant = session.scalar(select(LocalBootstrapGrant).where(
            LocalBootstrapGrant.secret_hash == configured_hash).with_for_update())
        if grant.used_at is not None or grant.expires_at <= now:
            raise ApiError("INVALID_BOOTSTRAP", status=401, category="authentication",
                           detail="bootstrap secret is invalid or expired")
        grant.used_at = now
        return _issue_session(session)


def current_actor(token: str | None) -> Actor:
    if not token or len(token) > 256:
        raise ApiError("SESSION_REQUIRED", status=401, category="authentication",
                       detail="a local session is required")
    token_hash = _hash(token)
    with SessionLocal() as session:
        row = session.scalar(select(LocalSession).where(LocalSession.token_hash == token_hash))
        if row is None or row.revoked_at is not None or row.expires_at <= utc_now():
            raise ApiError("SESSION_REQUIRED", status=401, category="authentication",
                           detail="local session is missing or expired")
        return Actor(row.actor_id, row.public_id, row.token_hash, row.csrf_hash,
                     frozenset(row.capabilities), row.row_version, row.expires_at)


def require_csrf(actor: Actor, submitted_token: str | None) -> None:
    if (not submitted_token or len(submitted_token) > 256
            or not hmac.compare_digest(actor.csrf_hash, _hash(submitted_token))):
        raise ApiError("CSRF_REQUIRED", status=403, category="authorization",
                       detail="valid X-CSRF-Token is required for this command")


def revoke_local_session(actor: Actor, *, if_match: str | None) -> None:
    actor.require("session.manage")
    with SessionLocal.begin() as session:
        row = session.scalar(select(LocalSession).where(
            LocalSession.token_hash == actor.session_token_hash).with_for_update())
        if row is None or row.revoked_at is not None or row.expires_at <= utc_now():
            raise ApiError("SESSION_REQUIRED", status=401, category="authentication",
                           detail="local session is missing or expired")
        require_if_match(if_match, row.public_id, row.row_version)
        row.revoked_at = utc_now()
        row.row_version += 1
        append_event(session, event_type="local_session.revoked", actor_id=actor.actor_id,
                     aggregate_id=row.id, payload={"session_public_id": row.public_id})
