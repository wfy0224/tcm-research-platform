import secrets
import time
from uuid import UUID


def new_id() -> UUID:
    """Generate a time-ordered RFC 9562 UUIDv7 on Python 3.11+."""
    timestamp_ms = int(time.time() * 1000) & ((1 << 48) - 1)
    random_a = secrets.randbits(12)
    random_b = secrets.randbits(62)
    value = (timestamp_ms << 80) | (7 << 76) | (random_a << 64) | (2 << 62) | random_b
    return UUID(int=value)

