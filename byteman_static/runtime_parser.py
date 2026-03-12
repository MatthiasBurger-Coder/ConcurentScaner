from __future__ import annotations

import json
import shlex
from datetime import UTC, datetime

from byteman_static.runtime_model import EventType, RuntimeEvent


def parse_runtime_event(line: str) -> RuntimeEvent | None:
    raw_line = line.rstrip("\n")
    if not raw_line:
        return None

    payload: dict[str, str]
    if raw_line.startswith("BTM_EVT "):
        payload = _parse_key_value_payload(raw_line[len("BTM_EVT ") :])
    elif raw_line.startswith("{"):
        payload = _parse_json_payload(raw_line)
    else:
        return None

    event_type = _parse_event_type(payload.get("event", payload.get("phase", "UNKNOWN")))
    timestamp = _parse_timestamp(payload.get("ts", payload.get("timestamp")))
    thread_name = payload.get("thread", payload.get("threadName", "unknown"))
    thread_id = payload.get("tid", payload.get("threadId", thread_name))
    class_name = payload.get("class", payload.get("className", "unknown"))
    method_name = payload.get("method", payload.get("methodName", "unknown"))
    field_name = payload.get("field", payload.get("fieldName"))
    is_write = _parse_optional_bool(payload.get("write", payload.get("isWrite")))

    return RuntimeEvent(
        event_type=event_type,
        timestamp=timestamp,
        thread_name=thread_name,
        thread_id=thread_id,
        class_name=class_name,
        method_name=method_name,
        field_name=field_name,
        is_write=is_write,
        raw_line=raw_line,
    )


def _parse_key_value_payload(payload_text: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for token in shlex.split(payload_text, posix=True):
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        parsed[key] = value
    return parsed


def _parse_json_payload(raw_line: str) -> dict[str, str]:
    try:
        obj = json.loads(raw_line)
    except json.JSONDecodeError:
        return {}
    if not isinstance(obj, dict):
        return {}
    return {str(key): str(value) for key, value in obj.items()}


def _parse_event_type(token: str) -> EventType:
    normalized = token.strip().upper()
    if normalized in {"METHOD_ENTER", "ENTER"}:
        return "METHOD_ENTER"
    if normalized in {"METHOD_EXIT", "EXIT"}:
        return "METHOD_EXIT"
    if normalized in {"FIELD_BEFORE", "BEFORE_FIELD_ACCESS", "FIELD_ACCESS_BEGIN"}:
        return "FIELD_BEFORE"
    if normalized in {"FIELD_AFTER", "AFTER_FIELD_ACCESS", "FIELD_ACCESS_END"}:
        return "FIELD_AFTER"
    if normalized in {"DEADLOCK_CHECK", "CHECK_DEADLOCK"}:
        return "DEADLOCK_CHECK"
    return "UNKNOWN"


def _parse_timestamp(token: str | None) -> datetime | None:
    if not token:
        return None
    token = token.strip()
    if not token:
        return None

    if token.isdigit():
        timestamp_value = int(token)
        if timestamp_value > 10_000_000_000:
            return datetime.fromtimestamp(timestamp_value / 1000, tz=UTC)
        return datetime.fromtimestamp(timestamp_value, tz=UTC)

    if token.endswith("Z"):
        token = token[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(token)
    except ValueError:
        return None


def _parse_optional_bool(token: str | None) -> bool | None:
    if token is None:
        return None
    lowered = token.strip().lower()
    if lowered in {"true", "1", "yes", "y"}:
        return True
    if lowered in {"false", "0", "no", "n"}:
        return False
    return None
