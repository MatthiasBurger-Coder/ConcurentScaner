from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

TypeKind = Literal["class", "interface", "enum", "record"]
ParseMode = Literal["ast", "heuristic"]
FieldAccessKind = Literal["read", "write"]
Confidence = Literal["exact", "heuristic"]
RuleLocation = Literal["ENTRY", "EXIT", "READ", "WRITE"]


@dataclass(frozen=True)
class ParameterInfo:
    name: str
    type_name: str


@dataclass(frozen=True)
class FieldUsage:
    field_name: str
    access_kind: FieldAccessKind
    confidence: Confidence
    evidence: str


@dataclass
class MethodInfo:
    name: str
    is_constructor: bool
    return_type: str | None
    parameters: list[ParameterInfo] = field(default_factory=list)
    local_variables: list[str] = field(default_factory=list)
    field_usages: list[FieldUsage] = field(default_factory=list)

    @property
    def signature(self) -> str:
        param_types = ",".join(param.type_name for param in self.parameters)
        if self.is_constructor:
            return f"<init>({param_types})"
        return f"{self.name}({param_types})"

    @property
    def display_name(self) -> str:
        param_types = ",".join(param.type_name for param in self.parameters)
        return f"{self.name}({param_types})"


@dataclass
class FieldInfo:
    name: str
    type_name: str


@dataclass
class TypeInfo:
    kind: TypeKind
    package_name: str
    simple_name: str
    enclosing_types: list[str] = field(default_factory=list)
    fields: list[FieldInfo] = field(default_factory=list)
    methods: list[MethodInfo] = field(default_factory=list)

    @property
    def qualified_name(self) -> str:
        nesting = "$".join([*self.enclosing_types, self.simple_name]).strip("$")
        if self.package_name:
            return f"{self.package_name}.{nesting}"
        return nesting


@dataclass
class JavaFileInfo:
    file_path: str
    package_name: str
    imports: list[str]
    types: list[TypeInfo]
    parse_mode: ParseMode
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AnalysisResult:
    scanned_files: int
    parsed_files: int
    parse_failures: int
    java_files: list[JavaFileInfo]
    parser_backend: str
    limitations: list[str] = field(default_factory=list)

    @property
    def discovered_types(self) -> int:
        return sum(len(file_info.types) for file_info in self.java_files)

    @property
    def discovered_methods(self) -> int:
        return sum(len(type_info.methods) for file_info in self.java_files for type_info in file_info.types)

    @property
    def discovered_fields(self) -> int:
        return sum(len(type_info.fields) for file_info in self.java_files for type_info in file_info.types)

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["discovered_types"] = self.discovered_types
        payload["discovered_methods"] = self.discovered_methods
        payload["discovered_fields"] = self.discovered_fields
        return payload


@dataclass(frozen=True)
class RuleDefinition:
    name: str
    class_name: str
    method_signature: str
    location: RuleLocation
    action: str
    field_name: str | None = None
