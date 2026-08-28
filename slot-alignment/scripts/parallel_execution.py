#!/usr/bin/env python3
import argparse
import json
import math
import os
import sys
from pathlib import Path


DEFAULT_CPU_FRACTION = 0.7


def available_cpu_count():
    try:
        count = len(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        count = os.cpu_count()
    return max(1, int(count or 1))


def _positive_int(value, name):
    if isinstance(value, bool):
        raise ValueError(f"{name}必须是正整数")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name}必须是正整数") from exc
    if result < 1 or str(value).strip() not in {str(result), f"+{result}"}:
        raise ValueError(f"{name}必须是正整数")
    return result


def resolve_worker_count(requested="auto", cpu_count=None, fraction=DEFAULT_CPU_FRACTION):
    if not isinstance(fraction, (int, float)) or isinstance(fraction, bool) or not math.isfinite(fraction) or not 0 < fraction <= 1:
        raise ValueError("cpu_fraction必须是0到1之间的有限数值")
    if isinstance(requested, str) and requested.strip().lower() == "auto":
        cpus = _positive_int(available_cpu_count() if cpu_count is None else cpu_count, "cpu_count")
        return max(1, math.floor(cpus * fraction))
    return _positive_int(requested, "workers")


def build_sample_shards(total_entries, shard_count):
    total = _positive_int(total_entries, "total_entries")
    count = min(total, _positive_int(shard_count, "shard_count"))
    base, remainder = divmod(total, count)
    start, shards = 0, []
    for index in range(count):
        size = base + (1 if index < remainder else 0)
        shards.append({
            "shard_index": index,
            "start_index": start,
            "count": size,
            "end_index_exclusive": start + size,
        })
        start += size
    return shards


def build_execution_plan(total_entries, workers="auto", cpu_count=None, fraction=DEFAULT_CPU_FRACTION, shard_count=None):
    available = available_cpu_count() if cpu_count is None else _positive_int(cpu_count, "cpu_count")
    resolved = resolve_worker_count(workers, available, fraction)
    shards = build_sample_shards(total_entries, resolved if shard_count is None else shard_count)
    return {
        "schema_version": "slot-alignment.parallel-execution-plan.v1",
        "policy_id": "deterministic-single-candidate-sample-sharding-v1",
        "total_entry_count": sum(item["count"] for item in shards),
        "workers_requested": str(workers),
        "available_cpu_count": available,
        "cpu_fraction": fraction,
        "workers_used": min(resolved, len(shards)),
        "shard_count": len(shards),
        "merge_order": "shard_index_ascending",
        "shards": shards,
    }


def main():
    parser = argparse.ArgumentParser(description="生成单候选确定性多Worker样本分片计划")
    parser.add_argument("--total-entries", required=True, type=int)
    parser.add_argument("--workers", default="auto", help="auto或正整数；auto=floor(可用逻辑核心数×70%%)")
    parser.add_argument("--shard-count", type=int, help="复验时固定沿用已密封分片数")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        plan = build_execution_plan(args.total_entries, args.workers, shard_count=args.shard_count)
    except ValueError as exc:
        print(json.dumps({"status": "失败", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    text = json.dumps(plan, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
