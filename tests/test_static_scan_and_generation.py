from __future__ import annotations

import json
from pathlib import Path

import pytest

from byteman_static.generator import GeneratorConfig, run_generator
from byteman_static.parser import analyze_source_tree


REPO_ROOT = Path(__file__).resolve().parents[1]
STATIC_FIXTURE_ROOT = REPO_ROOT / "verification" / "fixtures" / "static_java" / "src" / "main" / "java"


def test_ast_scan_extracts_java_structures() -> None:
    result = analyze_source_tree(
        source_root=STATIC_FIXTURE_ROOT,
        package_prefix="com.verifier.app",
    )
    assert result.parser_backend == "tree-sitter-java"
    assert result.scanned_files == 6
    assert result.parse_failures == 0

    kinds = sorted(type_info.kind for file_info in result.java_files for type_info in file_info.types)
    assert "class" in kinds
    assert "interface" in kinds
    assert "enum" in kinds
    assert "record" in kinds

    counter_type = None
    for file_info in result.java_files:
        for type_info in file_info.types:
            if type_info.qualified_name == "com.verifier.app.Counter":
                counter_type = type_info
                break
    assert counter_type is not None

    field_names = {field.name for field in counter_type.fields}
    assert {"value", "hits"} <= field_names

    constructors = [method for method in counter_type.methods if method.is_constructor]
    assert len(constructors) == 1
    assert constructors[0].display_name == "Counter(int)"

    increment = [method for method in counter_type.methods if method.name == "incrementAndGet"][0]
    assert "before" in increment.local_variables
    usage_pairs = {(usage.field_name, usage.access_kind) for usage in increment.field_usages}
    assert ("value", "read") in usage_pairs
    assert ("value", "write") in usage_pairs

    broken_file = [info for info in result.java_files if info.file_path.endswith("Broken.java")][0]
    assert broken_file.errors


def test_package_filter_excludes_nonmatching_package() -> None:
    result = analyze_source_tree(
        source_root=STATIC_FIXTURE_ROOT,
        package_prefix="com.verifier.app",
    )
    names = {type_info.qualified_name for file_info in result.java_files for type_info in file_info.types}
    assert "com.verifier.other.Excluded" not in names


def test_nonmatching_package_prefix_results_in_zero_parsed_types() -> None:
    result = analyze_source_tree(
        source_root=STATIC_FIXTURE_ROOT,
        package_prefix="com.missing.prefix",
    )
    assert result.scanned_files == 6
    assert result.parsed_files == 0
    assert result.discovered_types == 0


def test_generator_writes_outputs_and_rules_are_deterministic(tmp_path: Path) -> None:
    output_a = tmp_path / "run_a"
    output_b = tmp_path / "run_b"
    config_a = GeneratorConfig(
        source_root=STATIC_FIXTURE_ROOT,
        output_dir=output_a,
        package_prefix="com.verifier.app",
        helper_class="com.example.byteman.RuntimeTraceHelper",
        runtime_log_path=output_a / "Byteman.runtime.log",
    )
    config_b = GeneratorConfig(
        source_root=STATIC_FIXTURE_ROOT,
        output_dir=output_b,
        package_prefix="com.verifier.app",
        helper_class="com.example.byteman.RuntimeTraceHelper",
        runtime_log_path=output_b / "Byteman.runtime.log",
    )
    result_a = run_generator(config_a)
    result_b = run_generator(config_b)

    rules_a = result_a.rules_path.read_text(encoding="utf-8")
    rules_b = result_b.rules_path.read_text(encoding="utf-8")
    assert rules_a == rules_b

    inventory = result_a.byteman_log_path.read_text(encoding="utf-8")
    assert "INTERFACE com.verifier.app.Service" in inventory
    assert "ENUM com.verifier.app.Mode" in inventory
    assert "RECORD com.verifier.app.UserRecord" in inventory
    assert "CONSTRUCTOR Counter(int)" in inventory

    metadata_path = output_a / "analysis-metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["config"]["runtime_log_path"].endswith("Byteman.runtime.log")


def test_missing_source_root_raises_file_not_found(tmp_path: Path) -> None:
    missing = tmp_path / "missing-src"
    with pytest.raises(FileNotFoundError):
        analyze_source_tree(missing)
