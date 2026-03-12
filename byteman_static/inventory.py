from __future__ import annotations

from pathlib import Path

from byteman_static.model import AnalysisResult, MethodInfo, TypeInfo


def write_inventory_log(result: AnalysisResult, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = build_inventory_lines(result)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_inventory_lines(result: AnalysisResult) -> list[str]:
    lines: list[str] = [
        "# Byteman static inventory",
        f"# parser_backend={result.parser_backend}",
    ]
    for limitation in result.limitations:
        lines.append(f"# limitation={limitation}")
    lines.extend(
        [
            f"SUMMARY SCANNED_FILES {result.scanned_files}",
            f"SUMMARY PARSED_FILES {result.parsed_files}",
            f"SUMMARY PARSE_FAILURES {result.parse_failures}",
            f"SUMMARY TYPES {result.discovered_types}",
            f"SUMMARY METHODS {result.discovered_methods}",
            f"SUMMARY FIELDS {result.discovered_fields}",
            "",
        ]
    )

    for file_info in sorted(result.java_files, key=lambda item: item.file_path.lower()):
        lines.append(f"FILE {file_info.file_path}")
        lines.append(f"PARSE_MODE {file_info.parse_mode}")
        lines.append(f"PACKAGE {file_info.package_name or '<default>'}")
        for import_name in sorted(file_info.imports):
            lines.append(f"IMPORT {import_name}")
        for error in file_info.errors:
            lines.append(f"ERROR {error}")

        for type_info in sorted(file_info.types, key=lambda item: item.qualified_name):
            lines.extend(_format_type(type_info))
        lines.append("")

    return lines


def _format_type(type_info: TypeInfo) -> list[str]:
    lines = [
        f"TYPE {type_info.kind.upper()} {type_info.qualified_name}",
    ]
    if type_info.kind == "class":
        lines.append(f"CLASS {type_info.qualified_name}")
    elif type_info.kind == "interface":
        lines.append(f"INTERFACE {type_info.qualified_name}")
    elif type_info.kind == "enum":
        lines.append(f"ENUM {type_info.qualified_name}")
    elif type_info.kind == "record":
        lines.append(f"RECORD {type_info.qualified_name}")

    for field in sorted(type_info.fields, key=lambda item: item.name):
        lines.append(f"FIELD {field.name} : {field.type_name}")

    for method in sorted(type_info.methods, key=lambda item: item.signature):
        lines.extend(_format_method(method))

    return lines


def _format_method(method: MethodInfo) -> list[str]:
    lines: list[str] = []
    if method.is_constructor:
        lines.append(f"CONSTRUCTOR {method.display_name}")
    lines.append(
        (
            f"METHOD {method.display_name} RETURN {method.return_type}"
            if not method.is_constructor
            else f"METHOD {method.display_name} RETURN <constructor>"
        )
    )
    for parameter in method.parameters:
        lines.append(f"PARAM {parameter.name} : {parameter.type_name}")
    for local_name in sorted(method.local_variables):
        lines.append(f"LOCAL {local_name}")
    for usage in method.field_usages:
        lines.append(
            f"USES_FIELD {usage.field_name} ACCESS {usage.access_kind.upper()} CONFIDENCE {usage.confidence.upper()} EVIDENCE {usage.evidence}"
        )
    return lines
