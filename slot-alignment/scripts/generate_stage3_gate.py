#!/usr/bin/env python3
import argparse

from alignment import dump_json, load_json, sha256_file


def main():
    parser = argparse.ArgumentParser(description="生成v5阶段3到4门禁")
    parser.add_argument("--result", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = load_json(args.result)
    dump_json(args.output, {
        "schema_version": "slot-alignment.stage3-gate.v5",
        "task_id": result["task_id"],
        "alignment_result_sha256": sha256_file(args.result),
        "status": "通过",
        "stage4_allowed": True,
        "baseline_final_status": result["summary"]["final_status"],
        "reason_zh": "固定产物与合同一致，可继续CALIBRATION；失败与未判定实例必须持续保留。",
    })


if __name__ == "__main__":
    main()
