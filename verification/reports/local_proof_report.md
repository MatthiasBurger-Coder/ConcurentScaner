# Local Proof Report (WSL, jcstress-like Extension)

## Scope

This run verifies the **extended** in-repo system:

- static Java scan and AST extraction
- Byteman rule generation
- Linux startup integration (`-javaagent`)
- live runtime watcher and suspect detection
- new scenario-based repeated stress runner with aggregate outcome reporting

## WSL Environment Used

- Distribution: Ubuntu (WSL2)
- Kernel: `5.15.167.4-microsoft-standard-WSL2`
- Working path: `/mnt/d/Projects/ConcurentScaner`
- Python (WSL): `3.12.3`
- Java (system): OpenJDK 21.x
- Java used for proof scripts: local Temurin 17.0.16 at `verification/tools/jdk17`

Evidence:

- `verification/evidence/00_wsl_distribution_windows_bridge.txt`
- `verification/evidence/01_wsl_environment.txt`

## Commands Executed in WSL

Tests + coverage:

```bash
source .venv-wsl/bin/activate
python -m pytest --cov=byteman_static --cov-report=term-missing --cov-report=xml:verification/reports/coverage.xml --cov-report=html:verification/reports/coverage_html -q
```

Baseline E2E:

```bash
bash verification/scripts/e2e_wsl.sh
```

Negative/resilience:

```bash
bash verification/scripts/negative_scenarios_wsl.sh
```

Stress E2E:

```bash
bash verification/scripts/stress_e2e_wsl.sh
```

## Results

- Pytest: `23 passed`
- Coverage (line): `87%` total (`byteman_static`)
- Baseline E2E: `PASS`
- Stress E2E: `PASS`
- Negative script: expected failure paths observed and handled

Evidence:

- `verification/evidence/10_pytest_coverage.txt`
- `verification/evidence/20_e2e_run.txt`
- `verification/evidence/30_negative_scenarios_stdout.txt`
- `verification/evidence/40_stress_e2e_run.txt`

## Key Produced Artifacts

- Baseline flow:
  - `verification/artifacts/e2e/generated/Byteman.log`
  - `verification/artifacts/e2e/generated/generated-rules.btm`
  - `verification/artifacts/e2e/runtime/byteman-runtime.log`
  - `verification/artifacts/e2e/watcher-report.jsonl`
- Stress flow:
  - `verification/artifacts/stress/stress-summary.json`
  - `verification/artifacts/stress/stress-results.json`
  - `verification/artifacts/stress/runs/iteration-*/watcher-report.jsonl`
  - `verification/artifacts/stress/runs/iteration-*/runtime/byteman-runtime.log`

## Coverage Matrix

See:

- `verification/reports/functional_coverage_matrix.md`

Weighted functional coverage demonstrated:

- **99.49%**

## Remaining Gap

- Interleaving encouragement is semi-deterministic (sleep/timing-based), not scheduler-deterministic.

## Conclusion

The repository now contains a locally proven **jcstress-like** stress and observation workflow on WSL/Linux with repeatable scenario runs, Byteman runtime instrumentation, live watcher analysis, and aggregate suspect reporting.
