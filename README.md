# ConcurrentScanner - Static Byteman Generator

Python toolchain for statically scanning Java sources and generating:

- `Byteman.log` inventory
- `generated-rules.btm` rule file
- optional `analysis-metadata.json` traceability output

The generator is designed for runtime concurrency investigations with a companion Java helper, especially:

- deadlock suspicion checks (runtime-only confirmation via `ThreadMXBean` or equivalent)
- race-condition suspicion logging (static signal + runtime evidence)

## Module layout

- `byteman_static/parser.py`: Java parsing and source-tree scan orchestration
- `byteman_static/model.py`: analysis data model
- `byteman_static/inventory.py`: `Byteman.log` formatter/writer
- `byteman_static/rules.py`: deterministic Byteman rule generation
- `byteman_static/generator.py`: end-to-end pipeline wiring
- `byteman_static/cli.py`: command-line entrypoint

## Parser strategy

- Preferred: AST parsing using `tree-sitter` + `tree-sitter-java` (recommended for Java/JDK 17 codebases)
- Fallback: heuristic regex parser when AST dependencies are unavailable

The output clearly reports parser backend and limitations.

## Install

```bash
python -m pip install -r requirements.txt
```

## CLI usage

```bash
python -m byteman_static.cli \
  --source-root D:\path\to\project\src\main\java \
  --package-prefix com.example \
  --output-dir D:\path\to\project\build\byteman
```

### Arguments

- `--source-root` (required): recursively scanned root for `.java` files
- `--output-dir` (required): output directory
- `--package-prefix` (optional): include package and subpackages
- `--package-regex` (optional): additional regex filter for package names
- `--helper-class` (optional): helper used in generated actions, default `com.example.byteman.RuntimeTraceHelper`
- `--no-metadata` (optional): skip `analysis-metadata.json`

## Generated output format examples

### `Byteman.log` (sample)

```text
# Byteman static inventory
# parser_backend=tree-sitter-java
SUMMARY SCANNED_FILES 12
SUMMARY PARSED_FILES 12
SUMMARY PARSE_FAILURES 0
SUMMARY TYPES 8
SUMMARY METHODS 42
SUMMARY FIELDS 19

FILE D:\repo\src\main\java\com\example\service\AccountService.java
PARSE_MODE ast
PACKAGE com.example.service
IMPORT java.util.concurrent.locks.ReentrantLock
TYPE CLASS com.example.service.AccountService
CLASS com.example.service.AccountService
FIELD lock : ReentrantLock
METHOD transfer(long,long) RETURN boolean
PARAM fromId : long
PARAM toId : long
LOCAL attempts
USES_FIELD lock ACCESS READ CONFIDENCE EXACT EVIDENCE node=field_access
```

### `generated-rules.btm` (sample)

```text
RULE BM_ENTRY__com_example_service_AccountService__transfer_long_long_
CLASS com.example.service.AccountService
METHOD transfer(long,long)
AT ENTRY
IF TRUE
DO com.example.byteman.RuntimeTraceHelper.onMethodEnter("com.example.service.AccountService", "transfer(long,long)"); com.example.byteman.RuntimeTraceHelper.detectDeadlockNow()
ENDRULE

RULE BM_EXIT__com_example_service_AccountService__transfer_long_long_
CLASS com.example.service.AccountService
METHOD transfer(long,long)
AT EXIT
IF TRUE
DO com.example.byteman.RuntimeTraceHelper.onMethodExit("com.example.service.AccountService", "transfer(long,long)")
ENDRULE

RULE BM_FIELD_BEFORE_READ__com_example_service_AccountService__transfer_long_long___lock
CLASS com.example.service.AccountService
METHOD transfer(long,long)
AT READ lock
IF TRUE
DO com.example.byteman.RuntimeTraceHelper.beforeFieldAccess("com.example.service.AccountService", "transfer(long,long)", "lock", false)
ENDRULE
```

## Notes and limitations

- Static analysis provides exact source-structure facts (where parser support is available).
- Field usage mapping is conservative and intentionally marks uncertain cases as heuristic.
- Static analysis alone cannot prove race conditions.
- Deadlock identification must rely on runtime JVM facilities in the companion helper.
