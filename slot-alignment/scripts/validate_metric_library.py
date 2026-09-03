#!/usr/bin/env python3
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

from alignment import load_json


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_CARDS = ["N1", "N2", "N3", "N4", "N5", "N6", "J1", "J2", "J3", "P1", "P2", "B1", "B2"]


def validate_file(path, schema, errors):
    try:
        value = load_json(path)
    except Exception as exc:
        errors.append(f"{path}: {exc}")
        return {}
    for error in Draft202012Validator(load_json(schema)).iter_errors(value):
        location = ".".join(map(str, error.absolute_path)) or "$"
        errors.append(f"{path}:{location}: {error.message}")
    return value


def main():
    errors = []
    library = validate_file(
        ROOT / "references/指标目录/index.json",
        ROOT / "assets/schemas/metric-library.schema.json",
        errors,
    )
    if [item.get("card_id") for item in library.get("cards", [])] != EXPECTED_CARDS:
        errors.append("指标卡顺序或数量不正确")

    policy_schemas = {
        "alignment_evaluation_policy.json": "alignment-evaluation-policy.schema.json",
        "hard_gate_budget_policy.json": "hard-gate-budget-policy.schema.json",
        "target_evidence_policy.json": "target-evidence-policy.schema.json",
        "sample_execution_policy.json": "sample-execution-policy.schema.json",
        "runtime_capability_policy.json": "runtime-capability-policy.schema.json",
        "workspace_layout_policy.json": "workspace-layout-policy.schema.json",
    }
    policies = {}
    for name, schema in policy_schemas.items():
        policies[name] = validate_file(ROOT / "assets/policies" / name, ROOT / "assets/schemas" / schema, errors)
        if policies[name].get("version") != "7.0.0":
            errors.append(f"{name}版本必须为7.0.0")

    workspace = policies.get("workspace_layout_policy.json", {})
    if len(workspace.get("authoritative_artifacts", [])) != 6:
        errors.append("7.0工作区必须只有6份权威机器JSON")
    for item in workspace.get("authoritative_artifacts", []):
        for key in ("schema", "template"):
            if not (ROOT / item[key]).is_file():
                errors.append(f"工作区政策引用不存在: {item[key]}")

    required_scripts = [
        "compile_metric_contract.py",
        "evaluate_alignment.py",
        "render_alignment_report.py",
        "validate_preflight.py",
        "validate_source_summary.py",
        "validate_workspace_layout.py",
        "validate_delivery.py",
    ]
    for name in required_scripts:
        if not (ROOT / "scripts" / name).is_file():
            errors.append(f"缺少工具: scripts/{name}")

    for path in ROOT.rglob("*"):
        if path.is_file() and path.suffix in {".md", ".json", ".py", ".yaml"}:
            text = path.read_text(encoding="utf-8")
            if ("slot-alignment." in text and ".v" + "6" in text) or "6." + "0.0" in text:
                errors.append(f"仍包含旧版本内容: {path.relative_to(ROOT)}")

    if errors:
        print("\n".join(f"ERROR: {item}" for item in errors), file=sys.stderr)
        raise SystemExit(1)
    print("OK: slot-alignment 7.0指标、政策和轻量工作区有效")


if __name__ == "__main__":
    main()
