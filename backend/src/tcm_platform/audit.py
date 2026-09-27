import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from tcm_platform.ids import new_id
from tcm_platform.models import EventLog, EventLogHead

GENESIS_HASH = "0" * 64


def event_digest(
    sequence_no: int,
    previous_hash: str,
    event_type: str,
    actor_id: str,
    aggregate_id: str,
    payload: dict,
    occurred_at: datetime,
) -> str:
    canonical = json.dumps(
        {
            "sequence_no": sequence_no,
            "previous_hash": previous_hash,
            "event_type": event_type,
            "actor_id": actor_id,
            "aggregate_id": aggregate_id,
            "payload": payload,
            "occurred_at": occurred_at.isoformat(),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def append_event(
    session: Session,
    *,
    event_type: str,
    actor_id: str,
    aggregate_id: UUID | str,
    payload: dict,
) -> EventLog:
    """Append in the caller's business transaction; serialize through the head row."""
    head = session.execute(select(EventLogHead).where(EventLogHead.id == 1).with_for_update()).scalar_one()
    sequence_no = head.sequence_no + 1
    occurred_at = datetime.now(UTC)
    event_hash = event_digest(
        sequence_no, head.last_hash, event_type, actor_id, str(aggregate_id), payload, occurred_at
    )
    event = EventLog(
        id=new_id(),
        sequence_no=sequence_no,
        event_type=event_type,
        actor_id=actor_id,
        aggregate_id=str(aggregate_id),
        payload=payload,
        previous_hash=head.last_hash,
        event_hash=event_hash,
        occurred_at=occurred_at,
    )
    session.add(event)
    head.sequence_no = sequence_no
    head.last_hash = event_hash
    return event


def verify_chain(session: Session) -> bool:
    previous = GENESIS_HASH
    expected_sequence = 1
    for event in session.scalars(select(EventLog).order_by(EventLog.sequence_no)):
        if event.sequence_no != expected_sequence or event.previous_hash != previous:
            return False
        calculated = event_digest(
            event.sequence_no,
            event.previous_hash,
            event.event_type,
            event.actor_id,
            event.aggregate_id,
            event.payload,
            event.occurred_at,
        )
        if event.event_hash != calculated:
            return False
        previous = calculated
        expected_sequence += 1
    head = session.get(EventLogHead, 1)
    return head is not None and head.sequence_no == expected_sequence - 1 and head.last_hash == previous

