from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from byteman_static.cli import main as cli_main
from byteman_static.runtime_monitor import MonitorStats
from byteman_static.stress_model import (
    StressIterationObservation,
    StressIterationResult,
    StressRunConfig,
    StressScenario,
)
from byteman_static.stress_report import aggregate_stress_results, summarize_iteration_report
from byteman_static.stress_runner import execute_stress_run, load_stress_scenario


def test_load_stress_scenario_resolves_relative_paths(tmp_path: Path) -> None:
    source_root = tmp_path / "src"
    source_root.mkdir(parents=True)
    scenario_file = tmp_path / "scenario.json"
    scenario_file.write_text(
        json.dumps(
            {
                "scenario_id": "fixture-scenario",
                "source_root": "src",
                "main_class": "com.example.Main",
                "package_prefix": "com.example",
                "default_iterations": 7,
                "default_concurrency_level": 3,
            }
        ),
        encoding="utf-8",
    )

    scenario = load_stress_scenario(scenario_file)
    assert scenario.scenario_id == "fixture-scenario"
    assert scenario.source_root == source_root.resolve()
    assert scenario.main_class == "com.example.Main"
    assert scenario.default_iterations == 7
    assert scenario.default_concurrency_level == 3


def test_load_stress_scenario_requires_main_class(tmp_path: Path) -> None:
    scenario_file = tmp_path / "scenario.json"
    scenario_file.write_text(
        json.dumps(
            {
                "scenario_id": "broken",
                "source_root": "src",
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_stress_scenario(scenario_file)


def test_summarize_iteration_report_handles_malformed_and_suspects(tmp_path: Path) -> None:
    report_file = tmp_path / "watcher-report.jsonl"
    report_file.write_text(
        "\n".join(
            [
                json.dumps({"record_type": "RAW_EVENT", "payload": {"event_type": "FIELD_BEFORE"}}),
                "malformed json line",
                json.dumps(
                    {
                        "record_type": "RACE_SUSPECT",
                        "payload": {
                            "class_name": "com.example.Counter",
                            "field_name": "value",
                            "witness_methods": ["inc()", "read()"],
                        },
                    }
                ),
                json.dumps(
                    {
                        "record_type": "REPEATED_RACE_SUSPECT",
                        "payload": {
                            "class_name": "com.example.Counter",
                            "field_name": "value",
                            "witness_methods": ["inc()", "read()"],
                        },
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    observation = summarize_iteration_report(report_file)
    assert observation.total_records == 4
    assert observation.raw_events == 1
    assert observation.malformed_records == 1
    assert observation.suspects_by_level["RACE_SUSPECT"] == 1
    assert observation.suspects_by_level["REPEATED_RACE_SUSPECT"] == 1
    assert observation.pattern_counts["com.example.Counter::value::inc()|read()"] == 2


def test_summarize_iteration_report_missing_file_is_empty(tmp_path: Path) -> None:
    observation = summarize_iteration_report(tmp_path / "missing-report.jsonl")
    assert observation.total_records == 0
    assert observation.raw_events == 0
    assert observation.suspects_by_level == {}


def test_aggregate_stress_results_classifies_repeated_suspicion() -> None:
    now = datetime(2026, 3, 12, 21, 0, 0, tzinfo=UTC)
    base_result = StressIterationResult(
        iteration=1,
        started_at=now,
        finished_at=now,
        exit_code=0,
        command=["/tmp/run.sh"],
        runtime_log_file=Path("/tmp/runtime.log"),
        report_file=Path("/tmp/report.jsonl"),
        app_stdout_file=Path("/tmp/stdout.log"),
        app_stderr_file=Path("/tmp/stderr.log"),
        monitor_stats=MonitorStats(parsed_events=5),
        observation=StressIterationObservation(
            raw_events=5,
            suspects_by_level={"RACE_SUSPECT": 1},
            pattern_counts={"com.example.Counter::value::inc()|read()": 1},
        ),
    )
    second_result = StressIterationResult(
        iteration=2,
        started_at=now,
        finished_at=now,
        exit_code=0,
        command=["/tmp/run.sh"],
        runtime_log_file=Path("/tmp/runtime2.log"),
        report_file=Path("/tmp/report2.jsonl"),
        app_stdout_file=Path("/tmp/stdout2.log"),
        app_stderr_file=Path("/tmp/stderr2.log"),
        monitor_stats=MonitorStats(parsed_events=5),
        observation=StressIterationObservation(
            raw_events=6,
            suspects_by_level={"RACE_SUSPECT": 1},
            pattern_counts={"com.example.Counter::value::inc()|read()": 1},
        ),
    )
    summary = aggregate_stress_results(
        scenario_id="demo",
        iteration_results=[base_result, second_result],
        repeated_pattern_threshold=2,
        high_confidence_pattern_threshold=5,
    )
    assert summary.total_iterations == 2
    assert summary.iterations_with_suspect == 2
    assert summary.total_raw_events == 11
    assert summary.outcome_level == "SUSPICIOUS"


def test_execute_stress_run_with_mocked_processes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import byteman_static.stress_runner as stress_runner_module
    from byteman_static.generator import GeneratorOutput
    from byteman_static.model import AnalysisResult

    source_root = tmp_path / "src"
    source_root.mkdir(parents=True)
    (source_root / "Main.java").write_text("package com.example; class Main {}", encoding="utf-8")
    byteman_jar = tmp_path / "byteman.jar"
    byteman_jar.write_text("jar", encoding="utf-8")

    def fake_generator(config):
        config.output_dir.mkdir(parents=True, exist_ok=True)
        rules = config.output_dir / "generated-rules.btm"
        inv = config.output_dir / "Byteman.log"
        rules.write_text("RULE X\nENDRULE\n", encoding="utf-8")
        inv.write_text("FILE demo\n", encoding="utf-8")
        return GeneratorOutput(
            analysis=AnalysisResult(
                scanned_files=1,
                parsed_files=1,
                parse_failures=0,
                java_files=[],
                parser_backend="tree-sitter-java",
            ),
            byteman_log_path=inv,
            rules_path=rules,
            runtime_log_path=config.output_dir / "Byteman.runtime.log",
            metadata_path=None,
            generated_rules=1,
        )

    class FakeMonitor:
        def __init__(self, config):
            self.config = config

        def run(self):
            if self.config.report_file:
                self.config.report_file.parent.mkdir(parents=True, exist_ok=True)
                self.config.report_file.write_text(
                    "\n".join(
                        [
                            json.dumps({"record_type": "RAW_EVENT", "payload": {"event_type": "FIELD_BEFORE"}}),
                            json.dumps(
                                {
                                    "record_type": "RACE_SUSPECT",
                                    "payload": {
                                        "class_name": "com.example.Counter",
                                        "field_name": "value",
                                        "witness_methods": ["inc()", "read()"],
                                    },
                                }
                            ),
                        ]
                    )
                    + "\n",
                    encoding="utf-8",
                )
            return MonitorStats(total_lines=2, parsed_events=2, race_suspects=1)

    def fake_subprocess_run(command, cwd=None, stdout=None, stderr=None, check=False, env=None):
        if command[0] == "javac":
            return SimpleNamespace(returncode=0)
        runtime_log = Path(env["BYTEMAN_RUNTIME_LOG"])
        runtime_log.parent.mkdir(parents=True, exist_ok=True)
        runtime_log.write_text(
            "BTM_EVT ts=2026-03-12T20:00:00.100Z event=FIELD_BEFORE thread=t1 tid=1 class=c method=w field=v write=true\n",
            encoding="utf-8",
        )
        if stdout:
            stdout.write("MAIN_DONE\n")
        if stderr:
            stderr.write("byteman enabled\n")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(stress_runner_module, "run_generator", fake_generator)
    monkeypatch.setattr(stress_runner_module, "RuntimeLogMonitor", FakeMonitor)
    monkeypatch.setattr(stress_runner_module.subprocess, "run", fake_subprocess_run)

    scenario = StressScenario(
        scenario_id="fake",
        source_root=source_root,
        main_class="com.example.Main",
    )
    config = StressRunConfig(
        scenario=scenario,
        output_dir=tmp_path / "stress-out",
        iterations=2,
        concurrency_level=3,
        byteman_jar=byteman_jar,
    )
    result = execute_stress_run(config)
    assert result.summary.total_iterations == 2
    assert result.summary.successful_iterations == 2
    assert result.summary.iterations_with_suspect == 2
    assert result.summary.outcome_level == "SUSPICIOUS"
    assert result.summary_file.exists()
    assert result.results_file.exists()


def test_execute_stress_run_fails_on_missing_byteman_jar(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import byteman_static.stress_runner as stress_runner_module
    from byteman_static.generator import GeneratorOutput
    from byteman_static.model import AnalysisResult

    source_root = tmp_path / "src"
    source_root.mkdir(parents=True)
    (source_root / "Main.java").write_text("package com.example; class Main {}", encoding="utf-8")

    def fake_generator(config):
        config.output_dir.mkdir(parents=True, exist_ok=True)
        rules = config.output_dir / "generated-rules.btm"
        inv = config.output_dir / "Byteman.log"
        rules.write_text("RULE X\nENDRULE\n", encoding="utf-8")
        inv.write_text("FILE demo\n", encoding="utf-8")
        return GeneratorOutput(
            analysis=AnalysisResult(
                scanned_files=1,
                parsed_files=1,
                parse_failures=0,
                java_files=[],
                parser_backend="tree-sitter-java",
            ),
            byteman_log_path=inv,
            rules_path=rules,
            runtime_log_path=config.output_dir / "Byteman.runtime.log",
            metadata_path=None,
            generated_rules=1,
        )

    monkeypatch.setattr(stress_runner_module, "run_generator", fake_generator)
    monkeypatch.setattr(stress_runner_module.StressRunner, "_compile_sources", lambda *args, **kwargs: None)

    scenario = StressScenario(
        scenario_id="missing-jar",
        source_root=source_root,
        main_class="com.example.Main",
    )
    config = StressRunConfig(
        scenario=scenario,
        output_dir=tmp_path / "stress-out",
        iterations=1,
        concurrency_level=2,
        byteman_jar=tmp_path / "does-not-exist.jar",
    )
    with pytest.raises(FileNotFoundError):
        execute_stress_run(config)


def test_cli_stress_run_wires_configuration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import byteman_static.cli as cli_module

    source_root = tmp_path / "src"
    source_root.mkdir(parents=True)
    byteman_jar = tmp_path / "byteman.jar"
    byteman_jar.write_text("jar", encoding="utf-8")
    scenario = StressScenario(
        scenario_id="cli-demo",
        source_root=source_root,
        main_class="com.example.Main",
        byteman_jar=byteman_jar,
        default_iterations=4,
        default_concurrency_level=2,
    )
    captured = {}

    def fake_load(_path):
        return scenario

    def fake_execute(config):
        captured["config"] = config
        return SimpleNamespace(
            summary=SimpleNamespace(
                scenario_id="cli-demo",
                outcome_level="BENIGN",
                total_iterations=config.iterations,
                successful_iterations=config.iterations,
                failed_iterations=0,
                iterations_with_suspect=0,
                iterations_without_suspect=config.iterations,
                total_raw_events=0,
                suspects_by_level={},
            ),
            rules_file=Path("/tmp/rules.btm"),
            inventory_file=Path("/tmp/Byteman.log"),
            startup_script=Path("/tmp/run-with-byteman.sh"),
            summary_file=Path("/tmp/stress-summary.json"),
            results_file=Path("/tmp/stress-results.json"),
        )

    monkeypatch.setattr(cli_module, "load_stress_scenario", fake_load)
    monkeypatch.setattr(cli_module, "execute_stress_run", fake_execute)

    rc = cli_main(
        [
            "stress-run",
            "--scenario-file",
            str(tmp_path / "scenario.json"),
            "--output-dir",
            str(tmp_path / "out"),
            "--iterations",
            "6",
            "--concurrency-level",
            "5",
        ]
    )
    assert rc == 0
    config = captured["config"]
    assert config.iterations == 6
    assert config.concurrency_level == 5
