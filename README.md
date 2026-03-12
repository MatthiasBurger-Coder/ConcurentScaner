# ConcurrentScanner Byteman Toolchain (Linux Runtime Target)

This repository now contains a Python-based static and runtime analysis toolchain for Byteman.

## Current repository state

At the time of implementation in this checkout:

- no Java source files were present
- no Maven/Gradle build files were present
- no existing Java startup script was present

Because of that, integration is provided as an explicit Linux startup wrapper template that can be attached to the real Java app startup path when Java sources/build scripts are added or checked out.

## What is implemented

Python package: `byteman_static/`

- `parser.py`: recursive Java scan + AST parsing (`tree-sitter-java`) with fallback parser
- `model.py`: static analysis domain model (`TypeInfo`, `MethodInfo`, `FieldUsage`, `RuleDefinition`, etc.)
- `inventory.py`: `Byteman.log` inventory rendering
- `rules.py`: deterministic `.btm` generation
- `generator.py`: scan/generate orchestration and metadata output
- `runtime_parser.py`: runtime event line parser (`BTM_EVT ...`)
- `runtime_model.py`: runtime event and race suspect model
- `runtime_monitor.py`: live log follower (`tail -f` behavior) + race-suspect detection
- `linux_integration.py`: Linux startup script generation for `-javaagent`
- `cli.py`: CLI entrypoints (`scan`, `watch`, `linux-startup`)

## Install dependencies

```bash
python -m pip install -r requirements.txt
```

## CLI commands

### 1. Static scan + rule generation

```bash
python -m byteman_static.cli scan \
  --source-root /path/to/src/main/java \
  --package-prefix com.example \
  --output-dir /path/to/out \
  --runtime-log-path /path/to/logs/byteman-runtime.log \
  --generate-linux-startup /path/to/scripts/run-with-byteman.sh
```

Outputs:

- `Byteman.log` inventory
- `generated-rules.btm`
- `analysis-metadata.json` (unless `--no-metadata`)
- optional Linux startup script

### 2. Runtime log watcher

```bash
python -m byteman_static.cli watch \
  --log-file /path/to/logs/byteman-runtime.log \
  --report-file /path/to/out/race-report.jsonl \
  --emit-raw-events
```

Optional:

- `--no-follow` to process once and exit
- `--from-start` to read from beginning
- `--repeated-threshold 3`
- `--high-confidence-threshold 6`
- `--stop-after-idle-seconds 5` for smoke tests

### 3. Linux startup script generation only

```bash
python -m byteman_static.cli linux-startup \
  --output-script /path/to/scripts/run-with-byteman.sh \
  --rules-file /path/to/out/generated-rules.btm \
  --runtime-log-file /path/to/logs/byteman-runtime.log
```

## Runtime event format expected by watcher

The watcher consumes structured line events such as:

```text
BTM_EVT ts=2026-03-12T20:00:00.100Z event=FIELD_BEFORE thread=worker-1 tid=41 class=com.example.Counter method=inc() field=value write=true
BTM_EVT ts=2026-03-12T20:00:00.101Z event=FIELD_AFTER thread=worker-1 tid=41 class=com.example.Counter method=inc() field=value write=true
```

Accepted event types:

- `METHOD_ENTER`
- `METHOD_EXIT`
- `FIELD_BEFORE`
- `FIELD_AFTER`
- `DEADLOCK_CHECK`

## Inventory output keys

`Byteman.log` includes structured items:

- `FILE`
- `PACKAGE`
- `IMPORT`
- `TYPE`
- `CLASS`
- `INTERFACE`
- `ENUM`
- `RECORD`
- `FIELD`
- `CONSTRUCTOR`
- `METHOD`
- `PARAM`
- `LOCAL`
- `USES_FIELD`

## Race suspicion levels

Runtime monitor emits:

- `RACE_SUSPECT`
- `REPEATED_RACE_SUSPECT`
- `HIGH_CONFIDENCE_SUSPECT`

These are heuristic signals based on overlapping field-access windows across threads with at least one write. They are not formal proof.

## Linux startup integration behavior

Generated script:

- injects `-javaagent:<byteman.jar>=script:<generated-rules.btm>,listener:true`
- sets:
  - `-Dorg.jboss.byteman.verbose=true`
  - `-Dorg.jboss.byteman.transform.all=true`
  - `-Dbyteman.runtime.log=<runtime log path>`
- supports startup via:
  - `APP_JAR`, or
  - `APP_CLASSPATH` + `APP_MAIN_CLASS`

## Limitations

- Static analysis cannot prove race conditions.
- Runtime overlap detection is heuristic and field-centric.
- No deep interprocedural alias analysis is performed.
- `tree-sitter-java` parsing quality depends on source validity and grammar support.
- This checkout currently lacks Java app/build/startup files, so integration is delivered as explicit script generation rather than patching an existing launcher.
