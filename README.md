# ConcurrentScanner Byteman Toolchain

Static Java analysis + Byteman rule generation + runtime log monitoring for concurrency stress experiments.

This project is **jcstress-like** in workflow (repeat runs, observe overlaps, aggregate suspicion), but it is **not** a formal jcstress replacement and does not provide proof-level memory model guarantees.

## What The System Does

1. Scans Java source trees and extracts types, fields, methods, and field-usage hints.
2. Generates deterministic outputs:
   - `Byteman.log` inventory
   - `generated-rules.btm` rules
   - optional `analysis-metadata.json`
3. Generates a Linux startup wrapper that injects `-javaagent`.
4. Watches runtime `BTM_EVT` logs and emits suspect classifications.
5. Runs scenario-driven stress iterations and writes aggregated JSON summaries.

## High-Level Architecture

- `byteman_static/parser.py`
  Java parsing with `tree-sitter-java`, with regex fallback if AST parser is unavailable.
- `byteman_static/generator.py`
  Orchestrates source analysis and output generation.
- `byteman_static/inventory.py`
  Renders `Byteman.log`.
- `byteman_static/rules.py`
  Renders deterministic `.btm` rules.
- `byteman_static/linux_integration.py`
  Generates Linux/Bash startup script for Byteman agent launch.
- `byteman_static/runtime_parser.py`
  Parses runtime lines (`BTM_EVT ...` and JSON lines).
- `byteman_static/runtime_monitor.py`
  Tails runtime logs and detects overlapping write/read access patterns.
- `byteman_static/stress_runner.py`
  Compiles Java sources, runs iterations, launches watcher, writes stress results.
- `byteman_static/stress_report.py`
  Summarizes iteration JSONL reports and computes run outcome level.
- `byteman_static/cli.py`
  CLI entrypoint (`scan`, `watch`, `linux-startup`, `stress-run`).

## Repository Structure

```text
byteman_static/                  # core Python implementation
tests/                           # pytest suite
verification/
  fixtures/                      # Java and scenario fixtures
  scripts/                       # WSL/Linux E2E scripts
  reports/                       # verification reports and coverage artifacts
  tools/                         # optional local JDK17 + byteman.jar (gitignored, may be missing in fresh clone)
README.md
requirements.txt
```

## User Manual / How-To (Start Here)

This section is the practical onboarding guide. If you are new to this repository, start here.

### Who This Is For

- Junior developers who want a copy-paste path to first successful run.
- Maintainers who need to know which files, env vars, and commands are required.
- Users who want to run scan, watcher, and stress workflow manually or by script.

### What You Need Before Running

Required:

- Python 3.12+ recommended
- `pip`
- Java runtime + compiler (`java` + `javac`)
- Byteman agent jar (`byteman.jar`)
- Linux/Bash runtime for launcher execution (`run-with-byteman.sh`) and WSL scripts

Optional (documentation preview/export only):

- AsciiDoc tooling / PyCharm AsciiDoc plugin
- PlantUML renderer (local or Kroki)

Python packages from this repo:

- `tree-sitter>=0.21.3`
- `tree-sitter-java>=0.23.5`

Test/coverage tooling (optional but recommended):

- `pytest`
- `pytest-cov`

### Tooling Paths: Choose One Setup Mode

Mode A (repository-local tools, easiest if present):

- Uses:
  - `verification/tools/jdk17/bin/java`
  - `verification/tools/jdk17/bin/javac`
  - `verification/tools/byteman/byteman.jar`
- This is what `verification/scripts/*.sh` expect.

Mode B (your own installed tools, works in fresh clone without local tools):

- Use your own `java`, `javac`, and `byteman.jar`.
- Pass explicit paths via CLI flags:
  - `--java-command`
  - `--javac-command`
  - `--byteman-jar`

Important:

- `verification/tools/` is gitignored by this repository, so it may not exist in a fresh clone.

### Quick Start (Shortest Path to First Success)

If `verification/tools/` exists and you are in WSL/Linux:

```bash
source .venv-wsl/bin/activate
bash verification/scripts/stress_e2e_wsl.sh
cat verification/artifacts/stress/stress-summary.json
```

Success indicators:

- Script prints `STRESS_E2E_STATUS=PASS`
- `verification/artifacts/stress/stress-summary.json` exists and is non-empty

### Full Start Guide (Beginner, Step by Step)

The commands below are written for Linux/WSL shell.

1. Create and activate Python environment

```bash
cd /mnt/d/Projects/ConcurentScaner
python3 -m venv .venv-wsl
source .venv-wsl/bin/activate
pip install -r requirements.txt
pip install pytest pytest-cov
```

2. Verify tools

```bash
python --version
java -version
javac -version
```

3. Run static scan + rule generation

```bash
python -m byteman_static.cli scan \
  --source-root verification/fixtures/e2e_java/src/main/java \
  --output-dir verification/artifacts/manual_scan \
  --package-prefix com.verifier.app \
  --runtime-log-path verification/artifacts/manual_scan/runtime/byteman-runtime.log \
  --generate-linux-startup verification/artifacts/manual_scan/run-with-byteman.sh
```

Expected output includes:

- `Parser backend: ...`
- `Generated rules: ...`
- `Byteman.log: ...`
- `generated-rules.btm: ...`

4. Compile Java fixture sources

```bash
SRC_DIR="verification/fixtures/e2e_java/src/main/java"
CLASSES_DIR="verification/artifacts/manual_scan/classes"
mkdir -p "$CLASSES_DIR"
find "$SRC_DIR" -name '*.java' | sort > verification/artifacts/manual_scan/java-files.list
javac -d "$CLASSES_DIR" @verification/artifacts/manual_scan/java-files.list
```

5. Prepare mandatory `BYTEMAN_HOME` and run app with launcher

```bash
BYTEMAN_JAR="verification/tools/byteman/byteman.jar"  # or /absolute/path/to/byteman.jar
mkdir -p verification/artifacts/manual_scan/byteman-home/lib
cp "$BYTEMAN_JAR" verification/artifacts/manual_scan/byteman-home/lib/byteman.jar

export BYTEMAN_HOME="$PWD/verification/artifacts/manual_scan/byteman-home"
export APP_CLASSPATH="$PWD/$CLASSES_DIR"
export APP_MAIN_CLASS="com.verifier.app.Main"
./verification/artifacts/manual_scan/run-with-byteman.sh
```

6. Watch and analyze runtime log

```bash
python -m byteman_static.cli watch \
  --log-file verification/artifacts/manual_scan/runtime/byteman-runtime.log \
  --from-start \
  --report-file verification/artifacts/manual_scan/watcher-report.jsonl \
  --stop-after-idle-seconds 5
```

Expected output includes:

- one or more suspect lines (for overlap cases), for example `RACE_SUSPECT ...`
- final `WATCH_SUMMARY`

7. Run full stress workflow (manual)

```bash
JAVA_CMD="verification/tools/jdk17/bin/java"      # or /usr/bin/java
JAVAC_CMD="verification/tools/jdk17/bin/javac"    # or /usr/bin/javac
BYTEMAN_JAR="verification/tools/byteman/byteman.jar"  # or /absolute/path/to/byteman.jar

python -m byteman_static.cli stress-run \
  --scenario-file verification/fixtures/stress_scenarios/shared_counter_stress.json \
  --output-dir verification/artifacts/stress \
  --byteman-jar "$BYTEMAN_JAR" \
  --java-command "$JAVA_CMD" \
  --javac-command "$JAVAC_CMD" \
  --iterations 5 \
  --concurrency-level 4
```

Expected output starts with `STRESS_SUMMARY`.

### Environment Variables (Complete Runtime List)

The project does not use a `.env` file loader. Variables are read from process environment (shell exports / inline env).

| Variable | Required? | Default | What it controls | Read in code | Missing behavior / fallback | Example |
|---|---|---|---|---|---|---|
| `BYTEMAN_HOME` | Yes for launcher script | none | Base dir for default agent jar path (`lib/byteman.jar`) | generated script from `byteman_static/linux_integration.py` | launcher exits with code `2` and message `Missing BYTEMAN_HOME...` | `/opt/byteman` |
| `BYTEMAN_AGENT_JAR` | Optional | `${BYTEMAN_HOME}/lib/byteman.jar` | Explicit agent jar path used in `-javaagent` | generated launcher script | falls back to default path under `BYTEMAN_HOME` | `/opt/byteman/lib/byteman.jar` |
| `BYTEMAN_RULES_FILE` | Optional | embedded script default (`--rules-file`/generated path) | Rule file path passed to javaagent | generated launcher script | falls back to script default path | `/tmp/generated-rules.btm` |
| `BYTEMAN_RUNTIME_LOG` | Optional | embedded script default (`--runtime-log-file`/generated path) | Runtime log target via `-Dbyteman.runtime.log` | generated launcher script; helper reads Java property in `RuntimeTraceHelper` | falls back to script default path; helper itself defaults to `Byteman.runtime.log` if JVM property absent | `/tmp/byteman-runtime.log` |
| `BYTEMAN_VERBOSE` | Optional | `true` | Sets `-Dorg.jboss.byteman.verbose` | generated launcher script | default `true` | `false` |
| `JAVA_CMD` | Optional | script generation default (`java` unless overridden) | Java executable used by launcher | generated launcher script | falls back to generated command | `/usr/bin/java` |
| `JAVA_OPTS` | Optional | empty | Extra JVM args appended by launcher | generated launcher script | no extra options if unset | `-Xmx512m` |
| `APP_JAR` | Conditional (one startup mode) | none | Jar launch mode (`java -jar`) | generated launcher script | if not set, must use classpath mode | `/path/app.jar` |
| `APP_CLASSPATH` | Conditional (with `APP_MAIN_CLASS`) | none | Classpath launch mode | generated launcher script; set by stress runner | if either missing, launcher exits with code `2` | `/tmp/classes` |
| `APP_MAIN_CLASS` | Conditional (with `APP_CLASSPATH`) | none | Main class for classpath launch | generated launcher script; set by stress runner | if either missing, launcher exits with code `2` | `com.verifier.app.Main` |
| `STRESS_ITERATION` | Auto-set by stress runner | none | Current iteration index for app-side logic/diagnostics | set in `byteman_static/stress_runner.py` | not required for manual non-stress launch | `1` |
| `STRESS_CONCURRENCY_LEVEL` | Auto-set by stress runner; optional for manual app launch | app default `2` in fixture `Main.java` | Worker thread fan-out in fixture app | set in stress runner; read by fixture `Main.java` | fixture app uses default `2` if unset/invalid | `4` |
| `STRESS_OPS_PER_THREAD` | Optional | app default `20` in fixture `Main.java` | Operations per worker thread in fixture app | fixture `Main.java` | uses default `20` if unset/invalid | `24` |
| `STRESS_PAUSE_MS` | Optional | app default `25` in fixture `Main.java` | Pause duration to encourage overlap in fixture app | fixture `Main.java` | uses default `25` if unset/invalid | `20` |
| `JAVA_HOME` | Optional for CLI; required by provided WSL scripts | none | Tool path selection in scripts | `verification/scripts/*.sh` | scripts fail if required binaries unavailable | `$REPO_ROOT/verification/tools/jdk17` |
| `PATH` | Environment standard; required by scripts/tool lookup | shell default | Resolves `python`, `java`, `javac`, etc. | scripts and shell command resolution | command-not-found failures | `$JAVA_HOME/bin:$PATH` |

### Configuration Files and Settings

| File | Required? | Purpose | Notes |
|---|---|---|---|
| `requirements.txt` | Yes | Python parser dependencies | install via `pip install -r requirements.txt` |
| `verification/fixtures/stress_scenarios/shared_counter_stress.json` | Optional (required for stress scenario example) | Scenario defaults and env for `stress-run` | can be replaced by your own scenario JSON |
| `.venv-wsl/` | Optional but recommended | Isolated Python env used by scripts | scripts expect it by default |
| `.env` | Not used | - | no `.env` loader in implementation |

Startup-ready minimum for `stress-run`:

- valid scenario JSON (`--scenario-file`)
- writable output dir (`--output-dir`)
- valid `byteman.jar` path (CLI flag or scenario field)
- working `java` + `javac` commands

### CLI Commands at a Glance (Startup-Relevant)

| Command | Use case | Minimum required arguments | Success indicator |
|---|---|---|---|
| `python -m byteman_static.cli scan` | Generate inventory + rules from Java sources | `--source-root`, `--output-dir` | prints `Byteman.log:` and `generated-rules.btm:` |
| `python -m byteman_static.cli watch` | Parse runtime log and emit suspect summary | `--log-file` | prints `WATCH_SUMMARY` |
| `python -m byteman_static.cli linux-startup` | Generate launcher script only | `--output-script`, `--rules-file`, `--runtime-log-file` | prints `Linux startup script:` |
| `python -m byteman_static.cli stress-run` | Full compile + run + monitor + aggregate flow | `--scenario-file`, `--output-dir` (+ resolved byteman jar source) | prints `STRESS_SUMMARY` |

### Run Tests and Coverage

```bash
python -m pytest -q
```

```bash
python -m pytest --cov=byteman_static \
  --cov-report=term-missing \
  --cov-report=xml:verification/reports/coverage.xml \
  --cov-report=html:verification/reports/coverage_html -q
```

If `python -m pytest` fails with `No module named pytest`, install:

```bash
python -m pip install pytest pytest-cov
```

### Important Paths and Outputs

| Path | Meaning |
|---|---|
| `verification/fixtures/e2e_java/src/main/java` | Example Java app + runtime helper |
| `verification/fixtures/static_java/src/main/java` | Static scan fixture set |
| `verification/fixtures/stress_scenarios/*.json` | Stress scenario examples |
| `verification/scripts/` | End-to-end and negative verification scripts |
| `verification/artifacts/e2e/` | Baseline e2e outputs |
| `verification/artifacts/negative/` | Negative scenario logs |
| `verification/artifacts/stress/` | Stress run outputs (`stress-summary.json`, `stress-results.json`) |

How to know the system is working:

- `scan` prints generated file paths and non-zero discovered counts.
- `watch` prints `WATCH_SUMMARY`.
- `stress-run` prints `STRESS_SUMMARY`.
- `verification/scripts/e2e_wsl.sh` ends with `E2E_STATUS=PASS`.
- `verification/scripts/stress_e2e_wsl.sh` prints `STRESS_E2E_STATUS=PASS`.

## Requirements And Setup

### Runtime Requirements

- Python 3.12+ recommended
- Java + javac (JDK 17 used in verification scripts)
- Byteman agent jar (`byteman.jar`) for launcher/stress flows
- Linux/Bash runtime required for executing generated startup script and stress E2E scripts

Notes:
- `scan` and `watch` commands are pure Python and can run outside WSL if dependencies are available.
- `linux-startup` only generates a script; the script itself is Linux/Bash.
- `stress-run` executes that Linux startup script.

### Python Dependencies

`requirements.txt` currently contains:

- `tree-sitter>=0.21.3`
- `tree-sitter-java>=0.23.5`

Install:

```bash
python -m pip install -r requirements.txt
python -m pip install pytest pytest-cov
```

### WSL-Oriented Setup Example

```bash
cd /mnt/d/Projects/ConcurentScaner
python3 -m venv .venv-wsl
source .venv-wsl/bin/activate
pip install -r requirements.txt
pip install pytest pytest-cov
```

## CLI Usage

Entry command:

```bash
python -m byteman_static.cli <subcommand> [options]
```

Subcommands:

- `scan`
- `watch`
- `linux-startup`
- `stress-run`

Compatibility behavior:

- If options are passed without a subcommand (for example `--source-root ...`), CLI treats it as `scan`.

## Command Reference

### `scan`

Scans Java sources and writes inventory/rules (and metadata unless disabled).

```bash
python -m byteman_static.cli scan \
  --source-root verification/fixtures/e2e_java/src/main/java \
  --output-dir verification/artifacts/manual_scan \
  --package-prefix com.verifier.app \
  --runtime-log-path verification/artifacts/manual_scan/runtime/byteman-runtime.log \
  --generate-linux-startup verification/artifacts/manual_scan/run-with-byteman.sh
```

| Flag | Required | Default | Description |
|---|---|---|---|
| `--source-root` | Yes | - | Java source root scanned recursively (`*.java`). |
| `--output-dir` | Yes | - | Output directory for generated files. |
| `--package-prefix` | No | `None` | Package prefix filter (exact or child package). |
| `--package-regex` | No | `None` | Regex package filter (applied with prefix filter if both set). |
| `--helper-class` | No | `com.example.byteman.RuntimeTraceHelper` | Helper class called from generated rules. |
| `--inventory-log-path` | No | `<output-dir>/Byteman.log` | Custom inventory path. |
| `--rules-file-path` | No | `<output-dir>/generated-rules.btm` | Custom rules path. |
| `--runtime-log-path` | No | `<output-dir>/Byteman.runtime.log` | Runtime log path written into metadata and launcher defaults. |
| `--no-metadata` | No | `false` | Disable `analysis-metadata.json`. |
| `--generate-linux-startup` | No | `None` | Also generate Linux startup script at this path. |
| `--linux-java-command` | No | `java` | Java command inserted in generated script. |

Primary outputs:

- `Byteman.log`
- `generated-rules.btm`
- optional `analysis-metadata.json`
- optional Linux launcher script

### `watch`

Tails runtime log and emits suspect alerts plus optional JSONL report.

```bash
python -m byteman_static.cli watch \
  --log-file verification/artifacts/e2e/runtime/byteman-runtime.log \
  --from-start \
  --report-file verification/artifacts/e2e/watcher-report.jsonl \
  --stop-after-idle-seconds 5
```

| Flag | Required | Default | Description |
|---|---|---|---|
| `--log-file` | Yes | - | Runtime log file to read. |
| `--poll-interval-seconds` | No | `0.25` | Poll interval while waiting for new lines. |
| `--from-start` | No | `false` | Read from beginning of file instead of seeking to end on first open. |
| `--no-follow` | No | `false` | Process available lines once and exit. |
| `--stop-after-idle-seconds` | No | `None` | Stop when no new lines arrive for this duration. |
| `--repeated-threshold` | No | `3` | Overlap count threshold for `REPEATED_RACE_SUSPECT`. |
| `--high-confidence-threshold` | No | `6` | Overlap count threshold for `HIGH_CONFIDENCE_SUSPECT`. |
| `--report-file` | No | `None` | JSONL output path (append mode). |
| `--emit-raw-events` | No | `false` | Print parsed raw events to stdout. |

Threshold behavior:

- Internal monitor clamps `repeated-threshold` to at least `1`.
- Internal monitor clamps `high-confidence-threshold` to at least repeated threshold.

Summary output format:

```text
WATCH_SUMMARY
lines=...
parsed_events=...
ignored_lines=...
race_suspects=...
repeated_race_suspects=...
high_confidence_suspects=...
```

### `linux-startup`

Generates Linux/Bash wrapper that launches Java with Byteman `-javaagent`.

```bash
python -m byteman_static.cli linux-startup \
  --output-script verification/artifacts/manual_scan/run-with-byteman.sh \
  --rules-file verification/artifacts/manual_scan/generated-rules.btm \
  --runtime-log-file verification/artifacts/manual_scan/runtime/byteman-runtime.log
```

| Flag | Required | Default | Description |
|---|---|---|---|
| `--output-script` | Yes | - | Path to generated shell script. |
| `--rules-file` | Yes | - | `.btm` file path used by agent. |
| `--runtime-log-file` | Yes | - | Runtime log file path passed as `-Dbyteman.runtime.log`. |
| `--java-command` | No | `java` | Default Java command used by script (`JAVA_CMD` can override at runtime). |

The script injects:

- `-javaagent:${BYTEMAN_AGENT_JAR}=script:${BYTEMAN_RULES_FILE},listener:true`
- `-Dorg.jboss.byteman.verbose=${BYTEMAN_VERBOSE}`
- `-Dorg.jboss.byteman.transform.all=true`
- `-Dbyteman.runtime.log=${BYTEMAN_RUNTIME_LOG}`

Important:

- Running `run-with-byteman.sh` without `BYTEMAN_HOME` fails immediately with:
  `Missing BYTEMAN_HOME. Set it to your Byteman installation path.`
- In the current script implementation, `BYTEMAN_HOME` is mandatory even if `BYTEMAN_AGENT_JAR` is set.

Script environment variables:

| Variable | Required | Description |
|---|---|---|
| `BYTEMAN_HOME` | Yes | Must contain `lib/byteman.jar` unless `BYTEMAN_AGENT_JAR` is set. |
| `APP_JAR` | One launch mode | If set, script runs `java -jar "$APP_JAR"`. |
| `APP_CLASSPATH` + `APP_MAIN_CLASS` | One launch mode | If both set, script runs classpath launch. |
| `BYTEMAN_AGENT_JAR` | No | Explicit agent jar path override. |
| `BYTEMAN_RULES_FILE` | No | Override rules path (defaults to generation-time value). |
| `BYTEMAN_RUNTIME_LOG` | No | Override runtime log path (defaults to generation-time value). |
| `BYTEMAN_VERBOSE` | No | Defaults to `true`. |
| `JAVA_CMD` | No | Overrides Java command from script template. |
| `JAVA_OPTS` | No | Extra JVM options string. |

Minimal manual run example:

```bash
SRC_DIR="verification/fixtures/e2e_java/src/main/java"
CLASSES_DIR="verification/artifacts/manual_scan/classes"
mkdir -p "$CLASSES_DIR"
find "$SRC_DIR" -name '*.java' | sort > verification/artifacts/manual_scan/java-files.list
javac -d "$CLASSES_DIR" @verification/artifacts/manual_scan/java-files.list

mkdir -p .byteman-home/lib
cp verification/tools/byteman/byteman.jar .byteman-home/lib/byteman.jar

export BYTEMAN_HOME="$PWD/.byteman-home"
export APP_CLASSPATH="$PWD/$CLASSES_DIR"
export APP_MAIN_CLASS="com.verifier.app.Main"
./verification/artifacts/manual_scan/run-with-byteman.sh
```

### `stress-run`

Runs repeated scenario-based stress iterations:

- compiles scenario Java sources
- generates rules/inventory
- generates launcher script
- executes app per iteration
- runs runtime watcher per iteration
- writes aggregate JSON summary

```bash
python -m byteman_static.cli stress-run \
  --scenario-file verification/fixtures/stress_scenarios/shared_counter_stress.json \
  --output-dir verification/artifacts/stress \
  --byteman-jar verification/tools/byteman/byteman.jar \
  --java-command verification/tools/jdk17/bin/java \
  --javac-command verification/tools/jdk17/bin/javac \
  --iterations 5 \
  --concurrency-level 4
```

| Flag | Required | Default | Description |
|---|---|---|---|
| `--scenario-file` | Yes | - | Stress scenario JSON file. |
| `--output-dir` | Yes | - | Run output directory (compiled classes, logs, summaries). |
| `--iterations` | No | Scenario `default_iterations` | Iteration count override. |
| `--concurrency-level` | No | Scenario `default_concurrency_level` | Concurrency override; exported as `STRESS_CONCURRENCY_LEVEL`. |
| `--byteman-jar` | No | Scenario `byteman_jar` | Explicit byteman jar path; required by final resolved config. |
| `--java-command` | No | `java` | Java command used by generated launcher. |
| `--javac-command` | No | `javac` | Javac command used for source compilation. |
| `--watcher-poll-interval-seconds` | No | `0.25` | Watcher polling interval per iteration. |
| `--watcher-idle-seconds` | No | `3.0` | Watcher idle timeout per iteration. |
| `--repeated-threshold` | No | `3` | Repeated suspect threshold in monitor and aggregate classifier. |
| `--high-confidence-threshold` | No | `6` | High-confidence threshold in monitor and aggregate classifier. |
| `--emit-raw-events` | No | `false` | Emit parsed raw events while stress run executes. |
| `--fail-fast` | No | `false` | Stop after first failed iteration. |

Per-iteration process environment injected by stress runner:

| Variable | Source | Description |
|---|---|---|
| `APP_CLASSPATH` | Runner | Set to `<output-dir>/classes`. |
| `APP_MAIN_CLASS` | Scenario `main_class` | Main class executed by launcher script. |
| `BYTEMAN_HOME` | Runner | Set to `<output-dir>/byteman-home` (contains copied jar). |
| `BYTEMAN_RULES_FILE` | Runner | Set to generated rules path. |
| `BYTEMAN_RUNTIME_LOG` | Runner | Set to iteration runtime log path. |
| `STRESS_ITERATION` | Runner | Current iteration number (1-based). |
| `STRESS_CONCURRENCY_LEVEL` | CLI/scenario resolved value | Concurrency level for app side tuning. |
| additional keys from scenario `env` | Scenario JSON | Merged into environment before fixed keys above are applied. |

Error behavior:

- Missing scenario file or invalid scenario JSON: CLI returns exit code `2`.
- Missing resolved `byteman.jar`: CLI returns exit code `2`.
- Other stress runner exceptions: CLI returns exit code `1`.

### Stress Scenario File (`--scenario-file`)

Scenario JSON may be either:

- direct object with fields below, or
- `{ "scenario": { ... } }`

Relative paths are resolved relative to the scenario file directory.

Example fixture: `verification/fixtures/stress_scenarios/shared_counter_stress.json`

| Field | Required | Default | Description |
|---|---|---|---|
| `scenario_id` | No | Scenario filename stem | Scenario identifier for reports. |
| `source_root` | Yes | - | Java source root used for compile + static scan. |
| `main_class` | Yes | - | Java main class to execute. |
| `description` | No | `None` | Free-text scenario description. |
| `package_prefix` | No | `None` | Scan filter prefix. |
| `package_regex` | No | `None` | Scan filter regex. |
| `helper_class` | No | `com.example.byteman.RuntimeTraceHelper` | Helper class used in generated rules. |
| `java_sources_glob` | No | `**/*.java` | Glob under `source_root` used for compilation. |
| `app_args` | No | `[]` | Extra CLI args passed to the launched Java app. |
| `env` | No | `{}` | Environment variables merged into app process env. |
| `default_iterations` | No | `10` | Positive integer default for iterations. |
| `default_concurrency_level` | No | `2` | Positive integer default for concurrency level. |
| `byteman_jar` | No | `None` | Optional jar path if not passed by CLI flag. |

### Runtime Event Format

`watch` accepts:

- key/value lines starting with `BTM_EVT `
- JSON object lines

Recognized event aliases map to:

- `METHOD_ENTER`: `METHOD_ENTER`, `ENTER`
- `METHOD_EXIT`: `METHOD_EXIT`, `EXIT`
- `FIELD_BEFORE`: `FIELD_BEFORE`, `BEFORE_FIELD_ACCESS`, `FIELD_ACCESS_BEGIN`
- `FIELD_AFTER`: `FIELD_AFTER`, `AFTER_FIELD_ACCESS`, `FIELD_ACCESS_END`
- `DEADLOCK_CHECK`: `DEADLOCK_CHECK`, `CHECK_DEADLOCK`

Timestamp parsing supports:

- ISO timestamps (including `...Z`)
- epoch seconds
- epoch milliseconds

## Outputs And Artifacts

### Scan Outputs

Default files in `--output-dir`:

- `Byteman.log`
- `generated-rules.btm`
- `analysis-metadata.json` (unless `--no-metadata`)
- default runtime log path for launcher metadata: `Byteman.runtime.log`

### Watch Outputs

- stdout suspect lines (for example `RACE_SUSPECT class=... field=...`)
- final `WATCH_SUMMARY`
- optional JSONL report (`record_type` = `RAW_EVENT` or suspect levels)

### Stress-Run Outputs

Inside `--output-dir`:

- `generated/`
  - `Byteman.log`
  - `generated-rules.btm`
  - `Byteman.runtime.log` (generation-time runtime path)
- `classes/` compiled `.class` files
- `run-with-byteman.sh`
- `byteman-home/lib/byteman.jar` (copied from provided jar)
- `java-files.list` (javac argument file)
- `compile-stdout.log`, `compile-stderr.log`
- `runs/iteration-0001/` (per iteration)
  - `runtime/byteman-runtime.log`
  - `watcher-report.jsonl`
  - `app-stdout.log`, `app-stderr.log`
- `stress-summary.json` (aggregate summary)
- `stress-results.json` (config + summary + full iteration details)

## Result Levels

Runtime suspect levels:

- `RACE_SUSPECT`
- `REPEATED_RACE_SUSPECT`
- `HIGH_CONFIDENCE_SUSPECT`

Aggregate stress outcome levels:

- `BENIGN`
- `SUSPICIOUS`
- `REPEATED_SUSPICIOUS`
- `HIGH_CONFIDENCE_SUSPICIOUS`

Classification behavior comes from `byteman_static/stress_report.py`:

- Any `HIGH_CONFIDENCE_SUSPECT` event => `HIGH_CONFIDENCE_SUSPICIOUS`
- Else repeated patterns / repeated suspect thresholds => `REPEATED_SUSPICIOUS` or `SUSPICIOUS`

## Verification Scripts

WSL/Linux scripts under `verification/scripts/`:

Script assumptions:

- `.venv-wsl` exists and contains required Python packages.
- `verification/tools/jdk17` and `verification/tools/byteman/byteman.jar` exist.
- Shell is Linux/WSL Bash.

- `e2e_wsl.sh`
  End-to-end scan + compile + startup + watcher run against `verification/fixtures/e2e_java`.
- `negative_scenarios_wsl.sh`
  Negative/resilience checks (missing roots, malformed logs, read/read-only overlap, etc.).
- `stress_e2e_wsl.sh`
  Stress runner execution and JSON assertions.

Quick stress E2E run:

```bash
source .venv-wsl/bin/activate
bash verification/scripts/stress_e2e_wsl.sh
cat verification/artifacts/stress/stress-summary.json
```

Verification script artifact paths:

- `verification/scripts/e2e_wsl.sh`
  - writes under `verification/artifacts/e2e/`
  - key files: `generated/*`, `runtime/byteman-runtime.log`, `watcher-report.jsonl`, `watcher-stdout.log`, `app-stdout.log`, `app-stderr.log`, `e2e-summary.txt`
- `verification/scripts/negative_scenarios_wsl.sh`
  - writes under `verification/artifacts/negative/`
  - key files: `negative-scenarios.txt`, `<scenario>.stdout.log`, `<scenario>.stderr.log`
- `verification/scripts/stress_e2e_wsl.sh`
  - writes under `verification/artifacts/stress/`
  - key files: `stress-summary.json`, `stress-results.json`, `stress-stdout.log`, `stress-stderr.log`

## Example Workflow

1. Generate rules/inventory from Java sources:

```bash
python -m byteman_static.cli scan \
  --source-root verification/fixtures/e2e_java/src/main/java \
  --package-prefix com.verifier.app \
  --output-dir verification/artifacts/manual_scan \
  --runtime-log-path verification/artifacts/manual_scan/runtime/byteman-runtime.log \
  --generate-linux-startup verification/artifacts/manual_scan/run-with-byteman.sh
```

2. Prepare required launcher environment and run app through generated script:

```bash
SRC_DIR="verification/fixtures/e2e_java/src/main/java"
CLASSES_DIR="verification/artifacts/manual_scan/classes"
mkdir -p "$CLASSES_DIR"
find "$SRC_DIR" -name '*.java' | sort > verification/artifacts/manual_scan/java-files.list
javac -d "$CLASSES_DIR" @verification/artifacts/manual_scan/java-files.list

mkdir -p verification/artifacts/manual_scan/byteman-home/lib
cp verification/tools/byteman/byteman.jar verification/artifacts/manual_scan/byteman-home/lib/byteman.jar

export BYTEMAN_HOME="$PWD/verification/artifacts/manual_scan/byteman-home"
export APP_CLASSPATH="$PWD/$CLASSES_DIR"
export APP_MAIN_CLASS="com.verifier.app.Main"
./verification/artifacts/manual_scan/run-with-byteman.sh
```

3. Monitor the runtime log:

```bash
python -m byteman_static.cli watch \
  --log-file verification/artifacts/manual_scan/runtime/byteman-runtime.log \
  --from-start \
  --report-file verification/artifacts/manual_scan/watcher-report.jsonl \
  --stop-after-idle-seconds 5
```

4. For repeated scenario execution, switch to `stress-run` with a scenario file and inspect:
   - `stress-summary.json`
   - `stress-results.json`

## Testing

Run tests:

```bash
python -m pytest -q
```

Coverage:

```bash
python -m pytest --cov=byteman_static \
  --cov-report=term-missing \
  --cov-report=xml:verification/reports/coverage.xml \
  --cov-report=html:verification/reports/coverage_html -q
```

## Troubleshooting

- `Source root does not exist or is not a directory`
  - Check `--source-root` or scenario `source_root`.
- `No Java sources matched ...`
  - Check scenario `java_sources_glob`.
- `byteman.jar path is required`
  - Pass `--byteman-jar` or set scenario `byteman_jar`.
- Launcher exits with missing env error
  - Set `BYTEMAN_HOME` and either `APP_JAR` or `APP_CLASSPATH` + `APP_MAIN_CLASS`.
- Watcher returns no suspects
  - Ensure overlap includes at least one write from different threads; read/read overlaps are ignored by design.
- Parser backend falls back to heuristic mode
  - Verify `tree-sitter` and `tree-sitter-java` are installed.
- Running stress on non-Linux host fails to execute launcher
  - Generated launcher is Bash-based; use Linux/WSL runtime.

## Limitations And Boundaries

- Static analysis is structural and conservative; it is not a race proof.
- Field usage mapping does not perform full cross-file type resolution.
- Heuristic parser fallback has reduced Java syntax coverage.
- Runtime detection is overlap-based heuristic, not lock-state proof.
- Deadlock event generation exists (`detectDeadlockNow`) but full deadlock proof still depends on JVM/runtime evidence.

## Additional Verification Docs

- `verification/reports/functional_coverage_matrix.md`
- `verification/reports/local_proof_report.md`
