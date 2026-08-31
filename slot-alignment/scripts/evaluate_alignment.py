#!/usr/bin/env python3
import argparse
from pathlib import Path

from alignment import dump_json, evaluate_contract, load_json, sha256_file


ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description="计算slot-alignment v5逐卡判定")
    parser.add_argument("--contract", required=True)
    parser.add_argument("--measurements", required=True)
    parser.add_argument("--phase", choices=["BASELINE", "CALIBRATION", "FORMAL"], required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    contract = load_json(args.contract)
    measurements = load_json(args.measurements)
    expected = measurements.get("metric_contract_sha256")
    actual = sha256_file(args.contract)
    if expected and expected != actual:
        raise SystemExit("测量文件绑定的metric_contract_sha256与当前合同不一致")
    policy_binding = contract["policies"]["alignment_evaluation"]
    policy_path = ROOT / policy_binding["path"]
    if sha256_file(policy_path) != policy_binding["sha256"]:
        raise SystemExit("指标合同绑定的评价政策SHA-256与当前文件不一致")
    policy = load_json(policy_path)
    dump_json(args.output, evaluate_contract(contract, measurements, args.phase, actual, policy))


if __name__ == "__main__":
    main()
