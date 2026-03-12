from __future__ import annotations

import threading
import time
from datetime import UTC, datetime
from pathlib import Path

from byteman_static.runtime_model import RuntimeEvent
from byteman_static.runtime_monitor import MonitorConfig, RaceSuspectAggregator, RuntimeLogMonitor
from byteman_static.runtime_parser import parse_runtime_event


def test_runtime_parser_supports_key_value_and_json_lines() -> None:
    kv_line = (
        "BTM_EVT ts=2026-03-12T20:00:00.100Z event=FIELD_BEFORE "
        "thread=t1 tid=11 class=com.verifier.Counter method=inc() field=value write=true"
    )
    event = parse_runtime_event(kv_line)
    assert event is not None
    assert event.event_type == "FIELD_BEFORE"
    assert event.thread_name == "t1"
    assert event.thread_id == "11"
    assert event.class_name == "com.verifier.Counter"
    assert event.method_name == "inc()"
    assert event.field_name == "value"
    assert event.is_write is True

    json_line = (
        '{"event":"FIELD_AFTER","timestamp":"2026-03-12T20:00:00.120Z","thread":"t2","tid":"12",'
        '"class":"com.verifier.Counter","method":"read()","field":"value","write":"false"}'
    )
    json_event = parse_runtime_event(json_line)
    assert json_event is not None
    assert json_event.event_type == "FIELD_AFTER"
    assert json_event.is_write is False


def test_race_suspect_levels_progression() -> None:
    agg = RaceSuspectAggregator(repeated_threshold=2, high_confidence_threshold=4)
    emitted = []
    for i in range(4):
        ts = datetime(2026, 3, 12, 20, 0, i, tzinfo=UTC)
        emitted.extend(
            agg.process_event(
                RuntimeEvent(
                    event_type="FIELD_BEFORE",
                    timestamp=ts,
                    thread_name="writer",
                    thread_id="1",
                    class_name="com.verifier.Counter",
                    method_name="inc()",
                    field_name="value",
                    is_write=True,
                    raw_line="w",
                )
            )
        )
        emitted.extend(
            agg.process_event(
                RuntimeEvent(
                    event_type="FIELD_BEFORE",
                    timestamp=ts,
                    thread_name="reader",
                    thread_id="2",
                    class_name="com.verifier.Counter",
                    method_name="read()",
                    field_name="value",
                    is_write=False,
                    raw_line="r",
                )
            )
        )
        agg.process_event(
            RuntimeEvent(
                event_type="FIELD_AFTER",
                timestamp=ts,
                thread_name="reader",
                thread_id="2",
                class_name="com.verifier.Counter",
                method_name="read()",
                field_name="value",
                is_write=False,
                raw_line="ra",
            )
        )
        agg.process_event(
            RuntimeEvent(
                event_type="FIELD_AFTER",
                timestamp=ts,
                thread_name="writer",
                thread_id="1",
                class_name="com.verifier.Counter",
                method_name="inc()",
                field_name="value",
                is_write=True,
                raw_line="wa",
            )
        )

    levels = [suspect.level for suspect in emitted]
    assert "RACE_SUSPECT" in levels
    assert "REPEATED_RACE_SUSPECT" in levels
    assert "HIGH_CONFIDENCE_SUSPECT" in levels


def test_read_read_overlap_does_not_emit_suspect() -> None:
    agg = RaceSuspectAggregator(repeated_threshold=2, high_confidence_threshold=3)
    first = RuntimeEvent(
        event_type="FIELD_BEFORE",
        timestamp=None,
        thread_name="reader-a",
        thread_id="10",
        class_name="com.verifier.Counter",
        method_name="read()",
        field_name="value",
        is_write=False,
        raw_line="a",
    )
    second = RuntimeEvent(
        event_type="FIELD_BEFORE",
        timestamp=None,
        thread_name="reader-b",
        thread_id="11",
        class_name="com.verifier.Counter",
        method_name="read()",
        field_name="value",
        is_write=False,
        raw_line="b",
    )
    assert agg.process_event(first) == []
    assert agg.process_event(second) == []


def test_single_thread_write_read_does_not_emit_suspect() -> None:
    agg = RaceSuspectAggregator(repeated_threshold=2, high_confidence_threshold=3)
    before_write = RuntimeEvent(
        event_type="FIELD_BEFORE",
        timestamp=None,
        thread_name="worker",
        thread_id="100",
        class_name="com.verifier.Counter",
        method_name="inc()",
        field_name="value",
        is_write=True,
        raw_line="before-write",
    )
    before_read = RuntimeEvent(
        event_type="FIELD_BEFORE",
        timestamp=None,
        thread_name="worker",
        thread_id="100",
        class_name="com.verifier.Counter",
        method_name="read()",
        field_name="value",
        is_write=False,
        raw_line="before-read",
    )
    assert agg.process_event(before_write) == []
    assert agg.process_event(before_read) == []


def test_monitor_ignores_malformed_lines_without_crashing(tmp_path: Path) -> None:
    log_file = tmp_path / "runtime.log"
    log_file.write_text(
        "not-parseable-line\n"
        "BTM_EVT ts=2026-03-12T20:00:00.100Z event=FIELD_BEFORE thread=t1 tid=1 class=a method=b field=f write=true\n",
        encoding="utf-8",
    )
    monitor = RuntimeLogMonitor(
        MonitorConfig(
            log_file=log_file,
            follow=False,
            start_at_end=False,
            poll_interval_seconds=0.01,
        )
    )
    stats = monitor.run()
    assert stats.total_lines == 2
    assert stats.parsed_events == 1
    assert stats.ignored_lines == 1


def test_monitor_handles_log_truncation_during_follow(tmp_path: Path) -> None:
    log_file = tmp_path / "runtime.log"
    report_file = tmp_path / "report.jsonl"
    log_file.write_text("", encoding="utf-8")
    monitor = RuntimeLogMonitor(
        MonitorConfig(
            log_file=log_file,
            follow=True,
            start_at_end=False,
            poll_interval_seconds=0.05,
            stop_after_idle_seconds=1.5,
            report_file=report_file,
            repeated_threshold=2,
            high_confidence_threshold=3,
        )
    )

    holder: dict[str, object] = {}

    def runner() -> None:
        holder["stats"] = monitor.run()

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    time.sleep(0.15)

    log_file.write_text(
        "BTM_EVT ts=2026-03-12T20:00:00.100Z event=FIELD_BEFORE thread=t1 tid=1 class=c method=m field=v write=true\n",
        encoding="utf-8",
    )
    time.sleep(0.15)
    # Truncate and write a second event sequence.
    log_file.write_text(
        "BTM_EVT ts=2026-03-12T20:00:00.200Z event=FIELD_BEFORE thread=t2 tid=2 class=c method=r field=v write=false\n"
        "BTM_EVT ts=2026-03-12T20:00:00.220Z event=FIELD_AFTER thread=t2 tid=2 class=c method=r field=v write=false\n"
        "BTM_EVT ts=2026-03-12T20:00:00.240Z event=FIELD_AFTER thread=t1 tid=1 class=c method=m field=v write=true\n",
        encoding="utf-8",
    )

    thread.join(timeout=5.0)
    assert not thread.is_alive()
    stats = holder["stats"]
    assert stats.parsed_events >= 2
    assert report_file.exists()
    report_text = report_file.read_text(encoding="utf-8")
    assert "RAW_EVENT" in report_text


def test_duplicate_and_partial_order_events_do_not_crash_monitor(tmp_path: Path) -> None:
    log_file = tmp_path / "runtime.log"
    log_file.write_text(
        "BTM_EVT ts=2026-03-12T20:00:00.100Z event=FIELD_BEFORE thread=t1 tid=1 class=c method=m field=v write=true\n"
        "BTM_EVT ts=2026-03-12T20:00:00.101Z event=FIELD_BEFORE thread=t2 tid=2 class=c method=r field=v write=false\n"
        "BTM_EVT ts=2026-03-12T20:00:00.101Z event=FIELD_BEFORE thread=t2 tid=2 class=c method=r field=v write=false\n"
        "partial-line-without-format\n"
        "BTM_EVT ts=2026-03-12T20:00:00.200Z event=FIELD_AFTER thread=t2 tid=2 class=c method=r field=v write=false\n",
        encoding="utf-8",
    )
    monitor = RuntimeLogMonitor(
        MonitorConfig(
            log_file=log_file,
            follow=False,
            start_at_end=False,
            poll_interval_seconds=0.01,
            stop_after_idle_seconds=0.5,
        )
    )
    stats = monitor.run()
    assert stats.total_lines == 5
    assert stats.parsed_events >= 4
