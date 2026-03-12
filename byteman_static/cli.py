from __future__ import annotations

import argparse
import sys
from pathlib import Path

from byteman_static.generator import GeneratorConfig, run_generator
from byteman_static.linux_integration import LinuxStartupConfig, write_linux_startup_script
from byteman_static.runtime_monitor import MonitorConfig, RuntimeLogMonitor
from byteman_static.stress_model import StressRunConfig
from byteman_static.stress_runner import execute_stress_run, load_stress_scenario


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="byteman-static-generator",
        description="Static Java scan + Byteman rule generation + runtime race-suspect watcher (Linux startup integration included).",
    )
    subparsers = parser.add_subparsers(dest="command")

    scan_parser = subparsers.add_parser("scan", help="Scan Java sources and generate inventory/rules.")
    _add_scan_arguments(scan_parser)

    watch_parser = subparsers.add_parser("watch", help="Tail Byteman runtime log and report race suspects.")
    _add_watch_arguments(watch_parser)

    linux_parser = subparsers.add_parser(
        "linux-startup", help="Generate Linux startup wrapper script for -javaagent Byteman launch."
    )
    _add_linux_arguments(linux_parser)

    stress_parser = subparsers.add_parser(
        "stress-run",
        help="Run jcstress-like repeated concurrency scenarios with Byteman and aggregate suspect outcomes.",
    )
    _add_stress_arguments(stress_parser)
    return parser


def main(argv: list[str] | None = None) -> int:
    args_list = list(argv) if argv is not None else sys.argv[1:]
    parser = build_argument_parser()

    # Backward compatibility: old usage had only scan options without a subcommand.
    if args_list and args_list[0].startswith("-") and args_list[0] not in {"-h", "--help"}:
        args_list = ["scan", *args_list]
    if not args_list:
        parser.print_help()
        return 2

    args = parser.parse_args(args_list)
    if args.command == "scan":
        return _run_scan(args)
    if args.command == "watch":
        return _run_watch(args)
    if args.command == "linux-startup":
        return _run_linux_startup(args)
    if args.command == "stress-run":
        return _run_stress(args)

    parser.print_help()
    return 2


def _add_scan_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--source-root", required=True, help="Java source root directory scanned recursively.")
    parser.add_argument("--output-dir", required=True, help="Directory where generated files are written.")
    parser.add_argument("--package-prefix", default=None, help="Optional base package prefix filter.")
    parser.add_argument("--package-regex", default=None, help="Optional package regex filter.")
    parser.add_argument(
        "--helper-class",
        default="com.example.byteman.RuntimeTraceHelper",
        help="Fully qualified Java helper class used by generated rules.",
    )
    parser.add_argument(
        "--inventory-log-path",
        default=None,
        help="Optional explicit output path for Byteman.log inventory.",
    )
    parser.add_argument(
        "--rules-file-path",
        default=None,
        help="Optional explicit output path for generated-rules.btm.",
    )
    parser.add_argument(
        "--runtime-log-path",
        default=None,
        help="Optional runtime log path used for Linux startup script generation and metadata.",
    )
    parser.add_argument("--no-metadata", action="store_true", help="Disable analysis metadata JSON output.")
    parser.add_argument(
        "--generate-linux-startup",
        default=None,
        help="Optional path to generate a Linux startup wrapper after scan.",
    )
    parser.add_argument(
        "--linux-java-command",
        default="java",
        help="Java command inserted into generated Linux startup script.",
    )


def _add_watch_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--log-file", required=True, help="Byteman runtime log file to monitor.")
    parser.add_argument(
        "--poll-interval-seconds",
        type=float,
        default=0.25,
        help="Polling interval when waiting for new log lines.",
    )
    parser.add_argument(
        "--from-start",
        action="store_true",
        help="Read from start of file instead of jumping to end at startup.",
    )
    parser.add_argument(
        "--no-follow",
        action="store_true",
        help="Read available lines once and exit (no continuous tail).",
    )
    parser.add_argument(
        "--stop-after-idle-seconds",
        type=float,
        default=None,
        help="Optional idle timeout. Useful for smoke tests.",
    )
    parser.add_argument(
        "--repeated-threshold",
        type=int,
        default=3,
        help="Overlap count threshold for REPEATED_RACE_SUSPECT.",
    )
    parser.add_argument(
        "--high-confidence-threshold",
        type=int,
        default=6,
        help="Overlap count threshold for HIGH_CONFIDENCE_SUSPECT.",
    )
    parser.add_argument(
        "--report-file",
        default=None,
        help="Optional JSONL report output file for raw events and suspect alerts.",
    )
    parser.add_argument("--emit-raw-events", action="store_true", help="Print parsed RAW_EVENT lines to stdout.")


def _add_linux_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output-script", required=True, help="Path for generated Linux startup script.")
    parser.add_argument("--rules-file", required=True, help="Path to generated .btm rules file.")
    parser.add_argument("--runtime-log-file", required=True, help="Path to runtime log file consumed by watcher.")
    parser.add_argument(
        "--java-command",
        default="java",
        help="Java command used by script (default: java).",
    )


def _add_stress_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--scenario-file", required=True, help="Path to stress scenario JSON file.")
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory for generated rules, compiled classes, per-iteration logs and summaries.",
    )
    parser.add_argument("--iterations", type=int, default=None, help="Override scenario default iteration count.")
    parser.add_argument(
        "--concurrency-level",
        type=int,
        default=None,
        help="Override scenario default concurrency level. Exported as STRESS_CONCURRENCY_LEVEL.",
    )
    parser.add_argument(
        "--byteman-jar",
        default=None,
        help="Optional explicit path to byteman.jar. Overrides scenario file value.",
    )
    parser.add_argument("--java-command", default="java", help="Java command used by generated launcher script.")
    parser.add_argument("--javac-command", default="javac", help="Javac command used to compile scenario sources.")
    parser.add_argument(
        "--watcher-poll-interval-seconds",
        type=float,
        default=0.25,
        help="Polling interval for the runtime watcher.",
    )
    parser.add_argument(
        "--watcher-idle-seconds",
        type=float,
        default=3.0,
        help="Idle timeout used to stop watcher per iteration.",
    )
    parser.add_argument(
        "--repeated-threshold",
        type=int,
        default=3,
        help="Threshold for repeated suspect classification in monitor and aggregation.",
    )
    parser.add_argument(
        "--high-confidence-threshold",
        type=int,
        default=6,
        help="Threshold for high-confidence suspect classification in monitor and aggregation.",
    )
    parser.add_argument(
        "--emit-raw-events",
        action="store_true",
        help="Emit parsed runtime RAW_EVENT lines while the stress runner is active.",
    )
    parser.add_argument("--fail-fast", action="store_true", help="Stop after the first failed iteration.")


def _run_scan(args: argparse.Namespace) -> int:
    config = GeneratorConfig(
        source_root=Path(args.source_root).resolve(),
        output_dir=Path(args.output_dir).resolve(),
        package_prefix=args.package_prefix,
        package_regex=args.package_regex,
        helper_class=args.helper_class,
        inventory_log_path=Path(args.inventory_log_path).resolve() if args.inventory_log_path else None,
        rules_file_path=Path(args.rules_file_path).resolve() if args.rules_file_path else None,
        runtime_log_path=Path(args.runtime_log_path).resolve() if args.runtime_log_path else None,
        write_metadata=not args.no_metadata,
    )

    try:
        result = run_generator(config)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"ERROR: generator failed: {exc}", file=sys.stderr)
        return 1

    print(f"Parser backend: {result.analysis.parser_backend}")
    print(f"Scanned files: {result.analysis.scanned_files}")
    print(f"Parsed files: {result.analysis.parsed_files}")
    print(f"Parse failures: {result.analysis.parse_failures}")
    print(f"Discovered types: {result.analysis.discovered_types}")
    print(f"Discovered methods: {result.analysis.discovered_methods}")
    print(f"Discovered fields: {result.analysis.discovered_fields}")
    print(f"Generated rules: {result.generated_rules}")
    print(f"Byteman.log: {result.byteman_log_path}")
    print(f"generated-rules.btm: {result.rules_path}")
    print(f"Runtime log path (for app/helper): {result.runtime_log_path}")
    if result.metadata_path:
        print(f"analysis-metadata.json: {result.metadata_path}")
    if result.analysis.limitations:
        print("Limitations:")
        for limitation in result.analysis.limitations:
            print(f"- {limitation}")

    if args.generate_linux_startup:
        script_path = write_linux_startup_script(
            LinuxStartupConfig(
                script_path=Path(args.generate_linux_startup).resolve(),
                rules_file=result.rules_path,
                runtime_log_file=result.runtime_log_path,
                java_command=args.linux_java_command,
            )
        )
        print(f"Linux startup script: {script_path}")
    return 0


def _run_watch(args: argparse.Namespace) -> int:
    monitor = RuntimeLogMonitor(
        MonitorConfig(
            log_file=Path(args.log_file).resolve(),
            follow=not args.no_follow,
            start_at_end=not args.from_start,
            poll_interval_seconds=args.poll_interval_seconds,
            repeated_threshold=args.repeated_threshold,
            high_confidence_threshold=args.high_confidence_threshold,
            report_file=Path(args.report_file).resolve() if args.report_file else None,
            emit_raw_events=args.emit_raw_events,
            stop_after_idle_seconds=args.stop_after_idle_seconds,
        )
    )
    stats = monitor.run()
    print("WATCH_SUMMARY")
    print(f"lines={stats.total_lines}")
    print(f"parsed_events={stats.parsed_events}")
    print(f"ignored_lines={stats.ignored_lines}")
    print(f"race_suspects={stats.race_suspects}")
    print(f"repeated_race_suspects={stats.repeated_suspects}")
    print(f"high_confidence_suspects={stats.high_confidence_suspects}")
    return 0


def _run_linux_startup(args: argparse.Namespace) -> int:
    script = write_linux_startup_script(
        LinuxStartupConfig(
            script_path=Path(args.output_script).resolve(),
            rules_file=Path(args.rules_file).resolve(),
            runtime_log_file=Path(args.runtime_log_file).resolve(),
            java_command=args.java_command,
        )
    )
    print(f"Linux startup script: {script}")
    return 0


def _run_stress(args: argparse.Namespace) -> int:
    scenario_file = Path(args.scenario_file).resolve()
    output_dir = Path(args.output_dir).resolve()
    try:
        scenario = load_stress_scenario(scenario_file)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    byteman_jar = Path(args.byteman_jar).resolve() if args.byteman_jar else scenario.byteman_jar
    if byteman_jar is None:
        print(
            "ERROR: byteman.jar path is required. Set `byteman_jar` in scenario or pass `--byteman-jar`.",
            file=sys.stderr,
        )
        return 2

    iterations = args.iterations if args.iterations is not None else scenario.default_iterations
    concurrency_level = (
        args.concurrency_level if args.concurrency_level is not None else scenario.default_concurrency_level
    )
    config = StressRunConfig(
        scenario=scenario,
        output_dir=output_dir,
        iterations=iterations,
        concurrency_level=concurrency_level,
        byteman_jar=Path(byteman_jar).resolve(),
        java_command=args.java_command,
        javac_command=args.javac_command,
        watcher_poll_interval_seconds=args.watcher_poll_interval_seconds,
        watcher_idle_seconds=args.watcher_idle_seconds,
        repeated_threshold=args.repeated_threshold,
        high_confidence_threshold=args.high_confidence_threshold,
        emit_raw_events=args.emit_raw_events,
        fail_fast=args.fail_fast,
    )

    try:
        result = execute_stress_run(config)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"ERROR: stress runner failed: {exc}", file=sys.stderr)
        return 1

    summary = result.summary
    print("STRESS_SUMMARY")
    print(f"scenario_id={summary.scenario_id}")
    print(f"outcome_level={summary.outcome_level}")
    print(f"total_iterations={summary.total_iterations}")
    print(f"successful_iterations={summary.successful_iterations}")
    print(f"failed_iterations={summary.failed_iterations}")
    print(f"iterations_with_suspect={summary.iterations_with_suspect}")
    print(f"iterations_without_suspect={summary.iterations_without_suspect}")
    print(f"total_raw_events={summary.total_raw_events}")
    print(f"suspects_by_level={summary.suspects_by_level}")
    print(f"rules_file={result.rules_file}")
    print(f"inventory_file={result.inventory_file}")
    print(f"startup_script={result.startup_script}")
    print(f"summary_file={result.summary_file}")
    print(f"results_file={result.results_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
