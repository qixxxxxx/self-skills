#!/usr/bin/env python3
import argparse

from alignment import dump_json, joint_q99_tolerances, load_json


def main():
    parser = argparse.ArgumentParser(description="从原版自对照距离生成v5联合99%容差")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    source = load_json(args.input)
    tolerances, factor = joint_q99_tolerances(source["distances_by_instance"])
    dump_json(args.output, {
        "schema_version": "slot-alignment.joint-self-comparison.v5",
        "quantile": 0.99,
        "joint": True,
        "replicates": len(next(iter(source["distances_by_instance"].values()))),
        "seed": source.get("seed", 0),
        "evidence_sha256": source["evidence_sha256"],
        "joint_factor": factor,
        "tolerances": tolerances,
    })


if __name__ == "__main__":
    main()
