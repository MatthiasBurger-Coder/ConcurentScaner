from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from byteman_static.runtime_monitor import MonitorStats

OutcomeLevel = Literal["BENIGN", "SUSPICIOUS", "REPEATED_SUSPICIOUS", "HIGH_CONFIDENCE_SUSPICIOUS"]


@dataclass(frozen=True)
class StressScenario:
    scenario_id: str
    source_root: Path
    main_class: str
    description: str | None = None
    package_prefix: str | None = None
    package_regex: str | None = None
    helper_class: str = "com.example.byteman.RuntimeTraceHelper"
    java_sources_glob: str = "**/*.java"
    app_args: list[str] = field(default_factory=list)
    scenario_env: dict[str, str] = field(default_factory=dict)
    default_iterations: int = 10
    default_concurrency_level: int = 2
    byteman_jar: Path | None = None


@dataclass(frozen=True)
class StressRunConfig:
    scenario: StressScenario
    output_dir: Path
    iterations: int
    concurrency_level: int
    byteman_jar: Path
    java_command: str = "java"
    javac_command: str = "javac"
    watcher_poll_interval_seconds: float = 0.25
    watcher_idle_seconds: float = 3.0
    repeated_threshold: int = 3
    high_confidence_threshold: int = 6
    emit_raw_events: bool = False
    fail_fast: bool = False


@dataclass
class StressIterationObservation:
    total_records: int = 0
    raw_events: int = 0
    malformed_records: int = 0
    suspects_by_level: dict[str, int] = field(default_factory=dict)
    pattern_counts: dict[str, int] = field(default_factory=dict)

    @property
    def has_suspect(self) -> bool:
        return sum(self.suspects_by_level.values()) > 0


@dataclass
class StressIterationResult:
    iteration: int
    started_at: datetime
    finished_at: datetime
    exit_code: int
    command: list[str]
    runtime_log_file: Path
    report_file: Path
    app_stdout_file: Path
    app_stderr_file: Path
    monitor_stats: MonitorStats
    observation: StressIterationObservation
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.exit_code == 0 and self.error is None


@dataclass
class StressAggregateSummary:
    scenario_id: str
    total_iterations: int
    successful_iterations: int
    failed_iterations: int
    iterations_with_suspect: int
    iterations_without_suspect: int
    total_raw_events: int
    suspects_by_level: dict[str, int]
    repeated_patterns: dict[str, int]
    outcome_level: OutcomeLevel


@dataclass
class StressRunResult:
    config: StressRunConfig
    run_dir: Path
    classes_dir: Path
    generated_dir: Path
    rules_file: Path
    inventory_file: Path
    startup_script: Path
    summary_file: Path
    results_file: Path
    iterations: list[StressIterationResult]
    summary: StressAggregateSummary

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(asdict(self))


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value
