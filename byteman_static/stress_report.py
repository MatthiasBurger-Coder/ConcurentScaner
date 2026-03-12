from __future__ import annotations

import json
from pathlib import Path

from byteman_static.stress_model import (
    OutcomeLevel,
    StressAggregateSummary,
    StressIterationObservation,
    StressIterationResult,
)

SUSPECT_LEVELS = ("RACE_SUSPECT", "REPEATED_RACE_SUSPECT", "HIGH_CONFIDENCE_SUSPECT")


def summarize_iteration_report(report_file: Path) -> StressIterationObservation:
    observation = StressIterationObservation()
    if not report_file.exists():
        return observation

    with report_file.open("r", encoding="utf-8", errors="replace") as stream:
        for raw_line in stream:
            line = raw_line.strip()
            if not line:
                continue
            observation.total_records += 1
            try:
                envelope = json.loads(line)
            except json.JSONDecodeError:
                observation.malformed_records += 1
                continue
            if not isinstance(envelope, dict):
                observation.malformed_records += 1
                continue

            record_type = str(envelope.get("record_type", ""))
            payload = envelope.get("payload", {})
            if not isinstance(payload, dict):
                payload = {}

            if record_type == "RAW_EVENT":
                observation.raw_events += 1
                continue
            if record_type not in SUSPECT_LEVELS:
                continue

            observation.suspects_by_level[record_type] = observation.suspects_by_level.get(record_type, 0) + 1
            pattern_key = _pattern_key(payload)
            observation.pattern_counts[pattern_key] = observation.pattern_counts.get(pattern_key, 0) + 1
    return observation


def aggregate_stress_results(
    scenario_id: str,
    iteration_results: list[StressIterationResult],
    repeated_pattern_threshold: int,
    high_confidence_pattern_threshold: int,
) -> StressAggregateSummary:
    total_iterations = len(iteration_results)
    successful_iterations = sum(1 for item in iteration_results if item.succeeded)
    failed_iterations = total_iterations - successful_iterations
    iterations_with_suspect = sum(1 for item in iteration_results if item.observation.has_suspect)
    iterations_without_suspect = total_iterations - iterations_with_suspect

    total_raw_events = 0
    suspects_by_level: dict[str, int] = {}
    repeated_patterns: dict[str, int] = {}
    for result in iteration_results:
        observation = result.observation
        total_raw_events += observation.raw_events
        for level, count in observation.suspects_by_level.items():
            suspects_by_level[level] = suspects_by_level.get(level, 0) + count
        for pattern_key, count in observation.pattern_counts.items():
            repeated_patterns[pattern_key] = repeated_patterns.get(pattern_key, 0) + count

    outcome_level = _classify_outcome(
        suspects_by_level=suspects_by_level,
        repeated_patterns=repeated_patterns,
        repeated_pattern_threshold=max(repeated_pattern_threshold, 1),
        high_confidence_pattern_threshold=max(high_confidence_pattern_threshold, 1),
    )

    return StressAggregateSummary(
        scenario_id=scenario_id,
        total_iterations=total_iterations,
        successful_iterations=successful_iterations,
        failed_iterations=failed_iterations,
        iterations_with_suspect=iterations_with_suspect,
        iterations_without_suspect=iterations_without_suspect,
        total_raw_events=total_raw_events,
        suspects_by_level=suspects_by_level,
        repeated_patterns=dict(sorted(repeated_patterns.items(), key=lambda item: (-item[1], item[0]))),
        outcome_level=outcome_level,
    )


def _pattern_key(payload: dict) -> str:
    class_name = str(payload.get("class_name", "unknown"))
    field_name = str(payload.get("field_name", "unknown"))
    methods = payload.get("witness_methods", [])
    if isinstance(methods, list):
        methods_token = "|".join(sorted(str(item) for item in methods))
    else:
        methods_token = str(methods)
    return f"{class_name}::{field_name}::{methods_token}"


def _classify_outcome(
    suspects_by_level: dict[str, int],
    repeated_patterns: dict[str, int],
    repeated_pattern_threshold: int,
    high_confidence_pattern_threshold: int,
) -> OutcomeLevel:
    if suspects_by_level.get("HIGH_CONFIDENCE_SUSPECT", 0) > 0:
        return "HIGH_CONFIDENCE_SUSPICIOUS"

    max_pattern_hits = max(repeated_patterns.values(), default=0)
    if suspects_by_level.get("REPEATED_RACE_SUSPECT", 0) > 0 or max_pattern_hits >= high_confidence_pattern_threshold:
        return "REPEATED_SUSPICIOUS"
    if suspects_by_level.get("RACE_SUSPECT", 0) > 0 or max_pattern_hits >= repeated_pattern_threshold:
        return "SUSPICIOUS"
    return "BENIGN"
