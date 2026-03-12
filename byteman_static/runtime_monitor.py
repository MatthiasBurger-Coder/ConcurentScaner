from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO

from byteman_static.runtime_model import ActiveFieldAccess, RaceSuspect, RuntimeEvent
from byteman_static.runtime_parser import parse_runtime_event


@dataclass(frozen=True)
class MonitorConfig:
    log_file: Path
    follow: bool = True
    start_at_end: bool = True
    poll_interval_seconds: float = 0.25
    repeated_threshold: int = 3
    high_confidence_threshold: int = 6
    report_file: Path | None = None
    emit_raw_events: bool = False
    stop_after_idle_seconds: float | None = None


@dataclass
class MonitorStats:
    total_lines: int = 0
    parsed_events: int = 0
    ignored_lines: int = 0
    race_suspects: int = 0
    repeated_suspects: int = 0
    high_confidence_suspects: int = 0


class RuntimeLogFollower:
    def __init__(self, log_file: Path, start_at_end: bool, poll_interval_seconds: float) -> None:
        self._log_file = log_file
        self._start_at_end = start_at_end
        self._poll_interval_seconds = poll_interval_seconds

    def follow(self, do_follow: bool, stop_after_idle_seconds: float | None = None):
        stream: TextIO | None = None
        current_inode: tuple[int, int] | None = None
        idle_started = time.monotonic()
        first_open = True

        while True:
            if not self._log_file.exists():
                if not do_follow:
                    break
                time.sleep(self._poll_interval_seconds)
                if stop_after_idle_seconds and time.monotonic() - idle_started > stop_after_idle_seconds:
                    break
                continue

            stat = self._log_file.stat()
            inode = (int(stat.st_ino), int(stat.st_dev))
            truncated = stream is not None and stream.tell() > stat.st_size
            rotated = stream is not None and current_inode != inode

            if stream is None or rotated or truncated:
                if stream is not None:
                    stream.close()
                stream = self._log_file.open("r", encoding="utf-8", errors="replace")
                current_inode = inode
                if self._start_at_end and first_open and do_follow:
                    stream.seek(0, 2)
                elif truncated:
                    stream.seek(0)
                first_open = False

            assert stream is not None
            line = stream.readline()
            if line:
                idle_started = time.monotonic()
                yield line
                continue

            if not do_follow:
                break

            time.sleep(self._poll_interval_seconds)
            if stop_after_idle_seconds and time.monotonic() - idle_started > stop_after_idle_seconds:
                break

        if stream is not None:
            stream.close()


class RaceSuspectAggregator:
    def __init__(self, repeated_threshold: int, high_confidence_threshold: int) -> None:
        self._repeated_threshold = max(repeated_threshold, 1)
        self._high_confidence_threshold = max(high_confidence_threshold, self._repeated_threshold)
        self._active_by_field: dict[tuple[str, str], list[ActiveFieldAccess]] = {}
        self._active_by_thread_field: dict[tuple[str, str, str], list[ActiveFieldAccess]] = {}
        self._overlap_count_by_field: dict[tuple[str, str], int] = {}
        self._first_seen_by_field: dict[tuple[str, str], datetime] = {}

    def process_event(self, event: RuntimeEvent) -> list[RaceSuspect]:
        if event.event_type == "FIELD_BEFORE":
            return self._on_field_before(event)
        if event.event_type == "FIELD_AFTER":
            self._on_field_after(event)
        return []

    def _on_field_before(self, event: RuntimeEvent) -> list[RaceSuspect]:
        if not event.field_name:
            return []
        class_field_key = (event.class_name, event.field_name)
        thread_key = _thread_key(event)
        is_write = bool(event.is_write)
        access = ActiveFieldAccess(
            thread_key=thread_key,
            thread_name=event.thread_name,
            class_name=event.class_name,
            method_name=event.method_name,
            field_name=event.field_name,
            is_write=is_write,
            started_at=event.timestamp,
        )

        suspects: list[RaceSuspect] = []
        overlaps = self._active_by_field.get(class_field_key, [])
        for other in overlaps:
            if other.thread_key == access.thread_key:
                continue
            if not (other.is_write or access.is_write):
                continue
            suspects.append(self._build_suspect(access, other, event.timestamp))

        self._active_by_field.setdefault(class_field_key, []).append(access)
        thread_field_key = (thread_key, event.class_name, event.field_name)
        self._active_by_thread_field.setdefault(thread_field_key, []).append(access)
        return suspects

    def _on_field_after(self, event: RuntimeEvent) -> None:
        if not event.field_name:
            return
        thread_key = _thread_key(event)
        thread_field_key = (thread_key, event.class_name, event.field_name)
        stack = self._active_by_thread_field.get(thread_field_key)
        if not stack:
            return
        finished = stack.pop()
        if not stack:
            self._active_by_thread_field.pop(thread_field_key, None)

        class_field_key = (event.class_name, event.field_name)
        active_list = self._active_by_field.get(class_field_key)
        if not active_list:
            return
        for idx in range(len(active_list) - 1, -1, -1):
            candidate = active_list[idx]
            if candidate.thread_key == finished.thread_key and candidate.method_name == finished.method_name:
                active_list.pop(idx)
                break
        if not active_list:
            self._active_by_field.pop(class_field_key, None)

    def _build_suspect(
        self, access: ActiveFieldAccess, other: ActiveFieldAccess, now_ts: datetime | None
    ) -> RaceSuspect:
        class_field_key = (access.class_name, access.field_name)
        count = self._overlap_count_by_field.get(class_field_key, 0) + 1
        self._overlap_count_by_field[class_field_key] = count

        if class_field_key not in self._first_seen_by_field:
            self._first_seen_by_field[class_field_key] = _coalesce_timestamp(now_ts)

        level = "RACE_SUSPECT"
        if count >= self._high_confidence_threshold:
            level = "HIGH_CONFIDENCE_SUSPECT"
        elif count >= self._repeated_threshold:
            level = "REPEATED_RACE_SUSPECT"

        message = (
            f"{level} class={access.class_name} field={access.field_name} "
            f"threads={other.thread_name}|{access.thread_name} overlap_count={count}"
        )
        return RaceSuspect(
            level=level,
            class_name=access.class_name,
            field_name=access.field_name,
            witness_threads=sorted({other.thread_name, access.thread_name}),
            witness_methods=sorted({other.method_name, access.method_name}),
            overlap_count=count,
            first_seen=self._first_seen_by_field[class_field_key],
            last_seen=_coalesce_timestamp(now_ts),
            message=message,
            evidence=[
                {
                    "thread_a": other.thread_name,
                    "thread_b": access.thread_name,
                    "method_a": other.method_name,
                    "method_b": access.method_name,
                    "write_a": other.is_write,
                    "write_b": access.is_write,
                }
            ],
        )


class RuntimeLogMonitor:
    def __init__(self, config: MonitorConfig) -> None:
        self._config = config
        self._stats = MonitorStats()
        self._aggregator = RaceSuspectAggregator(
            repeated_threshold=config.repeated_threshold,
            high_confidence_threshold=config.high_confidence_threshold,
        )

    @property
    def stats(self) -> MonitorStats:
        return self._stats

    def run(self) -> MonitorStats:
        reporter = _JsonLineReporter(self._config.report_file) if self._config.report_file else None
        follower = RuntimeLogFollower(
            log_file=self._config.log_file,
            start_at_end=self._config.start_at_end,
            poll_interval_seconds=self._config.poll_interval_seconds,
        )
        try:
            for line in follower.follow(
                do_follow=self._config.follow, stop_after_idle_seconds=self._config.stop_after_idle_seconds
            ):
                self._stats.total_lines += 1
                event = parse_runtime_event(line)
                if event is None:
                    self._stats.ignored_lines += 1
                    continue
                self._stats.parsed_events += 1

                if self._config.emit_raw_events:
                    print(_format_raw_event(event))
                if reporter:
                    reporter.emit("RAW_EVENT", event.to_dict())

                suspects = self._aggregator.process_event(event)
                for suspect in suspects:
                    self._count_suspect(suspect.level)
                    print(suspect.message)
                    if reporter:
                        reporter.emit(suspect.level, suspect.to_dict())
        finally:
            if reporter:
                reporter.close()
        return self._stats

    def _count_suspect(self, level: str) -> None:
        if level == "RACE_SUSPECT":
            self._stats.race_suspects += 1
        elif level == "REPEATED_RACE_SUSPECT":
            self._stats.repeated_suspects += 1
        elif level == "HIGH_CONFIDENCE_SUSPECT":
            self._stats.high_confidence_suspects += 1


class _JsonLineReporter:
    def __init__(self, report_file: Path) -> None:
        report_file.parent.mkdir(parents=True, exist_ok=True)
        self._stream = report_file.open("a", encoding="utf-8")

    def emit(self, record_type: str, payload: dict) -> None:
        envelope = {
            "record_type": record_type,
            "emitted_at": datetime.now(tz=UTC).isoformat(),
            "payload": payload,
        }
        self._stream.write(json.dumps(envelope, ensure_ascii=True) + "\n")
        self._stream.flush()

    def close(self) -> None:
        self._stream.close()


def _thread_key(event: RuntimeEvent) -> str:
    return f"{event.thread_id}:{event.thread_name}"


def _coalesce_timestamp(ts: datetime | None) -> datetime:
    if ts is not None:
        return ts
    return datetime.now(tz=UTC)


def _format_raw_event(event: RuntimeEvent) -> str:
    field_part = f" field={event.field_name}" if event.field_name else ""
    write_part = f" write={event.is_write}" if event.is_write is not None else ""
    return (
        f"RAW_EVENT type={event.event_type} thread={event.thread_name} tid={event.thread_id} "
        f"class={event.class_name} method={event.method_name}{field_part}{write_part}"
    )
