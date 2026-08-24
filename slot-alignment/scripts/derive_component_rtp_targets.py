#!/usr/bin/env python3
import argparse
import json
import math
import sys
from pathlib import Path


METHOD = "original_component_share_mapped_to_authoritative_total_rtp"


def load(path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def normalize_target(value):
    if isinstance(value, (int, float)):
        return float(value), float(value), "point"
    if isinstance(value, list) and len(value) == 2:
        return float(value[0]), float(value[1]), "range"
    if isinstance(value, dict) and "min" in value and "max" in value:
        return float(value["min"]), float(value["max"]), "object"
    raise ValueError("authoritative_total_rtp_target必须是数值、[min,max]或{min,max}")


def render_target(low, high, target_type):
    if target_type == "point":
        return low
    if target_type == "object":
        return {"min": low, "max": high}
    return [low, high]


def derive(data):
    total_low, total_high, target_type = normalize_target(data["authoritative_total_rtp_target"])
    components = data.get("components", [])
    if not components:
        raise ValueError("components不能为空")
    shares = [float(item["original_component_share"]) for item in components]
    if any(share < 0 or share > 1 for share in shares):
        raise ValueError("original_component_share必须位于[0,1]")
    share_sum = sum(shares)
    if not math.isclose(share_sum, 1.0, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError(f"组件贡献占比合计必须为1，当前为{share_sum}")
    result_components = []
    for item, share in zip(components, shares):
        result_components.append({
            "metric_id": item.get("metric_id", "core.rtp.component_contribution"),
            "scope": item["scope"],
            "target": render_target(share * total_low, share * total_high, target_type),
            "target_derivation": {
                "method": METHOD,
                "original_component_share": share,
                "source_evidence": item.get("source_evidence", "")
            }
        })
    return {
        "schema_version": "slot-alignment.component-rtp-targets.v1",
        "method": METHOD,
        "authoritative_total_rtp_target": data["authoritative_total_rtp_target"],
        "original_absolute_rtp_as_target": False,
        "share_sum": share_sum,
        "components": result_components
    }


def main():
    parser = argparse.ArgumentParser(description="按原版组件贡献占比映射权威总RTP目标")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = derive(load(args.input))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": "通过", "output": str(args.output)}, ensure_ascii=False))
        return 0
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "失败", "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
