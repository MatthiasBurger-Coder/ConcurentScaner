from __future__ import annotations

from pathlib import Path

from byteman_static.cli import main as cli_main
from byteman_static.linux_integration import LinuxStartupConfig, write_linux_startup_script


REPO_ROOT = Path(__file__).resolve().parents[1]
STATIC_FIXTURE_ROOT = REPO_ROOT / "verification" / "fixtures" / "static_java" / "src" / "main" / "java"


def test_linux_startup_script_generation(tmp_path: Path) -> None:
    script_path = tmp_path / "run-with-byteman.sh"
    rules_file = tmp_path / "generated-rules.btm"
    runtime_log = tmp_path / "runtime.log"
    rules_file.write_text("# empty", encoding="utf-8")

    result_path = write_linux_startup_script(
        LinuxStartupConfig(
            script_path=script_path,
            rules_file=rules_file,
            runtime_log_file=runtime_log,
            java_command="java",
        )
    )
    assert result_path == script_path
    text = script_path.read_text(encoding="utf-8")
    assert "-javaagent:${BYTEMAN_AGENT_JAR}=script:${BYTEMAN_RULES_FILE},listener:true" in text
    assert "-Dorg.jboss.byteman.transform.all=true" in text
    assert "APP_JAR" in text
    assert "APP_CLASSPATH" in text
    assert "APP_MAIN_CLASS" in text


def test_cli_scan_command_generates_outputs(tmp_path: Path) -> None:
    output_dir = tmp_path / "scan_out"
    rc = cli_main(
        [
            "scan",
            "--source-root",
            str(STATIC_FIXTURE_ROOT),
            "--output-dir",
            str(output_dir),
            "--package-prefix",
            "com.verifier.app",
            "--runtime-log-path",
            str(output_dir / "Byteman.runtime.log"),
            "--no-metadata",
        ]
    )
    assert rc == 0
    assert (output_dir / "Byteman.log").exists()
    assert (output_dir / "generated-rules.btm").exists()


def test_cli_scan_missing_source_root_returns_nonzero(tmp_path: Path) -> None:
    output_dir = tmp_path / "scan_out"
    rc = cli_main(
        [
            "scan",
            "--source-root",
            str(tmp_path / "missing"),
            "--output-dir",
            str(output_dir),
        ]
    )
    assert rc == 2
