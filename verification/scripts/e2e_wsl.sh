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
if [[ ! -x "$JDK17_HOME/bin/java" || ! -f "$BYTEMAN_JAR" ]]; then
  echo "Missing JDK17 or Byteman jar in verification/tools." >&2
  exit 2
fi

export JAVA_HOME="$JDK17_HOME"
export PATH="$JAVA_HOME/bin:$PATH"

E2E_DIR="$REPO_ROOT/verification/artifacts/e2e"
SRC_DIR="$REPO_ROOT/verification/fixtures/e2e_java/src/main/java"
GEN_DIR="$E2E_DIR/generated"
CLASSES_DIR="$E2E_DIR/classes"
RUNTIME_DIR="$E2E_DIR/runtime"
RUNTIME_LOG="$RUNTIME_DIR/byteman-runtime.log"
RUN_SCRIPT="$E2E_DIR/run-with-byteman.sh"
WATCHER_STDOUT="$E2E_DIR/watcher-stdout.log"
WATCHER_REPORT="$E2E_DIR/watcher-report.jsonl"
APP_STDOUT="$E2E_DIR/app-stdout.log"
APP_STDERR="$E2E_DIR/app-stderr.log"
SCAN_STDOUT="$E2E_DIR/scan-stdout.log"
SCAN_STDERR="$E2E_DIR/scan-stderr.log"

rm -rf "$E2E_DIR"
mkdir -p "$GEN_DIR" "$CLASSES_DIR" "$RUNTIME_DIR"

python -m byteman_static.cli scan \
  --source-root "$SRC_DIR" \
  --output-dir "$GEN_DIR" \
  --package-prefix com.verifier.app \
  --helper-class com.example.byteman.RuntimeTraceHelper \
  --runtime-log-path "$RUNTIME_LOG" \
  --generate-linux-startup "$RUN_SCRIPT" \
  >"$SCAN_STDOUT" 2>"$SCAN_STDERR"

find "$SRC_DIR" -name '*.java' | sort > "$E2E_DIR/java-files.list"
javac -d "$CLASSES_DIR" @"$E2E_DIR/java-files.list"

BYTEMAN_HOME="$E2E_DIR/byteman-home"
mkdir -p "$BYTEMAN_HOME/lib"
cp "$BYTEMAN_JAR" "$BYTEMAN_HOME/lib/byteman.jar"

python -m byteman_static.cli watch \
  --log-file "$RUNTIME_LOG" \
  --from-start \
  --stop-after-idle-seconds 4 \
  --report-file "$WATCHER_REPORT" \
  >"$WATCHER_STDOUT" 2>&1 &
WATCHER_PID=$!

APP_CLASSPATH="$CLASSES_DIR" \
APP_MAIN_CLASS="com.verifier.app.Main" \
BYTEMAN_HOME="$BYTEMAN_HOME" \
BYTEMAN_VERBOSE="true" \
"$RUN_SCRIPT" >"$APP_STDOUT" 2>"$APP_STDERR"

wait "$WATCHER_PID"

RULE_FILE="$GEN_DIR/generated-rules.btm"
INV_FILE="$GEN_DIR/Byteman.log"

if [[ ! -s "$RULE_FILE" ]]; then
  echo "Generated rules missing or empty." >&2
  exit 3
fi
if [[ ! -s "$INV_FILE" ]]; then
  echo "Generated inventory missing or empty." >&2
  exit 3
fi
if [[ ! -s "$RUNTIME_LOG" ]]; then
  echo "Runtime log missing or empty." >&2
  exit 3
fi
if [[ ! -s "$WATCHER_REPORT" ]]; then
  echo "Watcher report missing or empty." >&2
  exit 3
fi
if ! grep -q "RACE_SUSPECT" "$WATCHER_STDOUT"; then
  echo "Watcher did not report any race suspect." >&2
  exit 3
fi
if ! grep -q "MAIN_DONE" "$APP_STDOUT"; then
  echo "Java app did not complete normally." >&2
  exit 3
fi
if ! grep -Eiq "byteman|BM_ENTRY|RULE" "$APP_STDERR" && ! grep -Eiq "byteman|BM_ENTRY|RULE" "$APP_STDOUT"; then
  echo "Byteman startup evidence not found in app output." >&2
  exit 3
fi

{
  echo "E2E_STATUS=PASS"
  echo "JAVA_VERSION=$("$JAVA_HOME/bin/java" -version 2>&1 | tr '\n' ';' | sed 's/;$/ /')"
  echo "SCANNED_RULES=$(grep -c '^RULE ' "$RULE_FILE")"
  echo "INVENTORY_LINES=$(wc -l < "$INV_FILE")"
  echo "RUNTIME_LINES=$(wc -l < "$RUNTIME_LOG")"
  echo "WATCHER_ALERTS=$(grep -E 'RACE_SUSPECT|REPEATED_RACE_SUSPECT|HIGH_CONFIDENCE_SUSPECT' -c "$WATCHER_STDOUT")"
} > "$E2E_DIR/e2e-summary.txt"

cat "$E2E_DIR/e2e-summary.txt"
