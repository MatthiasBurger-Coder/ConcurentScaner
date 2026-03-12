# ConcurrentScanner Byteman Toolchain (jcstress-like)

This repository provides a **jcstress-like concurrency stress and observation system** for Java/JDK 17 code, built with:

- Python static analysis (Java AST scan)
- Byteman rule generation and startup integration (`-javaagent`)
- Python runtime log watching and race-suspect analysis
- repeated stress scenario execution with aggregation

It is **not** a full jcstress reimplementation.

## Quick Start (Junior Friendly)

Run inside **WSL (Linux)** from the repository root:

```bash
source .venv-wsl/bin/activate
bash verification/scripts/stress_e2e_wsl.sh
cat verification/artifacts/stress/stress-summary.json
```

If the script passes, you have an end-to-end local proof run.

## 1. What This System Does

- Scans Java sources recursively and builds a structural model.
- Generates deterministic Byteman rules (`.btm`).
- Starts Java with Byteman agent (`-javaagent`) on Linux/WSL.
- Parses runtime `BTM_EVT` lines and flags race-condition suspects.
- Runs repeatable scenario-based stress iterations and aggregates outcomes.

## 2. What "jcstress-like" Means Here

This project supports a **stress-oriented workflow** similar in spirit to jcstress:

- repeat scenarios many times
- encourage problematic interleavings
- capture structured events
- aggregate repeated suspicious patterns

But it does **not** claim formal jcstress semantics or exhaustive memory-model proof.

## 3. What It Does NOT Guarantee

- Static analysis does not prove race conditions.
- Runtime overlap detection is heuristic (suspect-based).
- Deadlock proof still depends on runtime JVM evidence.
- High-confidence suspects are still observations, not full formal proof.

## 4. Architecture (Simple View)

- `byteman_static/parser.py`: Java AST parsing (`tree-sitter-java`) + fallback.
- `byteman_static/generator.py`: scan orchestration + inventory/rules output.
- `byteman_static/rules.py`: deterministic Byteman rule rendering.
- `byteman_static/linux_integration.py`: Linux launcher script with `-javaagent`.
- `byteman_static/runtime_parser.py`: parse runtime `BTM_EVT` lines.
- `byteman_static/runtime_monitor.py`: tail/follow + race suspect detection.
- `byteman_static/stress_runner.py`: repeated scenario runs + aggregation.
- `byteman_static/stress_report.py`: per-iteration and cross-run summaries.
- `byteman_static/cli.py`: CLI (`scan`, `watch`, `linux-startup`, `stress-run`).

## 5. Requirements

- **WSL Linux environment required** for Linux verification and startup flow.
- Java: **JDK 17** for target runtime verification.
- Python: 3.12+ recommended.
- Byteman agent jar (`byteman.jar`).
- Python dependencies:

```bash
python -m pip install -r requirements.txt
python -m pip install pytest pytest-cov
```

## 6. Setup (WSL)

Example setup in WSL:

```bash
cd /mnt/d/Projects/ConcurentScaner
python3 -m venv .venv-wsl
source .venv-wsl/bin/activate
pip install -r requirements.txt
pip install pytest pytest-cov
```

The repository already includes local verification tools under `verification/tools/` in this checkout.

## 7. Static Scan + Rule Generation

```bash
python -m byteman_static.cli scan \
  --source-root verification/fixtures/e2e_java/src/main/java \
  --package-prefix com.verifier.app \
  --output-dir verification/artifacts/manual_scan \
  --runtime-log-path verification/artifacts/manual_scan/runtime/byteman-runtime.log \
  --generate-linux-startup verification/artifacts/manual_scan/run-with-byteman.sh
```

Generated files:

- `Byteman.log`
- `generated-rules.btm`
- `analysis-metadata.json`
- optional startup wrapper script

## 8. Runtime Watcher

```bash
python -m byteman_static.cli watch \
  --log-file verification/artifacts/e2e/runtime/byteman-runtime.log \
  --from-start \
  --report-file verification/artifacts/e2e/watcher-report.jsonl \
  --stop-after-idle-seconds 5
```

## 9. Stress-Run (jcstress-like Workflow)

Scenario file example is provided:

- `verification/fixtures/stress_scenarios/shared_counter_stress.json`

Run:

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

## 10. Linux Startup Integration (`-javaagent`)

Use generated script (or generate only):

```bash
python -m byteman_static.cli linux-startup \
  --output-script verification/artifacts/manual_scan/run-with-byteman.sh \
  --rules-file verification/artifacts/manual_scan/generated-rules.btm \
  --runtime-log-file verification/artifacts/manual_scan/runtime/byteman-runtime.log
```

The launcher injects:

- `-javaagent:<byteman.jar>=script:<rules>,listener:true`
- `-Dorg.jboss.byteman.verbose=true`
- `-Dorg.jboss.byteman.transform.all=true`
- `-Dbyteman.runtime.log=<runtime-log>`

## 11. Tests

Unit/component/integration tests:

```bash
source .venv-wsl/bin/activate
python -m pytest -q
```

Coverage:

```bash
python -m pytest --cov=byteman_static \
  --cov-report=term-missing \
  --cov-report=xml:verification/reports/coverage.xml \
  --cov-report=html:verification/reports/coverage_html -q
```

## 12. End-to-End Scripts

- Baseline E2E: `verification/scripts/e2e_wsl.sh`
- Negative/resilience scenarios: `verification/scripts/negative_scenarios_wsl.sh`
- jcstress-like stress E2E: `verification/scripts/stress_e2e_wsl.sh`

## 13. Where Logs and Reports Are Written

- Baseline E2E artifacts: `verification/artifacts/e2e/`
- Negative scenario artifacts: `verification/artifacts/negative/`
- Stress-run artifacts: `verification/artifacts/stress/`
  - `stress-summary.json`
  - `stress-results.json`
  - `runs/iteration-*/watcher-report.jsonl`
  - per-iteration runtime/app logs

## 14. Result Categories

Runtime and stress classification uses:

- `RACE_SUSPECT`
- `REPEATED_RACE_SUSPECT`
- `HIGH_CONFIDENCE_SUSPECT`

Aggregate stress outcome levels:

- `BENIGN`
- `SUSPICIOUS`
- `REPEATED_SUSPICIOUS`
- `HIGH_CONFIDENCE_SUSPICIOUS`

Interpretation:

- `BENIGN`: no suspicious overlapping pattern observed.
- `SUSPICIOUS`: suspicious overlap observed.
- `REPEATED_SUSPICIOUS`: suspicious pattern repeats across runs.
- `HIGH_CONFIDENCE_SUSPICIOUS`: repeated/strong evidence, still heuristic.

## 15. Expected Output Examples

CLI stress summary (stdout):

```text
STRESS_SUMMARY
scenario_id=shared-counter-overlap
outcome_level=HIGH_CONFIDENCE_SUSPICIOUS
total_iterations=5
successful_iterations=5
...
```

Watcher alert line:

```text
RACE_SUSPECT class=com.verifier.app.SharedCounter field=value threads=...
```

## 16. Common Errors and Fixes

- `Missing .venv-wsl`
  - Create it with `python3 -m venv .venv-wsl`.
- `byteman.jar path is required`
  - Add `--byteman-jar ...` or set `byteman_jar` in scenario JSON.
- `Source root does not exist`
  - Check `source_root` in scenario/config.
- `processing of -javaagent failed`
  - Verify Byteman jar path and rules file path.
- No suspects seen in stress run
  - Increase iterations/concurrency or pause values in scenario env.

## 17. Troubleshooting

- Confirm WSL runtime context:
  - `uname -a`
  - `python3 --version`
  - `java -version`
- Check generated launcher script:
  - `verification/artifacts/stress/run-with-byteman.sh`
- Check per-iteration logs:
  - `verification/artifacts/stress/runs/iteration-*/`
- Check machine-readable summary:
  - `verification/artifacts/stress/stress-summary.json`

## 18. Verification Reports

- Functional coverage matrix:
  - `verification/reports/functional_coverage_matrix.md`
- Local proof report:
  - `verification/reports/local_proof_report.md`
