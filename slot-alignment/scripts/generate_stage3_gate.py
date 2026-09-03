#!/usr/bin/env python3
import argparse
from pathlib import Path

from jsonschema import Draft202012Validator

from alignment import dump_json, load_json, sha256_file


ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description="生成6.0阶段3到4门禁")
    parser.add_argument("--result", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = load_json(args.result)
    errors = list(Draft202012Validator(load_json(ROOT / "assets/schemas/alignment-result.schema.json")).iter_errors(result))
    if errors:
        error = errors[0]
        raise SystemExit(f"基线评价结果不符合Schema：{'.'.join(map(str, error.absolute_path)) or '$'}: {error.message}")
    if result["phase"] != "BASELINE":
        raise SystemExit("阶段3门禁只能由BASELINE评价结果生成")
    dump_json(args.output, {
        "schema_version": "slot-alignment.stage3-gate.v6",
        "task_id": result["task_id"],
        "alignment_result_sha256": sha256_file(args.result),
        "status": "通过",
        "stage4_allowed": True,
        "baseline_final_status": result["summary"]["final_status"],
        "baseline_conclusion": result["summary"]["conclusion"],
        "coverage_status": result["summary"]["coverage_status"],
        "reason_zh": "固定产物与合同一致，可继续CALIBRATION；观察项、失败项与未判定项必须持续保留。",
    })


if __name__ == "__main__":
    main()
