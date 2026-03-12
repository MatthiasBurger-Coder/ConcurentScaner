# Functional Coverage Matrix (jcstress-like Extension, WSL Proof)

| Requirement ID | Requirement description | Verification type | Test / script / command | Evidence artifact | Result | Coverage status | Weight | Score |
|---|---|---|---|---|---|---|---:|---:|
| F01 | Recursive static Java scan | Unit/Component | `tests/test_static_scan_and_generation.py::test_ast_scan_extracts_java_structures` | `verification/evidence/10_pytest_coverage.txt` | Pass | Covered | 3 | 3 |
| F02 | AST parsing path active (`tree-sitter-java`) | Unit + CLI | pytest + `cli scan` | `verification/evidence/10_pytest_coverage.txt`, `verification/artifacts/e2e/scan-stdout.log` | Pass | Covered | 3 | 3 |
| F03 | Extract package/import/type kinds | Unit | `test_ast_scan_extracts_java_structures` | `verification/evidence/10_pytest_coverage.txt`, `verification/artifacts/e2e/generated/Byteman.log` | Pass | Covered | 3 | 3 |
| F04 | Extract fields/constructors/methods/params/locals/field usage | Unit | `test_ast_scan_extracts_java_structures` | `verification/evidence/10_pytest_coverage.txt` | Pass | Covered | 4 | 4 |
| F05 | Inventory file structure and keys | Unit + Integration | generator tests + e2e scan | `verification/artifacts/e2e/generated/Byteman.log` | Pass | Covered | 3 | 3 |
| F06 | Deterministic Byteman rule generation | Unit | `test_generator_writes_outputs_and_rules_are_deterministic` | `verification/evidence/10_pytest_coverage.txt` | Pass | Covered | 3 | 3 |
| F07 | Rule generation includes method entry/exit and field hooks | Unit + Integration | rules tests + e2e artifacts | `verification/artifacts/e2e/generated/generated-rules.btm` | Pass | Covered | 4 | 4 |
| F08 | Linux startup wrapper with `-javaagent` | Unit + Integration | `test_linux_startup_script_generation`, `e2e_wsl.sh` | `verification/artifacts/e2e/run-with-byteman.sh` | Pass | Covered | 3 | 3 |
| F09 | JVM startup with Byteman in WSL/JDK17 | E2E | `verification/scripts/e2e_wsl.sh` | `verification/evidence/20_e2e_run.txt` | Pass | Covered | 5 | 5 |
| F10 | Runtime Byteman log creation | E2E | `e2e_wsl.sh` | `verification/artifacts/e2e/runtime/byteman-runtime.log` | Pass | Covered | 4 | 4 |
| F11 | Continuous log watching (`tail -f` behavior) | Unit + E2E | monitor tests + `e2e_wsl.sh` | `verification/evidence/10_pytest_coverage.txt`, `verification/artifacts/e2e/watcher-report.jsonl` | Pass | Covered | 3 | 3 |
| F12 | Runtime line parser for key-value and JSON | Unit | `test_runtime_parser_supports_key_value_and_json_lines` | `verification/evidence/10_pytest_coverage.txt` | Pass | Covered | 3 | 3 |
| F13 | Race-suspect detection (writer overlap) | Unit + E2E | monitor tests + e2e watcher | `verification/evidence/10_pytest_coverage.txt`, `verification/artifacts/e2e/watcher-stdout.log` | Pass | Covered | 4 | 4 |
| F14 | Escalation to repeated/high-confidence | Unit + Stress E2E | `test_race_suspect_levels_progression`, `stress_e2e_wsl.sh` | `verification/evidence/10_pytest_coverage.txt`, `verification/evidence/40_stress_e2e_run.txt` | Pass | Covered | 4 | 4 |
| F15 | No false positive for read-read only | Unit + Negative | `test_read_read_overlap_does_not_emit_suspect`, negative script | `verification/evidence/30_negative_scenarios_stdout.txt` | Pass | Covered | 3 | 3 |
| F16 | No false positive for single-threaded stream | Unit + Negative | `test_single_thread_write_read_does_not_emit_suspect`, negative script | `verification/evidence/30_negative_scenarios_stdout.txt` | Pass | Covered | 3 | 3 |
| F17 | Malformed runtime lines handled safely | Unit + Negative | `test_monitor_ignores_malformed_lines_without_crashing`, negative script | `verification/evidence/30_negative_scenarios_stdout.txt` | Pass | Covered | 3 | 3 |
| F18 | Truncation/rotation handling in watcher | Unit | `test_monitor_handles_log_truncation_during_follow` | `verification/evidence/10_pytest_coverage.txt` | Pass | Covered | 2 | 2 |
| F19 | Duplicate/partial ordering resilience | Unit + Negative | `test_duplicate_and_partial_order_events_do_not_crash_monitor`, negative script | `verification/evidence/30_negative_scenarios_stdout.txt` | Pass | Covered | 2 | 2 |
| F20 | Scenario-driven stress execution | Unit/Integration/E2E | `test_execute_stress_run_with_mocked_processes`, `stress_e2e_wsl.sh` | `verification/evidence/10_pytest_coverage.txt`, `verification/evidence/40_stress_e2e_run.txt` | Pass | Covered | 5 | 5 |
| F21 | Configurable iterations and concurrency | Unit + E2E | CLI stress test + stress script flags | `verification/evidence/10_pytest_coverage.txt`, `verification/scripts/stress_e2e_wsl.sh` | Pass | Covered | 4 | 4 |
| F22 | Structured per-iteration outcomes | Unit + E2E artifacts | stress runner/report tests + produced JSON | `verification/artifacts/stress/stress-results.json` | Pass | Covered | 4 | 4 |
| F23 | Aggregation across repeated runs | Unit + E2E artifacts | `test_aggregate_stress_results_classifies_repeated_suspicion`, stress script | `verification/evidence/10_pytest_coverage.txt`, `verification/artifacts/stress/stress-summary.json` | Pass | Covered | 4 | 4 |
| F24 | Stress outcome categories (`BENIGN`..`HIGH_CONFIDENCE`) | Unit + E2E | stress report tests + stress summary | `verification/artifacts/stress/stress-summary.json` | Pass | Covered | 3 | 3 |
| F25 | Missing source root / invalid scenario handling | Unit + Negative | scenario loader test + negative scan | `verification/evidence/10_pytest_coverage.txt`, `verification/evidence/30_negative_scenarios_stdout.txt` | Pass | Covered | 3 | 3 |
| F26 | Missing/invalid rules behavior on startup | Negative integration | `startup_missing_rules` scenario | `verification/evidence/30_negative_scenarios_stdout.txt`, `verification/artifacts/negative/startup_missing_rules.stderr.log` | Pass | Covered | 3 | 3 |
| F27 | WSL-based Linux proof for Python + Java + scripts | Environment + E2E | WSL commands + all scripts | `verification/evidence/00_wsl_distribution_windows_bridge.txt`, `verification/evidence/01_wsl_environment.txt`, `verification/evidence/20_e2e_run.txt`, `verification/evidence/40_stress_e2e_run.txt` | Pass | Covered | 5 | 5 |
| F28 | Interleaving encouragement is configurable/repeatable | Scenario/E2E | stress scenario env (`STRESS_PAUSE_MS`) + repeated runs | `verification/fixtures/stress_scenarios/shared_counter_stress.json`, `verification/artifacts/stress/stress-summary.json` | Pass (semi-deterministic, sleep-based) | Partial | 2 | 1.5 |

**Weighted functional coverage:** `98.5 / 99 = 99.49%`
