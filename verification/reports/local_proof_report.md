# Local Proof Report (WSL)

## 1. Verification scope

This is a verification-only workstream against the existing implementation in `byteman_static/`.

No core feature reimplementation was performed. Only verification assets were added:

- `tests/*`
- `verification/fixtures/*`
- `verification/scripts/*`
- `verification/reports/*`
- `verification/evidence/*`

## 2. WSL environment used

- Distribution: Ubuntu (WSL2)
- Linux kernel: `5.15.167.4-microsoft-standard-WSL2`
- WSL working directory: `/mnt/d/Projects/ConcurentScaner`
- Python inside WSL: `Python 3.12.3`
- Java inside WSL (system): `OpenJDK 21.0.9`
- Java for proof runs: local Temurin `JDK 17.0.16` under `verification/tools/jdk17`

Evidence:

- `verification/evidence/00_wsl_distribution_windows_bridge.txt`
- `verification/evidence/01_wsl_environment.txt`
- `verification/evidence/02_jdk17_local.txt`

## 3. Commands executed (WSL)

Setup:

- `python3 -m venv .venv-wsl`
- `source .venv-wsl/bin/activate`
- `pip install -r requirements.txt pytest pytest-cov`
- download tools:
  - JDK17 tarball -> `verification/tools/jdk17`
  - Byteman jar -> `verification/tools/byteman/byteman.jar`

Automated tests + coverage:

- `pytest -q --cov=byteman_static --cov-branch --cov-report=term-missing --cov-report=xml:verification/reports/coverage.xml --cov-report=html:verification/reports/coverage_html tests`

End-to-end proof:

- `verification/scripts/e2e_wsl.sh`

Negative scenarios:

- `verification/scripts/negative_scenarios_wsl.sh`

## 4. Test and coverage results

- Pytest: `15 passed`
- Line/branch coverage (code coverage tool): `83%` total

Evidence:

- `verification/evidence/10_pytest_coverage.txt`
- `verification/reports/coverage.xml`
- `verification/reports/coverage_html/index.html`

Note: code coverage percentage is not used as the only measure of functional completion; functional coverage matrix is provided separately.

## 5. End-to-end proof summary

E2E command executed in WSL:

- `verification/scripts/e2e_wsl.sh`

Observed outcomes:

- scan completed and generated:
  - `verification/artifacts/e2e/generated/Byteman.log`
  - `verification/artifacts/e2e/generated/generated-rules.btm`
- Linux startup wrapper generated:
  - `verification/artifacts/e2e/run-with-byteman.sh`
- Java app started under `-javaagent` with Byteman in WSL JDK17.
- Byteman trigger/load evidence present in app output.
- runtime log created and populated:
  - `verification/artifacts/e2e/runtime/byteman-runtime.log`
- watcher executed concurrently and emitted race suspects:
  - `verification/artifacts/e2e/watcher-stdout.log`
  - `verification/artifacts/e2e/watcher-report.jsonl`

High-level e2e summary:

- `verification/evidence/20_e2e_run.txt`
- `verification/evidence/20_e2e_summary.txt`
- `verification/evidence/21_e2e_key_excerpts.txt`

## 6. Negative/resilience proof summary

Executed negative/resilience scenarios in WSL:

- missing source root
- base package mismatch
- malformed runtime log lines
- read-read only overlap
- single-threaded access
- duplicate + partial event order
- missing `.btm` file at startup (`-javaagent` fails with explicit Byteman error)

Evidence:

- `verification/artifacts/negative/negative-scenarios.txt`
- `verification/evidence/30_negative_scenarios_stdout.txt`
- detailed stdout/stderr logs in `verification/artifacts/negative/*.log`

## 7. Functional coverage result

Functional coverage matrix:

- `verification/reports/functional_coverage_matrix.md`

Weighted functional coverage achieved:

- **99.5%**

## 8. Remaining gap

- Partial-only item: direct verification against an existing in-repo Java app startup convention is not possible in this checkout, because this repository currently has no Java app/build/startup files to attach to.  
  Coverage for this item is partial and explicitly documented in the matrix.

## 9. Conclusion

The existing implementation is locally proven in WSL for the intended toolchain behavior:

- static scan and structural extraction
- deterministic Byteman rule generation
- Linux startup integration (`-javaagent`)
- actual JVM startup with Byteman
- runtime event log creation
- continuous watcher parsing and race-suspect detection
- negative/resilience behavior handling

with evidence artifacts and reproducible commands captured under `verification/`.
