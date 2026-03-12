from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from byteman_static.model import (
    AnalysisResult,
    FieldInfo,
    FieldUsage,
    JavaFileInfo,
    MethodInfo,
    ParameterInfo,
    TypeInfo,
)

TYPE_DECLARATION_KINDS = {
    "class_declaration": "class",
    "interface_declaration": "interface",
    "enum_declaration": "enum",
    "record_declaration": "record",
}


@dataclass(frozen=True)
class ParserSelection:
    backend_name: str
    parser: "BaseJavaParser"
    limitations: list[str]


class BaseJavaParser:
    parse_mode: str = "heuristic"

    def parse_file(self, file_path: Path) -> JavaFileInfo:
        raise NotImplementedError


class TreeSitterJavaParser(BaseJavaParser):
    parse_mode = "ast"

    def __init__(self) -> None:
        from tree_sitter import Language, Parser
        import tree_sitter_java

        language = Language(tree_sitter_java.language())
        parser = Parser()
        if hasattr(parser, "set_language"):
            parser.set_language(language)
        else:
            parser = Parser(language)
        self._parser = parser

    def parse_file(self, file_path: Path) -> JavaFileInfo:
        source = file_path.read_bytes()
        tree = self._parser.parse(source)
        root = tree.root_node
        errors: list[str] = []
        if root.has_error:
            errors.append("Tree-sitter parse tree contains syntax errors; results may be partial.")

        package_name = _extract_package_name(root, source)
        imports = _extract_imports(root, source)
        types: list[TypeInfo] = []
        _walk_for_types(
            root=root,
            source=source,
            package_name=package_name,
            enclosing_types=[],
            sink=types,
        )

        return JavaFileInfo(
            file_path=str(file_path),
            package_name=package_name,
            imports=imports,
            types=types,
            parse_mode=self.parse_mode,
            errors=errors,
        )


class HeuristicJavaParser(BaseJavaParser):
    parse_mode = "heuristic"

    _PACKAGE_PATTERN = re.compile(r"^\s*package\s+([A-Za-z_][\w.]*)\s*;", re.MULTILINE)
    _IMPORT_PATTERN = re.compile(r"^\s*import\s+([^;]+);", re.MULTILINE)
    _TYPE_PATTERN = re.compile(r"\b(class|interface|enum|record)\s+([A-Za-z_]\w*)")
    _FIELD_PATTERN = re.compile(
        r"^\s*(?:public|private|protected|static|final|transient|volatile|\s)+([A-Za-z_][\w.<>\[\]? ,]*)\s+([A-Za-z_]\w*)\s*(?:=|;)",
        re.MULTILINE,
    )
    _METHOD_PATTERN = re.compile(
        r"^\s*(?:public|private|protected|static|final|synchronized|native|abstract|\s)+([A-Za-z_][\w.<>\[\]? ,]*)\s+([A-Za-z_]\w*)\s*\(([^)]*)\)",
        re.MULTILINE,
    )

    def parse_file(self, file_path: Path) -> JavaFileInfo:
        text = file_path.read_text(encoding="utf-8", errors="replace")
        package_match = self._PACKAGE_PATTERN.search(text)
        package_name = package_match.group(1) if package_match else ""
        imports = [match.group(1).strip() for match in self._IMPORT_PATTERN.finditer(text)]

        types: list[TypeInfo] = []
        type_matches = list(self._TYPE_PATTERN.finditer(text))
        if type_matches:
            first_kind, first_name = type_matches[0].groups()
            type_info = TypeInfo(kind=first_kind, package_name=package_name, simple_name=first_name)
            type_info.fields = [
                FieldInfo(name=match.group(2), type_name=_normalize_spaces(match.group(1)))
                for match in self._FIELD_PATTERN.finditer(text)
            ]
            type_info.methods = [
                MethodInfo(
                    name=match.group(2),
                    is_constructor=False,
                    return_type=_normalize_spaces(match.group(1)),
                    parameters=_parse_heuristic_parameters(match.group(3)),
                    local_variables=[],
                    field_usages=[],
                )
                for match in self._METHOD_PATTERN.finditer(text)
            ]
            types.append(type_info)

        return JavaFileInfo(
            file_path=str(file_path),
            package_name=package_name,
            imports=imports,
            types=types,
            parse_mode=self.parse_mode,
            errors=[],
        )


def select_parser_backend() -> ParserSelection:
    try:
        parser = TreeSitterJavaParser()
        return ParserSelection(
            backend_name="tree-sitter-java",
            parser=parser,
            limitations=[
                "Field usage classification is conservative; unqualified identifiers are treated as heuristic field usages.",
                "Method body analysis does not perform full type resolution across files.",
            ],
        )
    except Exception as exc:
        return ParserSelection(
            backend_name="heuristic-regex-fallback",
            parser=HeuristicJavaParser(),
            limitations=[
                f"AST parser unavailable ({exc!s}); using regex fallback with reduced accuracy.",
                "Fallback mode may miss nested types, local variables, and field usage mapping.",
                "Fallback mode is not reliable for full Java 17 syntax.",
            ],
        )


def analyze_source_tree(
    source_root: Path,
    package_prefix: str | None = None,
    package_regex: str | None = None,
) -> AnalysisResult:
    if not source_root.exists() or not source_root.is_dir():
        raise FileNotFoundError(f"Source root does not exist or is not a directory: {source_root}")

    selection = select_parser_backend()
    parser = selection.parser
    java_files = sorted(source_root.rglob("*.java"), key=lambda path: str(path).lower())
    parsed_files: list[JavaFileInfo] = []
    parse_failures = 0
    regex = re.compile(package_regex) if package_regex else None

    for file_path in java_files:
        try:
            parsed = parser.parse_file(file_path)
        except Exception as exc:
            parse_failures += 1
            parsed = JavaFileInfo(
                file_path=str(file_path),
                package_name="",
                imports=[],
                types=[],
                parse_mode=parser.parse_mode,
                errors=[f"Failed to parse file: {exc!s}"],
            )

        filtered_types = [
            type_info
            for type_info in parsed.types
            if _package_matches(type_info.package_name, prefix=package_prefix, regex=regex)
        ]

        package_matches = _package_matches(parsed.package_name, prefix=package_prefix, regex=regex)
        if filtered_types or package_matches:
            parsed.types = filtered_types
            parsed_files.append(parsed)

    return AnalysisResult(
        scanned_files=len(java_files),
        parsed_files=len(parsed_files),
        parse_failures=parse_failures,
        java_files=parsed_files,
        parser_backend=selection.backend_name,
        limitations=selection.limitations,
    )


def _package_matches(package_name: str, prefix: str | None, regex: re.Pattern[str] | None) -> bool:
    if prefix:
        if package_name != prefix and not package_name.startswith(f"{prefix}."):
            return False
    if regex:
        if not regex.search(package_name):
            return False
    return True


def _walk_for_types(
    root,
    source: bytes,
    package_name: str,
    enclosing_types: list[str],
    sink: list[TypeInfo],
) -> None:
    if root.type in TYPE_DECLARATION_KINDS:
        type_info = _parse_type_declaration(
            node=root,
            source=source,
            package_name=package_name,
            enclosing_types=enclosing_types,
        )
        sink.append(type_info)
        body = root.child_by_field_name("body")
        if body:
            next_enclosing = [*enclosing_types, type_info.simple_name]
            for child in body.named_children:
                _walk_for_types(child, source, package_name, next_enclosing, sink)
        return

    for child in root.named_children:
        _walk_for_types(child, source, package_name, enclosing_types, sink)


def _parse_type_declaration(node, source: bytes, package_name: str, enclosing_types: list[str]) -> TypeInfo:
    kind = TYPE_DECLARATION_KINDS[node.type]
    name_node = node.child_by_field_name("name")
    simple_name = _node_text(source, name_node) if name_node else "<anonymous>"
    type_info = TypeInfo(
        kind=kind,
        package_name=package_name,
        simple_name=simple_name,
        enclosing_types=list(enclosing_types),
    )

    body = node.child_by_field_name("body")
    if not body:
        return type_info

    fields: list[FieldInfo] = []
    methods: list[MethodInfo] = []

    for member in body.named_children:
        if member.type in {"field_declaration", "constant_declaration"}:
            fields.extend(_parse_field_declaration(member, source))
        elif member.type == "method_declaration":
            methods.append(_parse_method_declaration(member, source, fields))
        elif member.type in {"constructor_declaration", "compact_constructor_declaration"}:
            methods.append(_parse_constructor_declaration(member, source, fields, simple_name))

    type_info.fields = fields
    type_info.methods = methods
    return type_info


def _parse_field_declaration(node, source: bytes) -> list[FieldInfo]:
    type_node = node.child_by_field_name("type")
    type_name = _normalize_type_text(_node_text(source, type_node)) if type_node else "unknown"

    fields: list[FieldInfo] = []
    for declarator in node.named_children:
        if declarator.type != "variable_declarator":
            continue
        name_node = declarator.child_by_field_name("name")
        if not name_node:
            continue
        fields.append(FieldInfo(name=_node_text(source, name_node), type_name=type_name))
    return fields


def _parse_method_declaration(node, source: bytes, fields: list[FieldInfo]) -> MethodInfo:
    name_node = node.child_by_field_name("name")
    method_name = _node_text(source, name_node) if name_node else "<anonymous>"
    return_type_node = node.child_by_field_name("type")
    return_type = _normalize_type_text(_node_text(source, return_type_node)) if return_type_node else "void"
    parameters = _parse_parameters(node.child_by_field_name("parameters"), source)
    body = node.child_by_field_name("body")
    local_variables = _collect_local_variables(body, source) if body else []
    field_usages = _collect_field_usages(
        body=body,
        source=source,
        class_fields=fields,
        parameters=parameters,
        local_variables=local_variables,
    )
    return MethodInfo(
        name=method_name,
        is_constructor=False,
        return_type=return_type,
        parameters=parameters,
        local_variables=local_variables,
        field_usages=field_usages,
    )


def _parse_constructor_declaration(node, source: bytes, fields: list[FieldInfo], fallback_name: str) -> MethodInfo:
    name_node = node.child_by_field_name("name")
    constructor_name = _node_text(source, name_node) if name_node else fallback_name
    parameters = _parse_parameters(node.child_by_field_name("parameters"), source)
    body = node.child_by_field_name("body")
    local_variables = _collect_local_variables(body, source) if body else []
    field_usages = _collect_field_usages(
        body=body,
        source=source,
        class_fields=fields,
        parameters=parameters,
        local_variables=local_variables,
    )
    return MethodInfo(
        name=constructor_name,
        is_constructor=True,
        return_type=None,
        parameters=parameters,
        local_variables=local_variables,
        field_usages=field_usages,
    )


def _parse_parameters(parameters_node, source: bytes) -> list[ParameterInfo]:
    if not parameters_node:
        return []
    parameters: list[ParameterInfo] = []
    for child in parameters_node.named_children:
        if child.type not in {"formal_parameter", "spread_parameter", "receiver_parameter"}:
            continue
        name_node = child.child_by_field_name("name")
        type_node = child.child_by_field_name("type")
        if not name_node:
            continue
        parameters.append(
            ParameterInfo(
                name=_node_text(source, name_node),
                type_name=_normalize_type_text(_node_text(source, type_node)) if type_node else "unknown",
            )
        )
    return parameters


def _collect_local_variables(body_node, source: bytes) -> list[str]:
    if not body_node:
        return []
    locals_found: list[str] = []
    for node in _walk_named_nodes(body_node):
        if node.type != "local_variable_declaration":
            continue
        for child in node.named_children:
            if child.type != "variable_declarator":
                continue
            name_node = child.child_by_field_name("name")
            if name_node:
                locals_found.append(_node_text(source, name_node))
    return sorted(set(locals_found))


def _collect_field_usages(
    body,
    source: bytes,
    class_fields: list[FieldInfo],
    parameters: list[ParameterInfo],
    local_variables: list[str],
) -> list[FieldUsage]:
    if not body:
        return []

    field_names = {field.name for field in class_fields}
    if not field_names:
        return []

    # Local symbols shadow fields; unqualified matches are treated as suspicious only when not shadowed.
    local_names = {param.name for param in parameters} | set(local_variables)
    usages: dict[tuple[str, str], FieldUsage] = {}

    for node in _walk_named_nodes(body):
        if node.type != "identifier":
            continue
        identifier = _node_text(source, node)
        if identifier not in field_names:
            continue
        if _is_declaration_identifier(node):
            continue

        explicit_field = _is_explicit_this_or_super_field(node, source)
        if _is_other_object_field(node, source):
            continue
        if identifier in local_names and not explicit_field:
            continue

        access_kind = "write" if _is_write_usage(node) else "read"
        # Explicit `this.field`/`super.field` access is stronger evidence than unqualified identifiers.
        confidence = "exact" if explicit_field else "heuristic"
        key = (identifier, access_kind)
        candidate = FieldUsage(
            field_name=identifier,
            access_kind=access_kind,
            confidence=confidence,
            evidence=f"node={node.parent.type if node.parent else 'identifier'}",
        )
        previous = usages.get(key)
        if previous is None or (previous.confidence == "heuristic" and candidate.confidence == "exact"):
            usages[key] = candidate

    return sorted(usages.values(), key=lambda usage: (usage.field_name, usage.access_kind, usage.confidence))


def _is_declaration_identifier(node) -> bool:
    parent = node.parent
    if not parent:
        return False
    if parent.type == "variable_declarator" and parent.child_by_field_name("name") == node:
        return True
    if parent.type in {"formal_parameter", "spread_parameter", "receiver_parameter"} and parent.child_by_field_name(
        "name"
    ) == node:
        return True
    return False


def _is_write_usage(node) -> bool:
    current = node
    parent = node.parent
    while parent and parent.type in {"parenthesized_expression", "field_access", "array_access"}:
        current = parent
        parent = parent.parent
    if not parent:
        return False

    if parent.type == "assignment_expression":
        left = parent.child_by_field_name("left")
        if left is None and parent.named_children:
            left = parent.named_children[0]
        return left is not None and _contains(left, current)
    if parent.type == "update_expression":
        return True
    return False


def _is_explicit_this_or_super_field(node, source: bytes) -> bool:
    parent = node.parent
    if not parent or parent.type != "field_access":
        return False
    field_node = parent.child_by_field_name("field")
    if field_node != node:
        return False
    object_node = parent.child_by_field_name("object")
    if not object_node:
        return False
    object_name = _node_text(source, object_node)
    return object_name in {"this", "super"}


def _is_other_object_field(node, source: bytes) -> bool:
    parent = node.parent
    if not parent or parent.type != "field_access":
        return False
    field_node = parent.child_by_field_name("field")
    if field_node != node:
        return False
    object_node = parent.child_by_field_name("object")
    if not object_node:
        return False
    object_name = _node_text(source, object_node)
    return object_name not in {"this", "super"}


def _contains(container, child) -> bool:
    return container.start_byte <= child.start_byte and container.end_byte >= child.end_byte


def _extract_package_name(root, source: bytes) -> str:
    for node in root.named_children:
        if node.type != "package_declaration":
            continue
        name_node = node.child_by_field_name("name")
        if name_node:
            return _node_text(source, name_node)
        text = _node_text(source, node)
        text = text.removeprefix("package").strip().rstrip(";").strip()
        return _normalize_spaces(text)
    return ""


def _extract_imports(root, source: bytes) -> list[str]:
    imports: list[str] = []
    for node in root.named_children:
        if node.type != "import_declaration":
            continue
        text = _node_text(source, node)
        text = text.removeprefix("import").strip().rstrip(";").strip()
        imports.append(_normalize_spaces(text))
    return imports


def _walk_named_nodes(node) -> Iterable:
    yield node
    for child in node.named_children:
        yield from _walk_named_nodes(child)


def _node_text(source: bytes, node) -> str:
    if not node:
        return ""
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _normalize_type_text(type_text: str) -> str:
    if not type_text:
        return "unknown"
    compact = _normalize_spaces(type_text)
    compact = compact.replace(" ,", ",")
    compact = compact.replace(" <", "<").replace("< ", "<")
    compact = compact.replace(" >", ">").replace("> ", ">")
    return compact


def _normalize_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _parse_heuristic_parameters(raw: str) -> list[ParameterInfo]:
    raw = raw.strip()
    if not raw:
        return []
    parameters: list[ParameterInfo] = []
    for idx, chunk in enumerate(raw.split(","), start=1):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = chunk.split()
        if len(parts) == 1:
            parameters.append(ParameterInfo(name=f"arg{idx}", type_name=_normalize_spaces(parts[0])))
            continue
        parameters.append(ParameterInfo(name=parts[-1], type_name=_normalize_spaces(" ".join(parts[:-1]))))
    return parameters
