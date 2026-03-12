from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Literal

SuspectLevel = Literal["RACE_SUSPECT", "REPEATED_RACE_SUSPECT", "HIGH_CONFIDENCE_SUSPECT"]
EventType = Literal["METHOD_ENTER", "METHOD_EXIT", "FIELD_BEFORE", "FIELD_AFTER", "DEADLOCK_CHECK", "UNKNOWN"]


@dataclass(frozen=True)
class RuntimeEvent:
    event_type: EventType
    timestamp: datetime | None
    thread_name: str
    thread_id: str
    class_name: str
    method_name: str
    field_name: str | None
    is_write: bool | None
    raw_line: str

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["timestamp"] = self.timestamp.isoformat() if self.timestamp else None
        return payload


@dataclass
class ActiveFieldAccess:
    thread_key: str
    thread_name: str
    class_name: str
    method_name: str
    field_name: str
    is_write: bool
    started_at: datetime | None


@dataclass
class RaceSuspect:
    level: SuspectLevel
    class_name: str
    field_name: str
    witness_threads: list[str]
    witness_methods: list[str]
    overlap_count: int
    first_seen: datetime | None
    last_seen: datetime | None
    message: str
    evidence: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["first_seen"] = self.first_seen.isoformat() if self.first_seen else None
        payload["last_seen"] = self.last_seen.isoformat() if self.last_seen else None
        return payload
