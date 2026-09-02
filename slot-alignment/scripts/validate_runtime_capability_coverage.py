#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

from alignment import sha256_file


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "assets/schemas/runtime-capability-matrix.schema.json"
POLICY_PATH = ROOT / "assets/policies/runtime_capability_policy.json"
IMPLEMENTATION_LAYERS = ("candidate_generator", "calibration_simulator", "formal_simulator", "optimizer")


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def location(error):
    return ".".join(map(str, error.absolute_path)) or "$"


def cardinality_errors(capability, layer_name, authorized):
    layer = capability[layer_name]
    errors = []
    minimum = authorized.get("min_cardinality")
    maximum = authorized.get("max_cardinality")
    if minimum is not None and layer.get("min_cardinality", minimum) > minimum:
        errors.append(f"{layer_name}最小能力{layer['min_cardinality']}大于授权下限{minimum}")
    if maximum is not None and layer.get("max_cardinality", -1) < maximum:
        errors.append(f"{layer_name}最大能力{layer.get('max_cardinality')}小于授权上限{maximum}")
    return errors


def capability_errors(capability):
    capability_id = capability["capability_id"]
    authorization = capability["authorization"]
    if authorization["status"] != "authorized":
        errors = []
        if not authorization.get("exemption"):
            errors.append("未授权能力必须记录允许的豁免原因")
        if capability["optimizer"]["status"] != "not_applicable":
            errors.append("未授权能力不得暴露给优化器")
        return [f"{capability_id}: {item}" for item in errors]

    errors = []
    for layer_name in ("certified_script", "server_runtime", *IMPLEMENTATION_LAYERS):
        layer = capability[layer_name]
        if layer["status"] != "supported":
            errors.append(f"{layer_name}未完整支持已授权能力")
        errors.extend(cardinality_errors(capability, layer_name, authorization))
    optimizer = capability["optimizer"]
    if not optimizer["exposed_parameters"]:
        errors.append("optimizer.exposed_parameters不能为空")
    if not optimizer["sensitivity_plan_ids"]:
        errors.append("optimizer.sensitivity_plan_ids不能为空")
    equivalence = capability["equivalence"]
    if equivalence["status"] != "passed":
        errors.append("等价验证未通过")
    if equivalence["status"] == "passed" and not equivalence.get("evidence_sha256"):
        errors.append("等价验证通过时必须记录evidence_sha256")
    return [f"{capability_id}: {item}" for item in errors]


def validate_matrix(matrix, matrix_path="runtime-capability-matrix.json"):
    schema = load(SCHEMA_PATH)
    errors = [f"{matrix_path}:{location(error)}: {error.message}" for error in Draft202012Validator(schema).iter_errors(matrix)]
    if errors:
        return errors
    policy = matrix["policy"]
    if policy["sha256"] != sha256_file(POLICY_PATH):
        errors.append("runtime capability policy SHA-256与当前Skill不一致")
    capability_ids = [item["capability_id"] for item in matrix["capabilities"]]
    if len(capability_ids) != len(set(capability_ids)):
        errors.append("capability_id重复")
    missing_capabilities = set(load(POLICY_PATH)["required_capability_ids"]) - set(capability_ids)
    if missing_capabilities:
        errors.append(f"缺少政策要求的能力项: {sorted(missing_capabilities)}")
    authorized = [item for item in matrix["capabilities"] if item["authorization"]["status"] == "authorized"]
    covered = 0
    for capability in matrix["capabilities"]:
        item_errors = capability_errors(capability)
        errors.extend(item_errors)
        if capability["authorization"]["status"] == "authorized" and not item_errors:
            covered += 1
    summary = matrix["summary"]
    expected = {
        "total_capabilities": len(matrix["capabilities"]),
        "authorized_capabilities": len(authorized),
        "fully_covered_capabilities": covered,
        "coverage_status": "通过" if not errors and covered == len(authorized) else "不通过",
    }
    for key, value in expected.items():
        if summary[key] != value:
            errors.append(f"summary.{key}应为{value}，实际为{summary[key]}")
    return errors


def main():
    parser = argparse.ArgumentParser(description="校验认证Runtime、服务端、候选生成器、快速模拟器和优化器的能力覆盖")
    parser.add_argument("--matrix", required=True)
    parser.add_argument("--phase", choices=("PRE_CALIBRATION", "CANDIDATE_FREEZE", "FORMAL"), default="PRE_CALIBRATION")
    args = parser.parse_args()
    matrix = load(args.matrix)
    errors = validate_matrix(matrix, args.matrix)
    if errors:
        print("\n".join(f"ERROR: {item}" for item in errors), file=sys.stderr)
        raise SystemExit(1)
    authorized_count = matrix["summary"]["authorized_capabilities"]
    print(f"OK: {args.phase} Runtime能力覆盖通过，已授权能力{authorized_count}/{authorized_count}")


if __name__ == "__main__":
    main()
