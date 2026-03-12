from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from byteman_static.inventory import write_inventory_log
from byteman_static.model import AnalysisResult
from byteman_static.parser import analyze_source_tree
from byteman_static.rules import write_byteman_rules


@dataclass(frozen=True)
class GeneratorConfig:
    source_root: Path
    output_dir: Path
    package_prefix: str | None = None
    package_regex: str | None = None
    helper_class: str = "com.example.byteman.RuntimeTraceHelper"
    write_metadata: bool = True


@dataclass(frozen=True)
class GeneratorOutput:
    analysis: AnalysisResult
    byteman_log_path: Path
    rules_path: Path
    metadata_path: Path | None
    generated_rules: int


def run_generator(config: GeneratorConfig) -> GeneratorOutput:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    analysis = analyze_source_tree(
        source_root=config.source_root,
        package_prefix=config.package_prefix,
        package_regex=config.package_regex,
    )

    byteman_log_path = config.output_dir / "Byteman.log"
    rules_path = config.output_dir / "generated-rules.btm"
    write_inventory_log(analysis, byteman_log_path)
    generated_rules = write_byteman_rules(analysis, rules_path, config.helper_class)

    metadata_path: Path | None = None
    if config.write_metadata:
        metadata_path = config.output_dir / "analysis-metadata.json"
        payload = {
            "config": {
                "source_root": str(config.source_root),
                "output_dir": str(config.output_dir),
                "package_prefix": config.package_prefix,
                "package_regex": config.package_regex,
                "helper_class": config.helper_class,
                "write_metadata": config.write_metadata,
            },
            "analysis": analysis.to_dict(),
            "generated_rules": generated_rules,
            "notes": {
                "static_analysis_limits": (
                    "Static analysis identifies structure and suspicious field access hints only. "
                    "Runtime evidence is required for race and deadlock confirmation."
                )
            },
        }
        metadata_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    return GeneratorOutput(
        analysis=analysis,
        byteman_log_path=byteman_log_path,
        rules_path=rules_path,
        metadata_path=metadata_path,
        generated_rules=generated_rules,
    )
