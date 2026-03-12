#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"
source .venv-wsl/bin/activate

export JAVA_HOME="$REPO_ROOT/verification/tools/jdk17"
export PATH="$JAVA_HOME/bin:$PATH"

NEG_DIR="$REPO_ROOT/verification/artifacts/negative"
mkdir -p "$NEG_DIR"
REPORT="$NEG_DIR/negative-scenarios.txt"
: > "$REPORT"

log_section() {
  printf '\n===== %s =====\n' "$1" | tee -a "$REPORT"
}

run_capture() {
  local label="$1"
  shift
  log_section "$label"
  {
    echo "COMMAND: $*"
    set +e
    "$@" >"$NEG_DIR/${label}.stdout.log" 2>"$NEG_DIR/${label}.stderr.log"
    rc=$?
    set -e
    echo "EXIT_CODE: $rc"
    echo "--- STDOUT ---"
    sed -n '1,120p' "$NEG_DIR/${label}.stdout.log"
    echo "--- STDERR ---"
    sed -n '1,120p' "$NEG_DIR/${label}.stderr.log"
  } | tee -a "$REPORT"
}

run_capture scan_missing_root \
  python -m byteman_static.cli scan --source-root "$NEG_DIR/does-not-exist" --output-dir "$NEG_DIR/out-missing"

run_capture scan_no_package_match \
  python -m byteman_static.cli scan --source-root "$REPO_ROOT/verification/fixtures/static_java/src/main/java" --package-prefix com.none --output-dir "$NEG_DIR/out-nomatch"

cat > "$NEG_DIR/malformed.log" <<'EOF'
this line is malformed
BTM_EVT ts=2026-03-12T20:00:00.100Z event=FIELD_BEFORE thread=t1 tid=1 class=c method=m field=v write=true
EOF
run_capture watch_malformed_log \
  python -m byteman_static.cli watch --log-file "$NEG_DIR/malformed.log" --no-follow --from-start

cat > "$NEG_DIR/read_read_only.log" <<'EOF'
BTM_EVT ts=2026-03-12T20:00:00.100Z event=FIELD_BEFORE thread=r1 tid=1 class=c method=read field=v write=false
BTM_EVT ts=2026-03-12T20:00:00.101Z event=FIELD_BEFORE thread=r2 tid=2 class=c method=read field=v write=false
BTM_EVT ts=2026-03-12T20:00:00.102Z event=FIELD_AFTER thread=r1 tid=1 class=c method=read field=v write=false
BTM_EVT ts=2026-03-12T20:00:00.103Z event=FIELD_AFTER thread=r2 tid=2 class=c method=read field=v write=false
EOF
run_capture watch_read_read_only \
  python -m byteman_static.cli watch --log-file "$NEG_DIR/read_read_only.log" --no-follow --from-start

cat > "$NEG_DIR/single_thread.log" <<'EOF'
BTM_EVT ts=2026-03-12T20:00:00.100Z event=FIELD_BEFORE thread=t1 tid=1 class=c method=write field=v write=true
BTM_EVT ts=2026-03-12T20:00:00.101Z event=FIELD_AFTER thread=t1 tid=1 class=c method=write field=v write=true
BTM_EVT ts=2026-03-12T20:00:00.102Z event=FIELD_BEFORE thread=t1 tid=1 class=c method=read field=v write=false
BTM_EVT ts=2026-03-12T20:00:00.103Z event=FIELD_AFTER thread=t1 tid=1 class=c method=read field=v write=false
EOF
run_capture watch_single_thread \
  python -m byteman_static.cli watch --log-file "$NEG_DIR/single_thread.log" --no-follow --from-start

cat > "$NEG_DIR/duplicate_partial.log" <<'EOF'
BTM_EVT ts=2026-03-12T20:00:00.100Z event=FIELD_BEFORE thread=t1 tid=1 class=c method=write field=v write=true
BTM_EVT ts=2026-03-12T20:00:00.101Z event=FIELD_BEFORE thread=t2 tid=2 class=c method=read field=v write=false
BTM_EVT ts=2026-03-12T20:00:00.101Z event=FIELD_BEFORE thread=t2 tid=2 class=c method=read field=v write=false
partial garbage
BTM_EVT ts=2026-03-12T20:00:00.120Z event=FIELD_AFTER thread=t2 tid=2 class=c method=read field=v write=false
EOF
run_capture watch_duplicate_partial \
  python -m byteman_static.cli watch --log-file "$NEG_DIR/duplicate_partial.log" --no-follow --from-start

E2E_DIR="$REPO_ROOT/verification/artifacts/e2e"
if [[ -f "$E2E_DIR/run-with-byteman.sh" ]]; then
  run_capture startup_missing_rules \
    env APP_CLASSPATH="$E2E_DIR/classes" \
      APP_MAIN_CLASS="com.verifier.app.Main" \
      BYTEMAN_HOME="$E2E_DIR/byteman-home" \
      BYTEMAN_RULES_FILE="$NEG_DIR/missing-rules-file.btm" \
      "$E2E_DIR/run-with-byteman.sh"
fi

echo "NEGATIVE_SCENARIOS_DONE" | tee -a "$REPORT"
