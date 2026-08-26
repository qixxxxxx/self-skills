#!/usr/bin/env python3
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path


def load(path):
    with Path(path).open(encoding="utf-8") as stream:
        return json.load(stream)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical_sha256(value):
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def positive(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{label}必须是有限正数")
    return float(value)


def score_anchor_threshold(contract, policy, skill_root=None):
    metric_id = policy["hit_rate_threshold"]["metric_id"]
    anchor_score = policy["hit_rate_threshold"]["anchor_score"]
    values = []
    for metric in contract.get("metrics", []):
        if metric.get("metric_id") != metric_id:
            continue
        for anchor in metric.get("score_profile", {}).get("anchors", []):
            if isinstance(anchor, list) and len(anchor) == 2 and anchor[1] == anchor_score:
                values.append(positive(anchor[0], f"{metric_id}的{anchor_score}分距离锚点"))
    if not values and skill_root is not None:
        for path in sorted(Path(skill_root).glob("references/指标目录/**/catalog.json")):
            for metric in load(path).get("metrics", []):
                if metric.get("metric_id") != metric_id:
                    continue
                for anchor in metric.get("score_profile", {}).get("anchors", []):
                    if isinstance(anchor, list) and len(anchor) == 2 and anchor[1] == anchor_score:
                        values.append(positive(anchor[0], f"{metric_id}的{anchor_score}分距离锚点"))
    if not values or any(not math.isclose(value, values[0], rel_tol=0, abs_tol=1e-12) for value in values):
        raise ValueError(f"无法从{metric_id}唯一解析{anchor_score}分距离锚点")
    return values[0]


def component_rtp_threshold(contract, policy):
    metric_id = policy["rtp_contribution_threshold"]["metric_id"]
    values = [
        positive(metric.get("hard_gate_profile", {}).get("tolerance"), f"{metric_id}生效容差")
        for metric in contract.get("metrics", [])
        if metric.get("metric_id") == metric_id and metric.get("status") != "不适用"
    ]
    if not values:
        raise ValueError(f"合同缺少活动{metric_id}生效容差")
    return min(values)


def classifications(profile, hit_threshold, rtp_threshold):
    result = []
    for node in profile.get("mechanics", []):
        if node.get("status") not in {"必需", "适用"} or node.get("mechanic_id") != "award.jackpot":
            continue
        rows = node.get("attributes", {}).get("jackpot_tier_exposure")
        if not isinstance(rows, list) or not rows:
            raise ValueError(f"Jackpot节点缺少jackpot_tier_exposure: {node.get('node_id')}")
        grouped = {}
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError(f"Jackpot层级暴露存在非对象项: {node.get('node_id')}")
            opportunities = row.get("original_opportunity_count")
            hits = row.get("original_hit_count")
            rtp = row.get("original_rtp_contribution")
            if (
                not isinstance(opportunities, int) or isinstance(opportunities, bool) or opportunities < 1
                or not isinstance(hits, int) or isinstance(hits, bool) or hits < 0 or hits > opportunities
                or isinstance(rtp, bool) or not isinstance(rtp, (int, float)) or not math.isfinite(rtp) or rtp < 0
            ):
                raise ValueError(f"Jackpot层级暴露数值无效: {node.get('node_id')} / {row.get('tier_id')}")
            grouped.setdefault(row.get("opportunity_set_id"), []).append(row)
        for opportunity_set_id, group in sorted(grouped.items()):
            denominators = {row["original_opportunity_count"] for row in group}
            if not isinstance(opportunity_set_id, str) or not opportunity_set_id or len(denominators) != 1:
                raise ValueError(f"Jackpot机会集ID或统一分母无效: {node.get('node_id')} / {opportunity_set_id}")
            opportunity_count = next(iter(denominators))
            if sum(row["original_hit_count"] for row in group) > opportunity_count:
                raise ValueError(f"Jackpot机会集逐层命中数合计超过机会数: {node.get('node_id')} / {opportunity_set_id}")
            tier_rows, material, non_material = [], [], []
            for row in sorted(group, key=lambda item: item["tier_id"]):
                hit_rate = row["original_hit_count"] / row["original_opportunity_count"]
                is_material = hit_rate >= hit_threshold or row["original_rtp_contribution"] >= rtp_threshold
                tier_rows.append({
                    "tier_id": row["tier_id"],
                    "hit_rate": hit_rate,
                    "original_hit_count": row["original_hit_count"],
                    "original_rtp_contribution": row["original_rtp_contribution"],
                    "material": is_material,
                    "evidence_sha256": row["evidence_sha256"],
                })
                (material if is_material else non_material).append(row["tier_id"])
            result.append({
                "jackpot_node_id": node["node_id"],
                "opportunity_set_id": opportunity_set_id,
                "original_opportunity_count": opportunity_count,
                "material_tier_ids": material,
                "non_material_tier_ids": non_material,
                "tier_exposure": tier_rows,
            })
    return result


def embedded_policy(contract, profile, source_policy, source_path, source_sha256, skill_root=None):
    hit_threshold = score_anchor_threshold(contract, source_policy, skill_root)
    rtp_threshold = component_rtp_threshold(contract, source_policy)
    rows = classifications(profile, hit_threshold, rtp_threshold)
    return {
        "source_schema_version": source_policy["schema_version"],
        "policy_id": source_policy["policy_id"],
        "version": source_policy["version"],
        "source_path": source_path,
        "source_sha256": source_sha256,
        "hit_rate_threshold": hit_threshold,
        "component_rtp_tolerance_threshold": rtp_threshold,
        "classification_rule": source_policy["classification_rule"],
        "classifications": rows,
        "classifications_sha256": canonical_sha256(rows),
        "legacy_contracts_unchanged": bool(source_policy.get("legacy_contracts_unchanged")),
    }


def validate_policy_source_binding(contract, profile, skill_root):
    sealed = contract.get("jackpot_materiality_policy")
    if not isinstance(sealed, dict):
        return ["合同缺少jackpot_materiality_policy"]
    source = sealed.get("source_path")
    if not isinstance(source, str) or not source or Path(source).is_absolute():
        return ["Jackpot物质性政策来源路径无效"]
    root = Path(skill_root).resolve()
    path = (root / source).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        return ["Jackpot物质性政策来源越出Skill目录"]
    if not path.is_file() or sha(path) != sealed.get("source_sha256"):
        return ["Jackpot物质性政策来源不存在或hash失效"]
    try:
        expected = embedded_policy(contract, profile, load(path), source, sha(path), root)
    except (KeyError, TypeError, ValueError) as exc:
        return [str(exc)]
    return [] if sealed == expected else ["Jackpot物质性政策或分类结果无法确定性复算"]


def main():
    parser = argparse.ArgumentParser(description="按既有评分分辨率确定Jackpot物质性层级")
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--game-profile", required=True, type=Path)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    contract, profile, policy = load(args.contract), load(args.game_profile), load(args.policy)
    source_path = policy.get("source_path", f"assets/policies/{args.policy.name}")
    skill_root = args.policy.resolve().parents[2]
    contract["jackpot_materiality_policy"] = embedded_policy(contract, profile, policy, source_path, sha(args.policy), skill_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "通过", "output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "失败", "error": str(exc)}, ensure_ascii=False))
        sys.exit(2)
