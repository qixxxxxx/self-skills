#!/usr/bin/env python3
import argparse
import hashlib
import json
import sys
from pathlib import Path


FIELDS = (
    "seed_set_sha256",
    "rng_call_sequence_sha256",
    "semantic_entries",
    "total_rtp",
    "component_rtp",
    "key_metrics",
)


def load(path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def canonical_sha(value):
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(payload).hexdigest()


def main():
    parser = argparse.ArgumentParser(description="比较用户认证原始脚本与观测/输出派生脚本的确定性语义快照")
    parser.add_argument("--certified", required=True, type=Path)
    parser.add_argument("--execution", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        certified = load(args.certified)
        execution = load(args.execution)
        repair_attempts = []
        if args.output.exists():
            previous = load(args.output)
            if isinstance(previous.get("repair_attempts"), list):
                repair_attempts = previous["repair_attempts"]
        differences = []
        for field in FIELDS:
            if field not in certified or field not in execution:
                differences.append({"field": field, "reason": "缺少必需语义快照字段"})
            elif certified[field] != execution[field]:
                differences.append({
                    "field": field,
                    "reason": "原始与派生结果不一致",
                    "certified_sha256": canonical_sha(certified[field]),
                    "execution_sha256": canonical_sha(execution[field]),
                })
        source_sha = certified.get("script_sha256", "")
        execution_sha = execution.get("script_sha256", "")
        if not isinstance(source_sha, str) or len(source_sha) != 64:
            differences.append({"field": "certified.script_sha256", "reason": "原始脚本hash无效"})
        if not isinstance(execution_sha, str) or len(execution_sha) != 64:
            differences.append({"field": "execution.script_sha256", "reason": "派生脚本hash无效"})
        checks = {
            "same_seed_bet_payout_state_match": not any(x["field"] in {"seed_set_sha256", "semantic_entries"} for x in differences),
            "rng_call_order_match": not any(x["field"] == "rng_call_sequence_sha256" for x in differences),
            "total_rtp_match": not any(x["field"] == "total_rtp" for x in differences),
            "component_rtp_match": not any(x["field"] == "component_rtp" for x in differences),
            "key_metric_match": not any(x["field"] == "key_metrics" for x in differences),
        }
        result = {
            "status": "通过" if not differences else "不通过",
            "validation_method": "deterministic_same_seed_and_statistical",
            "change_scope": "observation_output_only",
            "source_certified_script_sha256": source_sha,
            "execution_script_sha256": execution_sha,
            "checks": checks,
            "differences": differences,
            "repair_required": bool(differences),
            "repair_instruction": "读取differences，仅修正观测/输出实现后重新生成派生快照并重跑；不得请求用户重新认证。" if differences else "无需修复",
            "repair_attempts": repair_attempts + [{
                "attempt": len(repair_attempts) + 1,
                "status": "通过" if not differences else "不通过",
                "difference_fields": [item["field"] for item in differences],
            }],
        }
        result["evidence_sha256"] = canonical_sha(result)
        result["evidence_path"] = str(args.output)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": result["status"], "output": str(args.output), "difference_count": len(differences)}, ensure_ascii=False))
        return 0 if not differences else 1
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "失败", "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
