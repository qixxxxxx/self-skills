#!/usr/bin/env python3
"""验收 metric_contract 1.4 的体积、展开等价与冷/热加载性能。"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path

from compact_metric_contract import write_compact_contract
from contract_io import clear_contract_cache, load_contract, load_json_strict


def elapsed_load(path, skill_root, repetitions, clear_each):
    values = []
    if not clear_each:
        clear_contract_cache()
        load_contract(path, skill_root)
    for _ in range(repetitions):
        if clear_each:
            clear_contract_cache()
        start = time.perf_counter()
        load_contract(path, skill_root)
        values.append(time.perf_counter() - start)
    return statistics.median(values)


def main():
    parser = argparse.ArgumentParser(description="验收紧凑指标合同体积与加载性能")
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--baseline-contract", type=Path, help="1.4输入用于体积与语义对比的1.3基线")
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--skill-root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.repetitions < 1:
        raise ValueError("repetitions必须是正整数")
    source = load_json_strict(args.contract)
    baseline_size = None
    source_metrics = None
    args.work_dir.mkdir(parents=True, exist_ok=True)
    if source.get("schema_version") == "1.4":
        compact_path = args.contract
        if args.baseline_contract:
            baseline = load_json_strict(args.baseline_contract)
            if baseline.get("schema_version") != "1.3":
                raise ValueError("baseline-contract必须是metric_contract 1.3")
            baseline_size = args.baseline_contract.stat().st_size
            source_metrics = baseline.get("metrics")
    elif source.get("schema_version") == "1.3":
        compact_path = args.work_dir / "metric_contract.json"
        write_compact_contract(source, compact_path, args.skill_root)
        baseline_size = args.contract.stat().st_size
        source_metrics = source.get("metrics")
    else:
        raise ValueError("性能验收只支持metric_contract 1.3或1.4")
    raw_compact = load_json_strict(compact_path)
    external_files = [compact_path.parent / row["path"] for row in raw_compact.get("external_data", [])]
    main_size = compact_path.stat().st_size
    external_size = sum(path.stat().st_size for path in external_files)
    expanded = load_contract(compact_path, args.skill_root)
    equivalent = True
    if source_metrics is not None:
        observed = []
        for metric in expanded.get("metrics", []):
            metric = dict(metric)
            metric.pop("instance_id", None)
            observed.append(metric)
        equivalent = observed == source_metrics
    cold_seconds = elapsed_load(compact_path, args.skill_root, args.repetitions, True)
    cached_seconds = elapsed_load(compact_path, args.skill_root, args.repetitions, False)
    main_ratio = main_size / baseline_size if baseline_size else None
    total_ratio = (main_size + external_size) / baseline_size if baseline_size else None
    checks = {
        "expanded_semantics_equal": equivalent,
        "main_ratio_lte_0_40": main_ratio is None or main_ratio <= 0.40,
        "total_ratio_lte_0_65": total_ratio is None or total_ratio <= 0.65,
        "cold_load_median_lte_5s": cold_seconds <= 5,
        "cached_load_median_lte_0_5s": cached_seconds <= 0.5,
    }
    result = {
        "schema_version": "slot-alignment.contract-io-benchmark.v1",
        "status": "通过" if all(checks.values()) else "阻塞",
        "source": str(args.contract.resolve()),
        "baseline_contract": str(args.baseline_contract.resolve()) if args.baseline_contract else (str(args.contract.resolve()) if source.get("schema_version") == "1.3" else None),
        "compact_contract": str(compact_path.resolve()),
        "sizes": {
            "baseline_bytes": baseline_size,
            "main_bytes": main_size,
            "external_bytes": external_size,
            "main_ratio": main_ratio,
            "total_ratio": total_ratio,
        },
        "timing": {
            "repetitions": args.repetitions,
            "cold_load_median_seconds": cold_seconds,
            "cached_load_median_seconds": cached_seconds,
        },
        "counts": {"metrics": len(expanded.get("metrics", [])), "external_files": len(external_files)},
        "checks": checks,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(0 if result["status"] == "通过" else 2)


if __name__ == "__main__":
    main()
