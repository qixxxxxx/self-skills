#!/usr/bin/env python3
import argparse
import json
import re
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

from alignment import canonical_json_sha256, sha256_file
from compile_metric_contract import contract_digest
from validate_delivery import validate_delivery


ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "assets/policies/workspace_layout_policy.json"
POLICY_SCHEMA_PATH = ROOT / "assets/schemas/workspace-layout-policy.schema.json"
RUNTIME_FILES = ["game_core.json", "payout_config.json", "reel_config.json", "symbol_catalog.json"]
SHARD_RE = re.compile(r"^shard-([0-9]{6})\.json$")


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def file_sha256(path):
    path = Path(path)
    return sha256_file(path) if path.is_file() else None


def validate_json(path, schema_path, errors):
    if not path.is_file():
        errors.append(f"缺少文件: {path}")
        return None
    try:
        data = load(path)
    except Exception as exc:
        errors.append(f"JSON无法解析: {path}: {exc}")
        return None
    schema = load(schema_path)
    schema_issues = list(Draft202012Validator(schema).iter_errors(data))
    for error in schema_issues:
        location = ".".join(map(str, error.absolute_path)) or "$"
        errors.append(f"{path}:{location}: {error.message}")
    return None if schema_issues else data


def canonical_shard_sha256(data):
    return canonical_json_sha256(data, {"output_sha256"})


def validate_promoted_hash(source, target, label, errors):
    if source.is_file() and target.is_file() and sha256_file(source) != sha256_file(target):
        errors.append(f"{label}晋级前后SHA-256不一致")


def validate_record(task_root, record, schema_path, errors, expected_path=None, label="记录"):
    relative = record.get("path") if isinstance(record, dict) else None
    if not isinstance(relative, str) or not relative:
        errors.append(f"{label}缺少相对路径")
        return None, None
    path = (task_root / relative).resolve()
    if task_root != path and task_root not in path.parents:
        errors.append(f"{label}路径越出任务根目录: {relative}")
        return None, None
    if expected_path and relative != expected_path:
        errors.append(f"{label}路径不正确: {relative} != {expected_path}")
    data = validate_json(path, schema_path, errors)
    if data and data.get("task_id") != task_root.name:
        errors.append(f"{label}的task_id与任务目录名不一致: {data.get('task_id')} != {task_root.name}")
    if path.is_file() and record.get("sha256") != sha256_file(path):
        errors.append(f"{label}绑定的SHA-256不一致: {relative}")
    return data, path


def validate_runtime(path, errors, entries=None, relative_root=None):
    for name in RUNTIME_FILES:
        if not (path / name).is_file():
            errors.append(f"Runtime四件套缺少{name}: {path}")
    if entries is None:
        return
    names = [item.get("name") for item in entries if isinstance(item, dict)]
    if names != RUNTIME_FILES:
        errors.append(f"Runtime文件清单或顺序必须为{RUNTIME_FILES}: {path}")
    by_name = {item.get("name"): item for item in entries if isinstance(item, dict)}
    for name in RUNTIME_FILES:
        file = path / name
        entry = by_name.get(name, {})
        expected = f"{relative_root}/{name}" if relative_root else None
        if expected and entry.get("path") != expected:
            errors.append(f"Runtime记录路径不正确: {entry.get('path')} != {expected}")
        if file.is_file() and entry.get("sha256") != sha256_file(file):
            errors.append(f"Runtime记录SHA-256不一致: {file}")


def validate_shards(path, errors, phase=None, batch_id=None, candidate_id=None, plan=None, expected_fields=None):
    json_files = sorted(path.glob("*.json")) if path.is_dir() else []
    malformed = [file.name for file in json_files if not SHARD_RE.fullmatch(file.name)]
    if malformed:
        errors.append(f"分片目录包含非法JSON文件名: {path}: {malformed}")
    files = sorted((file for file in json_files if SHARD_RE.fullmatch(file.name)), key=lambda item: int(SHARD_RE.fullmatch(item.name).group(1)))
    if not files:
        errors.append(f"缺少执行分片: {path}")
        return []
    schema = ROOT / "assets/schemas/execution-shard.schema.json"
    expected_start, results = 0, []
    for index, file in enumerate(files):
        data = validate_json(file, schema, errors)
        if not data:
            continue
        results.append(data)
        if data["shard_index"] != index or file.name != f"shard-{index:06d}.json":
            errors.append(f"分片文件名与shard_index不一致: {file}")
        if data["entry_start"] != expected_start:
            errors.append(f"分片entry_start不连续: {file}: {data['entry_start']} != {expected_start}")
        expected_start += data["entry_count"]
        if phase and data.get("phase") != phase:
            errors.append(f"分片phase不正确: {file}: {data.get('phase')} != {phase}")
        if batch_id and data.get("batch_id") != batch_id:
            errors.append(f"分片batch_id不正确: {file}")
        if candidate_id and data.get("candidate_id") != candidate_id:
            errors.append(f"分片candidate_id不正确: {file}")
        for key, value in (expected_fields or {}).items():
            if data.get(key) != value:
                errors.append(f"分片输入指纹不一致: {file}: {key}")
        if data.get("output_sha256") != canonical_shard_sha256(data):
            errors.append(f"分片output_sha256不一致: {file}")
    if plan:
        planned = plan.get("shards", [])
        if len(planned) != len(results):
            errors.append(f"FORMAL计划分片数与实际不一致: {path}")
        for expected, actual in zip(planned, results):
            for key in ["shard_index", "entry_start", "entry_count", "shard_seed"]:
                if expected.get(key) != actual.get(key):
                    errors.append(f"FORMAL计划与实际分片字段不一致: {path}/shard-{actual['shard_index']:06d}.json: {key}")
            if expected.get("path") != f"work/formal/{batch_id}/shards/shard-{actual['shard_index']:06d}.json":
                errors.append(f"FORMAL计划分片路径不正确: {expected.get('path')}")
        if sum(item.get("entry_count", 0) for item in planned) != plan.get("selected_paid_entry_count"):
            errors.append(f"FORMAL计划分片总入口数不等于selected_paid_entry_count: {path}")
    return results


def validate_skill_contract(errors):
    policy = validate_json(POLICY_PATH, POLICY_SCHEMA_PATH, errors)
    if not policy:
        return None
    seen = set()
    bindings = [*policy["authoritative_artifacts"], *policy["work_records"]]
    for item in bindings:
        key = item.get("path", item.get("path_pattern"))
        if key in seen:
            errors.append(f"目录政策出现重复路径: {key}")
        seen.add(key)
        schema_path, template_path = ROOT / item["schema"], ROOT / item["template"]
        if not schema_path.is_file():
            errors.append(f"目录政策绑定的Schema不存在: {item['schema']}")
        else:
            try:
                Draft202012Validator.check_schema(load(schema_path))
            except Exception as exc:
                errors.append(f"Schema无效: {item['schema']}: {exc}")
        if not template_path.is_file():
            errors.append(f"目录政策绑定的模板不存在: {item['template']}")
        elif schema_path.is_file():
            expected_version = load(schema_path).get("properties", {}).get("schema_version", {}).get("const")
            actual_version = load(template_path).get("schema_version")
            if expected_version and actual_version != expected_version:
                errors.append(f"模板与Schema版本不一致: {item['template']} -> {actual_version} != {expected_version}")
    bound_templates = {item["template"] for item in bindings}
    if len(bound_templates) != len(bindings):
        errors.append("目录政策中每个命名机器JSON必须绑定独立模板")
    all_templates = {path.relative_to(ROOT).as_posix() for path in (ROOT / "assets/templates").rglob("*.json")}
    if bound_templates != all_templates:
        errors.append(f"机器JSON模板与目录政策未一一闭环: 未绑定={sorted(all_templates - bound_templates)}，无模板={sorted(bound_templates - all_templates)}")
    docs = (ROOT / "references/04-工作区目录结构.md").read_text(encoding="utf-8")
    for marker in ["batch_manifest.json", "freeze_manifest.json", "candidate_freezes", "formal_batches", "independent-recheck", "shard-######.json", "report_manifest.json", "对齐报告.md"]:
        if marker not in docs:
            errors.append(f"工作区文档缺少6.0目录标记: {marker}")
    return policy


def validate_task(task_root, through_stage, policy, errors):
    artifacts = {}
    for item in policy["authoritative_artifacts"]:
        if item["stage"] <= through_stage:
            path = task_root / item["path"]
            artifacts[item["path"]] = validate_json(path, ROOT / item["schema"], errors)
    task_ids = {data.get("task_id") for data in artifacts.values() if isinstance(data, dict) and data.get("task_id")}
    if task_ids and task_ids != {task_root.name}:
        errors.append(f"权威产物task_id与任务目录名不一致: {sorted(task_ids)} != {task_root.name}")
    if through_stage >= 1:
        baseline_runtime = task_root / "work/baseline/runtime"
        validate_runtime(baseline_runtime, errors)
        input_manifest = artifacts.get("artifacts/01-input-profile/input_manifest.json") or {}
        selected_baseline = input_manifest.get("selected_baseline") or {}
        if input_manifest.get("status") != "READY":
            errors.append("完成阶段1时input_manifest.status必须为READY")
        allowed_runtime_sources = {"test": {"config-test", "server-dev"}, "prod": {"config-prod", "server-prod"}}
        if selected_baseline.get("directory_id") not in allowed_runtime_sources.get(input_manifest.get("runtime_environment"), set()):
            errors.append("基线Runtime来源与runtime_environment不匹配")
        candidate = next((item for item in input_manifest.get("runtime_candidates", []) if item.get("candidate_id") == selected_baseline.get("candidate_id")), None)
        if not candidate or candidate.get("bundle_sha256") != selected_baseline.get("bundle_sha256"):
            errors.append("selected_baseline未与runtime_candidates中的同一候选绑定")
        names = [item.get("name") for item in selected_baseline.get("files", [])]
        if names != RUNTIME_FILES:
            errors.append(f"selected_baseline文件清单或顺序必须为{RUNTIME_FILES}")
        for item in selected_baseline.get("files", []):
            file = baseline_runtime / item.get("name", "")
            if file.is_file() and item.get("sha256") != sha256_file(file):
                errors.append(f"密封基线Runtime与input_manifest文件SHA-256不一致: {item.get('name')}")
        capability = artifacts.get("artifacts/01-input-profile/runtime_capability_matrix.json") or {}
        script_equivalence = artifacts.get("artifacts/01-input-profile/script_equivalence.json") or {}
        parameter_authority = artifacts.get("artifacts/01-input-profile/parameter_authority.json") or {}
        if capability.get("runtime_bundle_sha256") != selected_baseline.get("bundle_sha256") or script_equivalence.get("runtime_bundle_sha256") != selected_baseline.get("bundle_sha256"):
            errors.append("能力矩阵或脚本等价记录未绑定密封基线Runtime bundle")
        if capability.get("parameter_authority_sha256") != file_sha256(task_root / "artifacts/01-input-profile/parameter_authority.json"):
            errors.append("能力矩阵未绑定当前parameter_authority.json")
        if script_equivalence.get("certified_script_sha256") != (input_manifest.get("certified_script") or {}).get("sha256"):
            errors.append("脚本等价记录未绑定input_manifest中的认证脚本")
        if capability.get("certified_script_sha256") != script_equivalence.get("certified_script_sha256"):
            errors.append("能力矩阵与脚本等价记录的认证脚本SHA-256不一致")
        if parameter_authority.get("status") != "READY" or capability.get("summary", {}).get("coverage_status") != "通过" or script_equivalence.get("status") != "passed":
            errors.append("完成阶段1时参数权限、能力矩阵和脚本等价必须全部就绪或通过")
        if any(item.get("status") != "passed" for item in script_equivalence.get("checks", [])):
            errors.append("script_equivalence存在未通过检查")
        for record in script_equivalence.get("evidence_files", []):
            relative = record.get("path", "")
            path = (task_root / relative).resolve()
            if task_root != path and task_root not in path.parents:
                errors.append(f"脚本等价证据路径越出任务根目录: {relative}")
            elif not path.is_file() or record.get("sha256") != sha256_file(path):
                errors.append(f"脚本等价证据不存在或SHA-256不一致: {relative}")
    if through_stage >= 2:
        bindings = artifacts.get("artifacts/02-metric-matching/contract_bindings.json") or {}
        contract = artifacts.get("artifacts/02-metric-matching/metric_contract.json") or {}
        stage_paths = {
            "game_profile_sha256": "artifacts/01-input-profile/game_profile.json",
            "parameter_authority_sha256": "artifacts/01-input-profile/parameter_authority.json",
            "sample_execution_plan_sha256": "artifacts/02-metric-matching/sample_execution_plan.json",
            "runtime_capability_matrix_sha256": "artifacts/01-input-profile/runtime_capability_matrix.json",
            "targets_sha256": "artifacts/02-metric-matching/targets.json",
            "contract_bindings_sha256": "artifacts/02-metric-matching/contract_bindings.json",
        }
        if bindings.get("game_profile_sha256") != file_sha256(task_root / stage_paths["game_profile_sha256"]) or bindings.get("parameter_authority_sha256") != file_sha256(task_root / stage_paths["parameter_authority_sha256"]):
            errors.append("contract_bindings绑定的画像或参数权限SHA-256不一致")
        for key, relative in stage_paths.items():
            if contract.get("hashes", {}).get(key) != file_sha256(task_root / relative):
                errors.append(f"metric_contract绑定SHA-256不一致: {key}")
        for key in ["runtime_bundle_sha256", "original_evidence_sha256", "script_sha256", "game_profile_sha256", "parameter_authority_sha256"]:
            if contract.get("hashes", {}).get(key) != bindings.get(key):
                errors.append(f"metric_contract与contract_bindings字段不一致: {key}")
        if contract and contract.get("hashes", {}).get("contract_sha256") != contract_digest(contract):
            errors.append("metric_contract内部contract_sha256不一致")
        for binding in [contract.get("metric_library", {}), *contract.get("policies", {}).values()]:
            path = ROOT / binding.get("path", "")
            if not path.is_file() or binding.get("sha256") != sha256_file(path):
                errors.append(f"metric_contract绑定的Skill事实源不存在或SHA-256不一致: {binding.get('path')}")
        sample_plan = artifacts.get("artifacts/02-metric-matching/sample_execution_plan.json") or {}
        capability = artifacts.get("artifacts/01-input-profile/runtime_capability_matrix.json") or {}
        if sample_plan.get("policy", {}).get("sha256") != sha256_file(ROOT / "assets/policies/sample_execution_policy.json"):
            errors.append("sample_execution_plan绑定的样本政策SHA-256不一致")
        capability_policy_path = ROOT / capability.get("policy", {}).get("path", "")
        if not capability_policy_path.is_file() or capability.get("policy", {}).get("sha256") != sha256_file(capability_policy_path):
            errors.append("runtime_capability_matrix绑定的能力政策不存在或SHA-256不一致")
    if through_stage >= 3:
        work_measurements = task_root / "work/baseline/measurements.json"
        baseline_measurements = validate_json(work_measurements, ROOT / "assets/schemas/metric-measurements.schema.json", errors)
        if baseline_measurements and baseline_measurements.get("phase") != "BASELINE":
            errors.append("work/baseline/measurements.json的phase必须为BASELINE")
        if baseline_measurements and baseline_measurements.get("task_id") != task_root.name:
            errors.append("work/baseline/measurements.json的task_id与任务目录名不一致")
        baseline_input = artifacts.get("artifacts/01-input-profile/input_manifest.json") or {}
        baseline_script = artifacts.get("artifacts/01-input-profile/script_equivalence.json") or {}
        validate_shards(task_root / "work/baseline/shards", errors, phase="BASELINE", expected_fields={
            "metric_contract_sha256": file_sha256(task_root / "artifacts/02-metric-matching/metric_contract.json"),
            "runtime_bundle_sha256": (baseline_input.get("selected_baseline") or {}).get("bundle_sha256"),
            "script_bundle_sha256": baseline_script.get("derived_script_bundle_sha256"),
            "candidate_parameter_sha256": None,
        })
        promoted = task_root / "artifacts/03-evaluation/baseline_measurements.json"
        validate_promoted_hash(work_measurements, promoted, "BASELINE测量", errors)
        contract_sha256 = file_sha256(task_root / "artifacts/02-metric-matching/metric_contract.json")
        baseline_result = artifacts.get("artifacts/03-evaluation/alignment_result.json") or {}
        stage3_gate = artifacts.get("artifacts/03-evaluation/stage3_gate.json") or {}
        if baseline_result.get("phase") != "BASELINE" or baseline_result.get("metric_contract_sha256") != contract_sha256:
            errors.append("阶段3 alignment_result必须是绑定当前合同的BASELINE结果")
        if baseline_measurements and baseline_measurements.get("metric_contract_sha256") != contract_sha256:
            errors.append("BASELINE测量绑定的metric_contract_sha256不一致")
        baseline_result_path = task_root / "artifacts/03-evaluation/alignment_result.json"
        baseline_summary = baseline_result.get("summary", {})
        if (stage3_gate.get("alignment_result_sha256") != file_sha256(baseline_result_path)
                or stage3_gate.get("baseline_final_status") != baseline_summary.get("final_status")
                or stage3_gate.get("baseline_conclusion") != baseline_summary.get("conclusion")
                or stage3_gate.get("coverage_status") != baseline_summary.get("coverage_status")):
            errors.append("stage3_gate与BASELINE评价结果绑定不一致")
    if through_stage >= 4:
        manifest = artifacts.get("artifacts/04-alignment/alignment_manifest.json") or {}
        if not manifest:
            return
        contract_path = task_root / "artifacts/02-metric-matching/metric_contract.json"
        sample_plan_path = task_root / "artifacts/02-metric-matching/sample_execution_plan.json"
        capability_path = task_root / "artifacts/01-input-profile/runtime_capability_matrix.json"
        authority_path = task_root / "artifacts/01-input-profile/parameter_authority.json"
        capability = artifacts.get("artifacts/01-input-profile/runtime_capability_matrix.json") or {}
        script_equivalence = artifacts.get("artifacts/01-input-profile/script_equivalence.json") or {}
        runtime_bundle_sha256 = capability.get("runtime_bundle_sha256")
        script_bundle_sha256 = script_equivalence.get("derived_script_bundle_sha256")
        expected_hashes = {
            "metric_contract_sha256": file_sha256(contract_path),
            "sample_execution_plan_sha256": file_sha256(sample_plan_path),
            "runtime_capability_matrix_sha256": file_sha256(capability_path),
        }
        if any(manifest.get(key) != value for key, value in expected_hashes.items()):
            errors.append("alignment_manifest绑定的合同、样本计划或能力矩阵SHA-256不一致")
        sensitivity_schemas = {"plan": "sensitivity-plan.schema.json", "result": "sensitivity-result.schema.json"}
        sensitivity = {}
        for key, schema in sensitivity_schemas.items():
            expected = f"work/sensitivity/sensitivity_{key}.json"
            sensitivity[key], _ = validate_record(task_root, manifest.get("sensitivity", {}).get(key, {}), ROOT / "assets/schemas" / schema, errors, expected, f"敏感性{key}")
        if sensitivity.get("plan"):
            plan = sensitivity["plan"]
            if plan.get("metric_contract_sha256") != expected_hashes["metric_contract_sha256"] or plan.get("parameter_authority_sha256") != file_sha256(authority_path) or plan.get("runtime_bundle_sha256") != runtime_bundle_sha256:
                errors.append("敏感性计划绑定的合同、参数权限或Runtime SHA-256不一致")
        if sensitivity.get("result"):
            result = sensitivity["result"]
            plan_path = task_root / "work/sensitivity/sensitivity_plan.json"
            if result.get("sensitivity_plan_sha256") != file_sha256(plan_path) or result.get("metric_contract_sha256") != expected_hashes["metric_contract_sha256"] or result.get("runtime_bundle_sha256") != runtime_bundle_sha256:
                errors.append("敏感性结果绑定的计划、合同或Runtime SHA-256不一致")
        listed_cv, ranked_parameter_hashes, final_top = set(), {}, None
        layers = manifest.get("search", {}).get("upgrade_layers", [])
        used_layers = []
        manifest_cv_order = [item.get("batch_id") for item in manifest.get("calibration_batches", [])]
        if manifest_cv_order != sorted(set(manifest_cv_order)):
            errors.append("alignment_manifest.calibration_batches必须按唯一cv####升序排列")
        for binding in manifest.get("calibration_batches", []):
            batch_id = binding.get("batch_id")
            listed_cv.add(batch_id)
            expected = f"work/calibration/{batch_id}/batch_manifest.json"
            batch, _ = validate_record(task_root, binding, ROOT / "assets/schemas/calibration-batch-manifest.schema.json", errors, expected, f"CALIBRATION批次{batch_id}")
            if not batch:
                continue
            if batch.get("batch_id") != batch_id or binding.get("candidate_count") != len(batch.get("candidates", [])) or binding.get("status") != batch.get("status"):
                errors.append(f"alignment_manifest与CALIBRATION批次摘要不一致: {batch_id}")
            if any(batch.get(key) != value for key, value in expected_hashes.items()):
                errors.append(f"CALIBRATION批次绑定的合同、样本计划或能力矩阵SHA-256不一致: {batch_id}")
            layer_id = batch.get("search_layer_id")
            if layer_id not in layers:
                errors.append(f"CALIBRATION批次引用未知搜索层: {batch_id} -> {layer_id}")
            used_layers.append((layer_id, batch.get("stage")))
            ranked = [item for item in batch.get("candidates", []) if item.get("status") == "ranked"]
            candidate_ids = [item.get("candidate_id") for item in batch.get("candidates", [])]
            if len(candidate_ids) != len(set(candidate_ids)):
                errors.append(f"CALIBRATION批次出现重复candidate_id: {batch_id}")
            statuses = [item.get("status") for item in batch.get("candidates", [])]
            first_non_ranked = next((index for index, status in enumerate(statuses) if status != "ranked"), len(statuses))
            if any(status == "ranked" for status in statuses[first_non_ranked:]):
                errors.append(f"CALIBRATION有效候选必须排在拒绝或失效提案之前: {batch_id}")
            rank_key = lambda item: (
                item["rank"]["n_failures"], item["rank"]["alignment_failures"], item["rank"]["unknown_instances"],
                float("inf") if item["rank"]["maximum_deviation_ratio"] is None else item["rank"]["maximum_deviation_ratio"],
                item["rank"]["deviation_ratio_sum"], item["rank"]["candidate_id"],
            )
            if ranked != sorted(ranked, key=rank_key):
                errors.append(f"CALIBRATION有效候选未按冻结排序元组排列: {batch_id}")
            if batch.get("stage") == "FINAL" and batch.get("status") == "completed":
                final_top = [item.get("candidate_id") for item in ranked[:2]]
            for candidate in batch.get("candidates", []):
                if candidate.get("status") != "ranked":
                    continue
                candidate_id = candidate.get("candidate_id")
                root = f"work/calibration/{batch_id}/candidates/{candidate_id}"
                parameter, parameter_path = validate_record(task_root, candidate.get("parameter_record", {}), ROOT / "assets/schemas/parameter-record.schema.json", errors, f"{root}/parameter_record.json", f"候选参数{candidate_id}")
                measurements, _ = validate_record(task_root, candidate.get("measurements", {}), ROOT / "assets/schemas/metric-measurements.schema.json", errors, f"{root}/measurements.json", f"候选测量{candidate_id}")
                result, _ = validate_record(task_root, candidate.get("alignment_result", {}), ROOT / "assets/schemas/alignment-result.schema.json", errors, f"{root}/alignment_result.json", f"候选结果{candidate_id}")
                if measurements and measurements.get("phase") != "CALIBRATION":
                    errors.append(f"候选测量phase必须为CALIBRATION: {candidate_id}")
                if result and result.get("phase") != "CALIBRATION":
                    errors.append(f"候选结果phase必须为CALIBRATION: {candidate_id}")
                if measurements and measurements.get("metric_contract_sha256") != expected_hashes["metric_contract_sha256"]:
                    errors.append(f"候选测量绑定的合同SHA-256不一致: {candidate_id}")
                if result and result.get("metric_contract_sha256") != expected_hashes["metric_contract_sha256"]:
                    errors.append(f"候选结果绑定的合同SHA-256不一致: {candidate_id}")
                if result:
                    summary, rank = result["summary"], candidate["rank"]
                    expected_counts = {
                        "n_failures": summary["hard_gate_failures"],
                        "alignment_failures": summary["alignment_failures"],
                        "unknown_instances": summary["insufficient_or_error_instances"],
                    }
                    if any(rank.get(key) != value for key, value in expected_counts.items()):
                        errors.append(f"候选排序计数与评价结果不一致: {candidate_id}")
                    ratios = [
                        item["deviation_ratio"]
                        for card in result["card_results"]
                        for item in card["instances"]
                        if isinstance(item.get("deviation_ratio"), (int, float)) and not isinstance(item.get("deviation_ratio"), bool)
                    ]
                    if rank.get("maximum_deviation_ratio") != summary.get("maximum_deviation_ratio"):
                        errors.append(f"候选最大偏差倍数与评价结果不一致: {candidate_id}")
                    if abs(rank.get("deviation_ratio_sum", 0.0) - sum(ratios)) > 1e-9:
                        errors.append(f"候选偏差倍数总和与评价结果不一致: {candidate_id}")
                validate_runtime(task_root / root / "runtime", errors, (parameter or {}).get("runtime_files"), f"{root}/runtime")
                shards = validate_shards(task_root / root / "shards", errors, "CALIBRATION", batch_id, candidate_id, expected_fields={
                    "metric_contract_sha256": expected_hashes["metric_contract_sha256"],
                    "candidate_parameter_sha256": (parameter or {}).get("parameter_sha256"),
                    "runtime_bundle_sha256": (parameter or {}).get("runtime_bundle_sha256"),
                    "script_bundle_sha256": script_bundle_sha256,
                })
                if sum(item.get("entry_count", 0) for item in shards) != batch.get("cumulative_paid_entries"):
                    errors.append(f"候选分片总入口数与CALIBRATION档位不一致: {candidate_id}")
                if parameter and (parameter.get("batch_id") != batch_id or parameter.get("candidate_id") != candidate_id):
                    errors.append(f"候选参数ID与目录不一致: {candidate_id}")
                if parameter and parameter.get("parameter_authority_sha256") != file_sha256(authority_path):
                    errors.append(f"候选参数绑定的参数权限SHA-256不一致: {candidate_id}")
                if parameter_path and parameter_path.is_file():
                    ranked_parameter_hashes[candidate_id] = sha256_file(parameter_path)
                if candidate.get("rank", {}).get("candidate_id") != candidate_id:
                    errors.append(f"候选排序键candidate_id不一致: {candidate_id}")
        actual_cv = {path.name for path in (task_root / "work/calibration").glob("cv[0-9][0-9][0-9][0-9]") if path.is_dir()}
        if actual_cv != listed_cv:
            errors.append(f"CALIBRATION目录与alignment_manifest索引不一致: 目录={sorted(actual_cv)}，索引={sorted(listed_cv)}")
        actual_layer_order = []
        for layer_id, _ in used_layers:
            if not actual_layer_order or actual_layer_order[-1] != layer_id:
                actual_layer_order.append(layer_id)
        if actual_layer_order != layers[:len(actual_layer_order)]:
            errors.append(f"CALIBRATION搜索层顺序与冻结升级顺序不一致: {actual_layer_order} != {layers}")
        for layer_id in actual_layer_order:
            stages = [stage for current, stage in used_layers if current == layer_id]
            if stages != ["SCREEN", "REFINE", "FINAL"]:
                errors.append(f"搜索层必须完整执行SCREEN→REFINE→FINAL: {layer_id}: {stages}")
        selected, listed_freezes = [], set()
        freeze_order = [item.get("candidate_id") for item in manifest.get("candidate_freezes", [])]
        if len(freeze_order) != len(set(freeze_order)):
            errors.append("alignment_manifest.candidate_freezes出现重复candidate_id")
        freeze_by_candidate = {}
        for binding in manifest.get("candidate_freezes", []):
            candidate_id = binding.get("candidate_id")
            listed_freezes.add(candidate_id)
            expected = f"work/candidate-freeze/{candidate_id}/freeze_manifest.json"
            freeze, _ = validate_record(task_root, binding, ROOT / "assets/schemas/candidate-freeze-manifest.schema.json", errors, expected, f"冻结候选{candidate_id}")
            if binding.get("selected_for_formal") is True:
                selected.append(candidate_id)
            if not freeze:
                continue
            freeze_by_candidate[candidate_id] = freeze
            freeze_root = task_root / "work/candidate-freeze" / candidate_id
            parameter, parameter_path = validate_record(task_root, freeze.get("parameter_record", {}), ROOT / "assets/schemas/parameter-record.schema.json", errors, f"work/candidate-freeze/{candidate_id}/parameter_record.json", f"冻结参数{candidate_id}")
            validate_runtime(freeze_root / "runtime", errors, freeze.get("runtime_files"), f"work/candidate-freeze/{candidate_id}/runtime")
            recheck = freeze_root / "independent-recheck"
            recheck_shards = validate_shards(recheck / "shards", errors, "INDEPENDENT_RECHECK", candidate_id=candidate_id, expected_fields={
                "metric_contract_sha256": expected_hashes["metric_contract_sha256"],
                "candidate_parameter_sha256": freeze.get("parameter_sha256"),
                "runtime_bundle_sha256": freeze.get("runtime_bundle_sha256"),
                "script_bundle_sha256": freeze.get("script_bundle_sha256"),
            })
            if sum(item.get("entry_count", 0) for item in recheck_shards) != 2000000:
                errors.append(f"独立复核分片总入口数必须为2000000: {candidate_id}")
            recheck_contract = freeze.get("independent_recheck", {})
            recheck_measurements, _ = validate_record(task_root, recheck_contract.get("measurements", {}), ROOT / "assets/schemas/metric-measurements.schema.json", errors, f"work/candidate-freeze/{candidate_id}/independent-recheck/measurements.json", f"独立复核测量{candidate_id}")
            recheck_result, _ = validate_record(task_root, recheck_contract.get("alignment_result", {}), ROOT / "assets/schemas/alignment-result.schema.json", errors, f"work/candidate-freeze/{candidate_id}/independent-recheck/alignment_result.json", f"独立复核结果{candidate_id}")
            if recheck_measurements and recheck_measurements.get("phase") != "INDEPENDENT_RECHECK":
                errors.append(f"独立复核测量phase不正确: {candidate_id}")
            if recheck_result and recheck_result.get("phase") != "INDEPENDENT_RECHECK":
                errors.append(f"独立复核结果phase不正确: {candidate_id}")
            if recheck_measurements and recheck_measurements.get("metric_contract_sha256") != expected_hashes["metric_contract_sha256"]:
                errors.append(f"独立复核测量绑定的合同SHA-256不一致: {candidate_id}")
            if recheck_result and recheck_result.get("metric_contract_sha256") != expected_hashes["metric_contract_sha256"]:
                errors.append(f"独立复核结果绑定的合同SHA-256不一致: {candidate_id}")
            if recheck_result and recheck_contract.get("status") != recheck_result.get("summary", {}).get("final_status"):
                errors.append(f"freeze_manifest独立复核状态与实际结果不一致: {candidate_id}")
            if freeze.get("candidate_id") != candidate_id or binding.get("independent_recheck_status") != recheck_contract.get("status"):
                errors.append(f"冻结候选摘要与freeze_manifest不一致: {candidate_id}")
            if freeze.get("metric_contract_sha256") != expected_hashes["metric_contract_sha256"] or freeze.get("runtime_capability_matrix_sha256") != expected_hashes["runtime_capability_matrix_sha256"] or freeze.get("script_bundle_sha256") != script_bundle_sha256:
                errors.append(f"冻结候选绑定的合同、能力矩阵或脚本SHA-256不一致: {candidate_id}")
            if parameter and parameter_path and freeze.get("parameter_sha256") != parameter.get("parameter_sha256"):
                errors.append(f"冻结候选parameter_sha256与参数记录不一致: {candidate_id}")
            if parameter and freeze.get("runtime_bundle_sha256") != parameter.get("runtime_bundle_sha256"):
                errors.append(f"冻结候选Runtime bundle SHA-256与参数记录不一致: {candidate_id}")
            if parameter:
                source_files = {item.get("name"): item for item in parameter.get("runtime_files", [])}
                frozen_files = {item.get("name"): item for item in freeze.get("runtime_files", [])}
                for name in RUNTIME_FILES:
                    if source_files.get(name, {}).get("sha256") != frozen_files.get(name, {}).get("sha256"):
                        errors.append(f"冻结Runtime不是CALIBRATION候选的原样副本: {candidate_id}/{name}")
            if candidate_id not in ranked_parameter_hashes:
                errors.append(f"冻结候选未出现在有效CALIBRATION候选中: {candidate_id}")
            elif parameter_path and sha256_file(parameter_path) != ranked_parameter_hashes[candidate_id]:
                errors.append(f"冻结parameter_record不是CALIBRATION原记录的原样副本: {candidate_id}")
        actual_freezes = {path.name for path in (task_root / "work/candidate-freeze").iterdir() if path.is_dir()} if (task_root / "work/candidate-freeze").is_dir() else set()
        if actual_freezes != listed_freezes:
            errors.append(f"冻结候选目录与alignment_manifest索引不一致: 目录={sorted(actual_freezes)}，索引={sorted(listed_freezes)}")
        if final_top is None:
            errors.append("CALIBRATION缺少已完成的FINAL批次")
        elif freeze_order != final_top:
            errors.append(f"冻结候选必须按最终批次前2名顺序排列: 冻结={freeze_order}，应为={final_top}")
        if len(selected) != 1:
            errors.append("alignment_manifest必须且只能选择一个FORMAL候选")
        promoted_batches, listed_fv = [], set()
        promoted_result = None
        formal_order = [item.get("batch_id") for item in manifest.get("formal_batches", [])]
        if formal_order != sorted(set(formal_order)):
            errors.append("alignment_manifest.formal_batches必须按唯一fv####升序排列")
        for binding in manifest.get("formal_batches", []):
            batch_id, candidate_id = binding.get("batch_id"), binding.get("candidate_id")
            listed_fv.add(batch_id)
            formal_root = task_root / "work/formal" / str(batch_id)
            plan, _ = validate_record(task_root, binding.get("plan", {}), ROOT / "assets/schemas/formal-plan.schema.json", errors, f"work/formal/{batch_id}/formal_plan.json", f"FORMAL计划{batch_id}")
            result, result_path = validate_record(task_root, binding.get("result", {}), ROOT / "assets/schemas/alignment-result.schema.json", errors, f"work/formal/{batch_id}/alignment_result.json", f"FORMAL结果{batch_id}")
            selected_freeze = freeze_by_candidate.get(candidate_id, {})
            validate_runtime(formal_root / "runtime", errors)
            freeze_runtime = task_root / "work/candidate-freeze" / str(candidate_id) / "runtime"
            for name in RUNTIME_FILES:
                formal_file, freeze_file = formal_root / "runtime" / name, freeze_runtime / name
                if formal_file.is_file() and freeze_file.is_file() and sha256_file(formal_file) != sha256_file(freeze_file):
                    errors.append(f"FORMAL Runtime不是冻结候选的原样副本: {batch_id}/{name}")
            validate_shards(formal_root / "shards", errors, "FORMAL", batch_id, candidate_id, plan, {
                "metric_contract_sha256": expected_hashes["metric_contract_sha256"],
                "candidate_parameter_sha256": selected_freeze.get("parameter_sha256"),
                "runtime_bundle_sha256": selected_freeze.get("runtime_bundle_sha256"),
                "script_bundle_sha256": selected_freeze.get("script_bundle_sha256"),
            })
            formal_measurements = validate_json(formal_root / "measurements.json", ROOT / "assets/schemas/metric-measurements.schema.json", errors)
            if formal_measurements and formal_measurements.get("phase") != "FORMAL":
                errors.append(f"FORMAL测量phase不正确: {batch_id}")
            if formal_measurements and formal_measurements.get("task_id") != task_root.name:
                errors.append(f"FORMAL测量task_id与任务目录名不一致: {batch_id}")
            if formal_measurements and formal_measurements.get("metric_contract_sha256") != expected_hashes["metric_contract_sha256"]:
                errors.append(f"FORMAL测量绑定的合同SHA-256不一致: {batch_id}")
            if plan and (plan.get("batch_id") != batch_id or plan.get("candidate_id") != candidate_id):
                errors.append(f"FORMAL计划ID与索引不一致: {batch_id}")
            selected_freeze_path = task_root / f"work/candidate-freeze/{candidate_id}/freeze_manifest.json"
            if plan and (
                not selected_freeze_path.is_file()
                or plan.get("freeze_manifest_sha256") != sha256_file(selected_freeze_path)
                or plan.get("metric_contract_sha256") != expected_hashes["metric_contract_sha256"]
                or plan.get("sample_execution_plan_sha256") != expected_hashes["sample_execution_plan_sha256"]
                or plan.get("runtime_bundle_sha256") != selected_freeze.get("runtime_bundle_sha256")
                or plan.get("script_bundle_sha256") != selected_freeze.get("script_bundle_sha256")
            ):
                errors.append(f"FORMAL计划绑定的冻结候选、合同、样本计划、Runtime或脚本SHA-256不一致: {batch_id}")
            if result and result.get("phase") != "FORMAL":
                errors.append(f"FORMAL结果phase不正确: {batch_id}")
            if result and result.get("metric_contract_sha256") != expected_hashes["metric_contract_sha256"]:
                errors.append(f"FORMAL结果绑定的合同SHA-256不一致: {batch_id}")
            if binding.get("promoted_to_artifact") is True:
                promoted_batches.append(binding)
                promoted_result = result
                if binding.get("status") != "completed":
                    errors.append(f"只有已完成FORMAL批次可以晋级: {batch_id}")
                if result_path:
                    validate_promoted_hash(result_path, task_root / "artifacts/04-alignment/formal_result.json", "FORMAL结果", errors)
        actual_fv = {path.name for path in (task_root / "work/formal").glob("fv[0-9][0-9][0-9][0-9]") if path.is_dir()}
        if actual_fv != listed_fv:
            errors.append(f"FORMAL目录与alignment_manifest索引不一致: 目录={sorted(actual_fv)}，索引={sorted(listed_fv)}")
        if len(promoted_batches) != 1:
            errors.append("alignment_manifest必须且只能晋级一个FORMAL批次")
        elif selected != [promoted_batches[0].get("candidate_id")]:
            errors.append("FORMAL晋级批次必须使用唯一入选候选")
        aligned = artifacts.get("artifacts/04-alignment/aligned_parameters.json") or {}
        if selected and aligned.get("candidate_id") != selected[0]:
            errors.append("aligned_parameters必须属于唯一入选候选")
        if selected and selected[0] in freeze_by_candidate:
            freeze = freeze_by_candidate[selected[0]]
            freeze_path = task_root / f"work/candidate-freeze/{selected[0]}/freeze_manifest.json"
            parameter_path = task_root / f"work/candidate-freeze/{selected[0]}/parameter_record.json"
            parameter = load(parameter_path) if parameter_path.is_file() else {}
            if aligned.get("freeze_manifest_sha256") != sha256_file(freeze_path):
                errors.append("aligned_parameters绑定的freeze_manifest_sha256不一致")
            if aligned.get("parameter_record", {}).get("sha256") != (sha256_file(parameter_path) if parameter_path.is_file() else None):
                errors.append("aligned_parameters绑定的parameter_record SHA-256不一致")
            if aligned.get("parameter_record", {}).get("path") != f"work/candidate-freeze/{selected[0]}/parameter_record.json":
                errors.append("aligned_parameters绑定的parameter_record路径不正确")
            if aligned.get("parameters") != parameter.get("complete_parameters") or aligned.get("runtime_bundle_sha256") != freeze.get("runtime_bundle_sha256"):
                errors.append("aligned_parameters内容与冻结候选不一致")
        status_map = {"通过": "formal_pass", "不通过": "formal_not_pass", "无法完整判定": "formal_undetermined"}
        final_status = (promoted_result or {}).get("summary", {}).get("final_status")
        if final_status and manifest.get("termination", {}).get("status") != status_map.get(final_status):
            errors.append("alignment_manifest终止状态与晋级FORMAL结果不一致")
    if through_stage >= 5:
        validate_runtime(task_root / "交付物/runtime", errors)
        delivery_args = [
            task_root,
            task_root / "artifacts/04-alignment/formal_result.json",
            task_root / "artifacts/04-alignment/alignment_manifest.json",
            task_root / "artifacts/04-alignment/aligned_parameters.json",
            task_root / "交付物/runtime",
            task_root / "artifacts/05-delivery/delivery_manifest.json",
        ]
        if all(Path(path).exists() for path in delivery_args[1:]):
            errors.extend(validate_delivery(*delivery_args))
        report_root = task_root / "交付物/报告文档"
        report_path = task_root / policy["report_paths"]["final_report"]
        manifest_path = task_root / policy["report_paths"]["report_manifest"]
        if not report_path.is_file():
            errors.append("缺少唯一最终报告: 交付物/报告文档/对齐报告.md")
        markdown_files = sorted(path.resolve() for path in report_root.rglob("*.md")) if report_root.is_dir() else []
        if markdown_files != ([report_path.resolve()] if report_path.is_file() else []):
            errors.append(f"报告文档目录只能存在一份对齐报告.md，当前Markdown={markdown_files}")
        required_sources = {
            "artifacts/01-input-profile/input_manifest.json",
            "artifacts/02-metric-matching/metric_contract.json",
            "artifacts/04-alignment/formal_result.json",
        }
        view = validate_json(manifest_path, ROOT / "assets/schemas/alignment-report-manifest.schema.json", errors) or {}
        if view.get("task_id") != task_root.name:
            errors.append("报告清单task_id与任务目录不一致")
        sources = {item.get("path") for item in view.get("source_files", [])}
        if sources != required_sources:
            errors.append(f"报告来源必须精确绑定三份实际输入: {sorted(sources)}")
        report_record = view.get("report_file", {})
        if report_record.get("path") != policy["report_paths"]["final_report"]:
            errors.append("报告清单未绑定唯一对齐报告.md")
        for record in [*view.get("source_files", []), report_record]:
            relative = record.get("path", "")
            file = (task_root / relative).resolve()
            if task_root != file and task_root not in file.parents:
                errors.append(f"报告清单路径越出任务根目录: {relative}")
                continue
            if not file.is_file():
                errors.append(f"报告清单绑定文件不存在: {relative}")
            elif record.get("sha256") != sha256_file(file):
                errors.append(f"报告清单绑定SHA-256不一致: {relative}")
        if report_path.is_file():
            report_text = report_path.read_text(encoding="utf-8")
            if "{{" in report_text:
                errors.append("对齐报告仍有未替换占位符")
            for marker in ["对齐总览", "四大指标结果", "指标详情", "N 数值指标", "J 中奖结算", "P 玩法过程", "B 盘面呈现", "最终结论"]:
                if marker not in report_text:
                    errors.append(f"对齐报告缺少必需阅读章节: {marker}")


def main():
    parser = argparse.ArgumentParser(description="校验slot-alignment 6.0目录合同与任务落盘")
    parser.add_argument("--task-root")
    parser.add_argument("--through-stage", type=int, choices=range(1, 6), default=5)
    args = parser.parse_args()
    errors = []
    policy = validate_skill_contract(errors)
    if args.task_root and policy:
        validate_task(Path(args.task_root).resolve(), args.through_stage, policy, errors)
    if errors:
        print("\n".join(f"ERROR: {item}" for item in errors), file=sys.stderr)
        raise SystemExit(1)
    suffix = f"，任务已校验至阶段{args.through_stage}" if args.task_root else ""
    print(f"OK: 6.0目录政策、Schema与模板闭环{suffix}")


if __name__ == "__main__":
    main()
