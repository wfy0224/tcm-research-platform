from enum import StrEnum


class JobStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    RETRY_WAIT = "RETRY_WAIT"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ResourceClass(StrEnum):
    IO = "IO"
    CPU_PARSE = "CPU_PARSE"
    OCR = "OCR"
    EMBEDDING = "EMBEDDING"
    LLM_LOCAL = "LLM_LOCAL"
    LLM_REMOTE = "LLM_REMOTE"
    RERANK = "RERANK"
    DB_MAINTENANCE = "DB_MAINTENANCE"
    EXPORT = "EXPORT"


class HealthState(StrEnum):
    READY = "READY"
    DEGRADED = "DEGRADED"
    MAINTENANCE = "MAINTENANCE"
    NOT_READY = "NOT_READY"

