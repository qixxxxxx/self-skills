#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

from alignment import load_json, sha256_file
from compile_metric_contract import contract_digest


ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "assets/policies/workspace_layout_policy.json"
RUNTIME_FILES = ["game_core.json", "payout_config.json", "reel_config.json", "symbol_catalog.json"]


def validate_json(path, schema_path, errors):
    if not path.is_file():
        errors.append(f"缺少文件: {path}")
        return {}
    try:
        value = load_json(path)
    except Exception as exc:
        errors.append(f"JSON读取失败: {path}: {exc}")
        return {}
    for error in Draft202012Validator(load_json(schema_path)).iter_errors(value):
        location = ".".join(map(str, error.absolute_path)) or "$"
        errors.append(f"{path}:{location}: {error.message}")
    return value


def validate_runtime(path, manifest_files, errors, label):
    actual = sorted(item.name for item in path.iterdir() if item.is_file()) if path.is_dir() else []
    if actual != sorted(RUNTIME_FILES):
        errors.append(f"{label}必须且只能包含Runtime四件套")
        return
    by_name = {item["name"]: item for item in manifest_files}
    if list(by_name) != RUNTIME_FILES:
        errors.append(f"{label}清单顺序必须为{RUNTIME_FILES}")
        return
    for name in RUNTIME_FILES:
        if sha256_file(path / name) != by_name[name].get("sha256"):
            errors.append(f"{label}文件SHA-256不一致: {name}")


def validate_candidate_ledger(path, manifest, expected_script_sha256, expected_contract_sha256, errors):
    records = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            errors.append(f"候选账本第{line_number}行不是有效JSON: {exc}")
            continue
        if not isinstance(value, dict):
            errors.append(f"候选账本第{line_number}行必须是JSON对象")
            continue
        records.append(value)
    if len(records) != manifest["candidate_ledger"]["candidate_count"]:
        errors.append("候选账本记录数与alignment_manifest不一致")
    candidate_ids = [item.get("candidate_id") for item in records]
    if None in candidate_ids or len(candidate_ids) != len(set(candidate_ids)):
        errors.append("候选账本candidate_id缺失或重复")
    required = {"candidate_id", "parameter_sha256", "runtime_bundle_sha256", "certified_script_sha256", "metric_contract_sha256"}
    for index, item in enumerate(records, 1):
        missing = sorted(required - set(item))
        if missing:
            errors.append(f"候选账本第{index}条缺少字段: {missing}")
            continue
        if item["certified_script_sha256"] != expected_script_sha256:
            errors.append(f"候选账本第{index}条未使用用户认证脚本")
        if item["metric_contract_sha256"] != expected_contract_sha256:
            errors.append(f"候选账本第{index}条未使用当前指标合同")
    selected = manifest["selected_candidate"]
    selected_records = [item for item in records if item.get("candidate_id") == selected["candidate_id"]]
    if len(selected_records) != 1:
        errors.append("唯一入选候选未在候选账本中出现一次")
    elif any(selected_records[0].get(key) != selected[key] for key in ("parameter_sha256", "runtime_bundle_sha256")):
        errors.append("候选账本中的入选参数或Runtime与alignment_manifest不一致")


def validate_task(task_root, through_stage):
    errors = []
    policy = load_json(POLICY)
    values = {}
    for item in policy["authoritative_artifacts"]:
        if item["stage"] <= through_stage:
            path = task_root / item["path"]
            values[item["path"]] = validate_json(path, ROOT / item["schema"], errors)
    task_ids = {item.get("task_id") for item in values.values() if item.get("task_id")}
    if task_ids and task_ids != {task_root.name}:
        errors.append(f"权威产物task_id与任务目录不一致: {sorted(task_ids)}")

    preflight = values.get("artifacts/preflight.json", {})
    if through_stage >= 1 and preflight:
        validate_runtime(task_root / "work/baseline/runtime", preflight["runtime"]["files"], errors, "密封基线Runtime")
        if preflight["workspace"]["task_root"].rstrip("/").split("/")[-1] != task_root.name:
            errors.append("preflight.workspace.task_root与任务目录名不一致")

    source = values.get("artifacts/source_summary.json", {})
    if through_stage >= 2 and source and preflight and source["task_id"] != preflight["task_id"]:
        errors.append("source_summary与preflight的task_id不一致")

    contract = values.get("artifacts/metric_contract.json", {})
    if through_stage >= 3 and contract:
        contract_path = task_root / "artifacts/metric_contract.json"
        if contract["hashes"]["contract_sha256"] != contract_digest(contract):
            errors.append("metric_contract内部hash不一致")
        expected = {
            "preflight_sha256": sha256_file(task_root / "artifacts/preflight.json"),
            "source_summary_sha256": sha256_file(task_root / "artifacts/source_summary.json"),
        }
        if any(contract["hashes"].get(key) != value for key, value in expected.items()):
            errors.append("metric_contract未绑定当前preflight或source_summary")
        if preflight and (
            contract["hashes"].get("script_sha256") != preflight["certified_script"]["sha256"]
            or contract["hashes"].get("runtime_bundle_sha256") != preflight["runtime"]["bundle_sha256"]
        ):
            errors.append("metric_contract绑定的认证脚本或基线Runtime不一致")

    if through_stage >= 4:
        manifest = values.get("artifacts/alignment_manifest.json", {})
        formal = values.get("artifacts/formal_result.json", {})
        delivery = values.get("artifacts/delivery_manifest.json", {})
        contract_path = task_root / "artifacts/metric_contract.json"
        if manifest and manifest["metric_contract_sha256"] != sha256_file(contract_path):
            errors.append("alignment_manifest未绑定当前指标合同")
        if manifest and preflight and manifest["certified_script_sha256"] != preflight["certified_script"]["sha256"]:
            errors.append("alignment_manifest未绑定用户认证脚本")
        ledger_path = task_root / "work/candidate_ledger.jsonl"
        if manifest and (not ledger_path.is_file() or manifest["candidate_ledger"]["sha256"] != sha256_file(ledger_path)):
            errors.append("候选账本不存在或SHA-256不一致")
        elif manifest:
            validate_candidate_ledger(
                ledger_path,
                manifest,
                preflight.get("certified_script", {}).get("sha256", manifest["certified_script_sha256"]),
                sha256_file(contract_path),
                errors,
            )
        if manifest:
            validate_runtime(task_root / "work/selected/runtime", manifest["selected_candidate"]["runtime_files"], errors, "入选候选Runtime")
        if formal and manifest:
            execution = formal["execution"]
            selected = manifest["selected_candidate"]
            if formal["phase"] != "FORMAL" or execution["independent_seed"] is not True:
                errors.append("formal_result必须是独立FORMAL结果")
            if formal["metric_contract_sha256"] != manifest["metric_contract_sha256"]:
                errors.append("FORMAL与候选使用的指标合同不一致")
            if execution["candidate_id"] != selected["candidate_id"] or execution["runtime_bundle_sha256"] != selected["runtime_bundle_sha256"]:
                errors.append("FORMAL没有使用唯一入选候选Runtime")
            if execution["certified_script_sha256"] != manifest["certified_script_sha256"]:
                errors.append("FORMAL与候选使用的认证脚本不一致")
            if execution["paid_entry_count"] != manifest["formal_plan"]["paid_entry_count"]:
                errors.append("FORMAL实际样本数与冻结计划不一致")
        if delivery and manifest and formal:
            selected = manifest["selected_candidate"]
            if delivery["task_id"] != task_root.name or delivery["runtime_version"] != task_root.name:
                errors.append("交付任务或Runtime版本不正确")
            if delivery["alignment_manifest_sha256"] != sha256_file(task_root / "artifacts/alignment_manifest.json"):
                errors.append("delivery_manifest未绑定当前alignment_manifest")
            if delivery["formal_result_sha256"] != sha256_file(task_root / "artifacts/formal_result.json"):
                errors.append("delivery_manifest未绑定当前formal_result")
            manifest_files = [
                {"name": item["name"], "sha256": item["delivery_sha256"]}
                for item in delivery["runtime_files"]
            ]
            validate_runtime(task_root / "交付物/runtime", manifest_files, errors, "交付Runtime")
            selected_files = {item["name"]: item["sha256"] for item in selected["runtime_files"]}
            for item in delivery["runtime_files"]:
                if item["source_sha256"] != item["delivery_sha256"]:
                    errors.append(f"FORMAL与交付Runtime不一致: {item['name']}")
                if item["source_sha256"] != selected_files.get(item["name"]):
                    errors.append(f"入选候选与交付Runtime不一致: {item['name']}")
            if (
                delivery["source_runtime_bundle_sha256"] != selected["runtime_bundle_sha256"]
                or delivery["delivery_runtime_bundle_sha256"] != selected["runtime_bundle_sha256"]
            ):
                errors.append("候选、FORMAL和交付Runtime bundle不一致")
        report_dir = task_root / "交付物/报告文档"
        reports = list(report_dir.glob("*.md")) if report_dir.is_dir() else []
        if [item.name for item in reports] != ["对齐报告.md"]:
            errors.append("报告目录必须且只能包含对齐报告.md")
    return errors


def main():
    parser = argparse.ArgumentParser(description="校验slot-alignment 7.0轻量工作区")
    parser.add_argument("--task-root", required=True)
    parser.add_argument("--through-stage", type=int, choices=range(1, 5), default=4)
    args = parser.parse_args()
    errors = validate_task(Path(args.task_root).resolve(), args.through_stage)
    if errors:
        print("\n".join(f"ERROR: {item}" for item in errors), file=sys.stderr)
        raise SystemExit(1)
    print(f"OK: 工作区通过阶段{args.through_stage}校验")


if __name__ == "__main__":
    main()
