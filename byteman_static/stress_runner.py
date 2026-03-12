from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from byteman_static.generator import GeneratorConfig, run_generator
from byteman_static.linux_integration import LinuxStartupConfig, write_linux_startup_script
from byteman_static.runtime_monitor import MonitorConfig, MonitorStats, RuntimeLogMonitor
from byteman_static.stress_model import (
    StressAggregateSummary,
    StressIterationObservation,
    StressIterationResult,
    StressRunConfig,
    StressRunResult,
    StressScenario,
)
from byteman_static.stress_report import aggregate_stress_results, summarize_iteration_report


def load_stress_scenario(scenario_file: Path) -> StressScenario:
    if not scenario_file.exists():
        raise FileNotFoundError(f"Scenario file does not exist: {scenario_file}")

    try:
        raw_payload = json.loads(scenario_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid scenario JSON: {exc}") from exc
    if not isinstance(raw_payload, dict):
        raise ValueError("Scenario JSON must be an object.")

    payload = raw_payload.get("scenario", raw_payload)
    if not isinstance(payload, dict):
        raise ValueError("`scenario` must be an object when provided.")

    scenario_id = _required_string(payload, "scenario_id", default=scenario_file.stem)
    source_root_raw = _required_string(payload, "source_root")
    source_root = _resolve_path(scenario_file.parent, source_root_raw)
    main_class = _required_string(payload, "main_class")

    description = _optional_string(payload, "description")
    package_prefix = _optional_string(payload, "package_prefix")
    package_regex = _optional_string(payload, "package_regex")
    helper_class = _required_string(payload, "helper_class", default="com.example.byteman.RuntimeTraceHelper")
    java_sources_glob = _required_string(payload, "java_sources_glob", default="**/*.java")

    app_args_raw = payload.get("app_args", [])
    if not isinstance(app_args_raw, list):
        raise ValueError("`app_args` must be an array.")
    app_args = [str(item) for item in app_args_raw]

    env_raw = payload.get("env", {})
    if not isinstance(env_raw, dict):
        raise ValueError("`env` must be an object.")
    scenario_env = {str(key): str(value) for key, value in env_raw.items()}

    default_iterations = _positive_int(payload.get("default_iterations", 10), "default_iterations")
    default_concurrency_level = _positive_int(
        payload.get("default_concurrency_level", 2), "default_concurrency_level"
    )

    byteman_jar_raw = _optional_string(payload, "byteman_jar")
    byteman_jar = _resolve_path(scenario_file.parent, byteman_jar_raw) if byteman_jar_raw else None

    return StressScenario(
        scenario_id=scenario_id,
        source_root=source_root,
        main_class=main_class,
        description=description,
        package_prefix=package_prefix,
        package_regex=package_regex,
        helper_class=helper_class,
        java_sources_glob=java_sources_glob,
        app_args=app_args,
        scenario_env=scenario_env,
        default_iterations=default_iterations,
        default_concurrency_level=default_concurrency_level,
        byteman_jar=byteman_jar,
    )


def execute_stress_run(config: StressRunConfig) -> StressRunResult:
    return StressRunner(config).run()


class StressRunner:
    def __init__(self, config: StressRunConfig) -> None:
        self._config = config

    def run(self) -> StressRunResult:
        _validate_config(self._config)
        run_dir = self._config.output_dir.resolve()
        generated_dir = run_dir / "generated"
        classes_dir = run_dir / "classes"
        runs_dir = run_dir / "runs"
        generated_dir.mkdir(parents=True, exist_ok=True)
        classes_dir.mkdir(parents=True, exist_ok=True)
        runs_dir.mkdir(parents=True, exist_ok=True)

        source_files = _collect_java_sources(
            source_root=self._config.scenario.source_root,
            source_glob=self._config.scenario.java_sources_glob,
        )
        self._compile_sources(source_files=source_files, classes_dir=classes_dir, run_dir=run_dir)

        generator_output = run_generator(
            GeneratorConfig(
                source_root=self._config.scenario.source_root,
                output_dir=generated_dir,
                package_prefix=self._config.scenario.package_prefix,
                package_regex=self._config.scenario.package_regex,
                helper_class=self._config.scenario.helper_class,
                runtime_log_path=generated_dir / "Byteman.runtime.log",
            )
        )

        startup_script = write_linux_startup_script(
            LinuxStartupConfig(
                script_path=run_dir / "run-with-byteman.sh",
                rules_file=generator_output.rules_path,
                runtime_log_file=generated_dir / "Byteman.runtime.log",
                java_command=self._config.java_command,
            )
        )
        byteman_home = _prepare_byteman_home(run_dir=run_dir, byteman_jar=self._config.byteman_jar)

        iteration_results: list[StressIterationResult] = []
        for iteration in range(1, self._config.iterations + 1):
            result = self._run_iteration(
                iteration=iteration,
                runs_dir=runs_dir,
                startup_script=startup_script,
                rules_file=generator_output.rules_path,
                classes_dir=classes_dir,
                byteman_home=byteman_home,
            )
            iteration_results.append(result)
            if self._config.fail_fast and (not result.succeeded):
                break

        summary = aggregate_stress_results(
            scenario_id=self._config.scenario.scenario_id,
            iteration_results=iteration_results,
            repeated_pattern_threshold=self._config.repeated_threshold,
            high_confidence_pattern_threshold=self._config.high_confidence_threshold,
        )

        summary_file = run_dir / "stress-summary.json"
        results_file = run_dir / "stress-results.json"
        _write_json(summary_file, asdict(summary))
        _write_json(
            results_file,
            {
                "config": _jsonable(asdict(self._config)),
                "summary": asdict(summary),
                "iterations": [_jsonable(asdict(item)) for item in iteration_results],
            },
        )

        return StressRunResult(
            config=self._config,
            run_dir=run_dir,
            classes_dir=classes_dir,
            generated_dir=generated_dir,
            rules_file=generator_output.rules_path,
            inventory_file=generator_output.byteman_log_path,
            startup_script=startup_script,
            summary_file=summary_file,
            results_file=results_file,
            iterations=iteration_results,
            summary=summary,
        )

    def _compile_sources(self, source_files: list[Path], classes_dir: Path, run_dir: Path) -> None:
        compile_stdout = run_dir / "compile-stdout.log"
        compile_stderr = run_dir / "compile-stderr.log"
        arg_file = run_dir / "java-files.list"
        arg_file.write_text("\n".join(source.as_posix() for source in source_files) + "\n", encoding="utf-8")

        command = [self._config.javac_command, "-d", str(classes_dir), f"@{arg_file}"]
        with compile_stdout.open("w", encoding="utf-8") as stdout_stream, compile_stderr.open(
            "w", encoding="utf-8"
        ) as stderr_stream:
            completed = subprocess.run(
                command,
                cwd=run_dir,
                stdout=stdout_stream,
                stderr=stderr_stream,
                check=False,
            )
        if completed.returncode != 0:
            raise RuntimeError(
                f"javac failed with exit code {completed.returncode}. "
                f"See {compile_stdout} and {compile_stderr} for details."
            )

    def _run_iteration(
        self,
        iteration: int,
        runs_dir: Path,
        startup_script: Path,
        rules_file: Path,
        classes_dir: Path,
        byteman_home: Path,
    ) -> StressIterationResult:
        iteration_dir = runs_dir / f"iteration-{iteration:04d}"
        runtime_dir = iteration_dir / "runtime"
        runtime_dir.mkdir(parents=True, exist_ok=True)

        runtime_log_file = runtime_dir / "byteman-runtime.log"
        report_file = iteration_dir / "watcher-report.jsonl"
        app_stdout_file = iteration_dir / "app-stdout.log"
        app_stderr_file = iteration_dir / "app-stderr.log"
        runtime_log_file.write_text("", encoding="utf-8")

        monitor_stats_holder: dict[str, MonitorStats] = {}
        watcher_error_holder: dict[str, str] = {}
        monitor = RuntimeLogMonitor(
            MonitorConfig(
                log_file=runtime_log_file,
                follow=True,
                start_at_end=False,
                poll_interval_seconds=self._config.watcher_poll_interval_seconds,
                repeated_threshold=self._config.repeated_threshold,
                high_confidence_threshold=self._config.high_confidence_threshold,
                report_file=report_file,
                emit_raw_events=self._config.emit_raw_events,
                stop_after_idle_seconds=self._config.watcher_idle_seconds,
            )
        )

        def run_monitor() -> None:
            try:
                monitor_stats_holder["stats"] = monitor.run()
            except Exception as exc:  # pragma: no cover - defensive path
                watcher_error_holder["error"] = str(exc)

        monitor_thread = threading.Thread(target=run_monitor, daemon=True)
        monitor_thread.start()

        env = os.environ.copy()
        env.update(self._config.scenario.scenario_env)
        env.update(
            {
                "APP_CLASSPATH": classes_dir.as_posix(),
                "APP_MAIN_CLASS": self._config.scenario.main_class,
                "BYTEMAN_HOME": byteman_home.as_posix(),
                "BYTEMAN_RULES_FILE": rules_file.as_posix(),
                "BYTEMAN_RUNTIME_LOG": runtime_log_file.as_posix(),
                "STRESS_ITERATION": str(iteration),
                "STRESS_CONCURRENCY_LEVEL": str(self._config.concurrency_level),
            }
        )
        command = [startup_script.as_posix(), *self._config.scenario.app_args]

        started_at = datetime.now(tz=UTC)
        with app_stdout_file.open("w", encoding="utf-8") as stdout_stream, app_stderr_file.open(
            "w", encoding="utf-8"
        ) as stderr_stream:
            completed = subprocess.run(
                command,
                cwd=self._config.output_dir,
                env=env,
                stdout=stdout_stream,
                stderr=stderr_stream,
                check=False,
            )
        finished_at = datetime.now(tz=UTC)

        monitor_thread.join(timeout=max(self._config.watcher_idle_seconds, 1.0) + 20.0)
        error: str | None = None
        if monitor_thread.is_alive():
            error = "Runtime watcher did not stop before timeout."
        if watcher_error_holder.get("error"):
            error = f"Runtime watcher failed: {watcher_error_holder['error']}"
        if completed.returncode != 0 and error is None:
            error = f"Application exited with code {completed.returncode}"

        if not report_file.exists():
            report_file.write_text("", encoding="utf-8")

        monitor_stats = monitor_stats_holder.get("stats", MonitorStats())
        observation = summarize_iteration_report(report_file)
        return StressIterationResult(
            iteration=iteration,
            started_at=started_at,
            finished_at=finished_at,
            exit_code=completed.returncode,
            command=command,
            runtime_log_file=runtime_log_file,
            report_file=report_file,
            app_stdout_file=app_stdout_file,
            app_stderr_file=app_stderr_file,
            monitor_stats=monitor_stats,
            observation=observation,
            error=error,
        )


def _collect_java_sources(source_root: Path, source_glob: str) -> list[Path]:
    if not source_root.exists() or not source_root.is_dir():
        raise FileNotFoundError(f"Source root does not exist or is not a directory: {source_root}")
    source_files = sorted(source_root.glob(source_glob), key=lambda path: str(path).lower())
    if not source_files:
        raise FileNotFoundError(f"No Java sources matched `{source_glob}` under {source_root}")
    return source_files


def _prepare_byteman_home(run_dir: Path, byteman_jar: Path) -> Path:
    if not byteman_jar.exists():
        raise FileNotFoundError(f"Byteman jar not found: {byteman_jar}")
    byteman_home = run_dir / "byteman-home"
    lib_dir = byteman_home / "lib"
    lib_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(byteman_jar, lib_dir / "byteman.jar")
    return byteman_home


def _validate_config(config: StressRunConfig) -> None:
    if config.iterations < 1:
        raise ValueError("iterations must be >= 1")
    if config.concurrency_level < 1:
        raise ValueError("concurrency_level must be >= 1")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_jsonable(payload), indent=2, sort_keys=True), encoding="utf-8")


def _resolve_path(base_dir: Path, raw_path: str) -> Path:
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = (base_dir / candidate).resolve()
    return candidate


def _required_string(payload: dict, key: str, default: str | None = None) -> str:
    value = payload.get(key, default)
    if value is None:
        raise ValueError(f"Missing required scenario field: {key}")
    if not isinstance(value, str):
        raise ValueError(f"Scenario field `{key}` must be a string.")
    value = value.strip()
    if not value:
        raise ValueError(f"Scenario field `{key}` must not be empty.")
    return value


def _optional_string(payload: dict, key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"Scenario field `{key}` must be a string when set.")
    value = value.strip()
    return value or None


def _positive_int(value: object, key: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"Scenario field `{key}` must be an integer.")
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Scenario field `{key}` must be an integer.") from exc
    if parsed < 1:
        raise ValueError(f"Scenario field `{key}` must be >= 1.")
    return parsed


def _jsonable(value):
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, StressAggregateSummary):
        return _jsonable(asdict(value))
    if isinstance(value, StressIterationObservation):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value
