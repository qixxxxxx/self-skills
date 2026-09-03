#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

from alignment import load_json, sha256_file
from validate_workspace_layout import validate_task


def main():
    parser = argparse.ArgumentParser(description="校验slot-alignment 7.0 FORMAL交付")
    parser.add_argument("--task-root", required=True)
    args = parser.parse_args()
    task_root = Path(args.task_root).resolve()
    errors = validate_task(task_root, 4)
    if errors:
        print("\n".join(f"ERROR: {item}" for item in errors), file=sys.stderr)
        raise SystemExit(1)

    preflight = load_json(task_root / "artifacts/preflight.json")
    contract = load_json(task_root / "artifacts/metric_contract.json")
    manifest = load_json(task_root / "artifacts/alignment_manifest.json")
    formal = load_json(task_root / "artifacts/formal_result.json")
    delivery = load_json(task_root / "artifacts/delivery_manifest.json")
    execution = formal["execution"]
    selected = manifest["selected_candidate"]
    selected_files = {item["name"]: item["sha256"] for item in selected["runtime_files"]}

    checks = {
        "same_certified_script": (
            preflight["certified_script"]["sha256"]
            == contract["hashes"]["script_sha256"]
            == manifest["certified_script_sha256"]
            == execution["certified_script_sha256"]
            == delivery["certified_script_sha256"]
        ),
        "same_metric_contract": (
            manifest["metric_contract_sha256"]
            == formal["metric_contract_sha256"]
            == delivery["metric_contract_sha256"]
            == sha256_file(task_root / "artifacts/metric_contract.json")
        ),
        "formal_independent_seed": execution["independent_seed"] is True,
        "runtime_files_match": all(
            item["source_sha256"] == item["delivery_sha256"] == selected_files.get(item["name"])
            for item in delivery["runtime_files"]
        ),
        "runtime_version_matches_task_id": delivery["runtime_version"] == task_root.name,
        "rtp_group_is_one": delivery["rtp_group"] == 1,
    }
    if checks != delivery["checks"]:
        raise SystemExit(f"delivery_manifest.checks与实际结果不一致: {checks}")
    if not (
        delivery["source_runtime_bundle_sha256"]
        == delivery["delivery_runtime_bundle_sha256"]
        == execution["runtime_bundle_sha256"]
        == selected["runtime_bundle_sha256"]
    ):
        raise SystemExit("候选、FORMAL和交付Runtime bundle不一致")
    game_core = load_json(task_root / "交付物/runtime/game_core.json")
    if game_core.get("meta", {}).get("version") != task_root.name:
        raise SystemExit("game_core.json.meta.version必须等于task_id")
    print("OK: FORMAL与交付Runtime、认证脚本和指标合同一致")


if __name__ == "__main__":
    main()
