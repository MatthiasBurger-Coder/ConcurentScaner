#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

if [[ ! -d ".venv-wsl" ]]; then
  echo "Missing .venv-wsl. Run WSL setup first." >&2
  exit 2
fi

source .venv-wsl/bin/activate

JDK17_HOME="$REPO_ROOT/verification/tools/jdk17"
BYTEMAN_JAR="$REPO_ROOT/verification/tools/byteman/byteman.jar"
if [[ ! -x "$JDK17_HOME/bin/java" || ! -x "$JDK17_HOME/bin/javac" || ! -f "$BYTEMAN_JAR" ]]; then
  echo "Missing JDK17 or byteman.jar under verification/tools." >&2
  exit 2
fi

export JAVA_HOME="$JDK17_HOME"
export PATH="$JAVA_HOME/bin:$PATH"

STRESS_DIR="$REPO_ROOT/verification/artifacts/stress"
SCENARIO_FILE="$REPO_ROOT/verification/fixtures/stress_scenarios/shared_counter_stress.json"
STDOUT_LOG="$STRESS_DIR/stress-stdout.log"
STDERR_LOG="$STRESS_DIR/stress-stderr.log"
SUMMARY_JSON="$STRESS_DIR/stress-summary.json"
RESULTS_JSON="$STRESS_DIR/stress-results.json"

rm -rf "$STRESS_DIR"
mkdir -p "$STRESS_DIR"

python -m byteman_static.cli stress-run \
  --scenario-file "$SCENARIO_FILE" \
  --output-dir "$STRESS_DIR" \
  --iterations 5 \
  --concurrency-level 4 \
  --byteman-jar "$BYTEMAN_JAR" \
  --java-command "$JAVA_HOME/bin/java" \
  --javac-command "$JAVA_HOME/bin/javac" \
  --watcher-idle-seconds 4 \
  --repeated-threshold 3 \
  --high-confidence-threshold 6 \
  >"$STDOUT_LOG" 2>"$STDERR_LOG"

if [[ ! -s "$SUMMARY_JSON" || ! -s "$RESULTS_JSON" ]]; then
  echo "Stress summary artifacts are missing." >&2
  exit 3
fi

python - <<'PY'
import json
from pathlib import Path

summary = json.loads(Path("verification/artifacts/stress/stress-summary.json").read_text(encoding="utf-8"))
if summary.get("total_iterations", 0) < 1:
    raise SystemExit("total_iterations must be >= 1")
if summary.get("successful_iterations", 0) < 1:
    raise SystemExit("No successful iteration recorded")
if summary.get("iterations_with_suspect", 0) < 1:
    raise SystemExit("Expected at least one suspicious iteration")
print("STRESS_E2E_STATUS=PASS")
print(f"OUTCOME_LEVEL={summary.get('outcome_level')}")
print(f"ITERATIONS={summary.get('total_iterations')}")
print(f"ITER_WITH_SUSPECT={summary.get('iterations_with_suspect')}")
print(f"SUSPECTS={summary.get('suspects_by_level')}")
PY
