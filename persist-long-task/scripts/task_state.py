#!/usr/bin/env python3
"""Durable state machine for resumable long-running Codex tasks."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import tempfile
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_STATE = Path(".codex/long-task/state.json")
STATE_NAME = "state.json"
JOURNAL_NAME = "journal.json"
LEGACY_EVENTS_NAME = "events.jsonl"
SCHEMA_VERSION = 4
HISTORY_LIMIT = 12
ATTEMPT_LIMIT = 5
TASK_REVISION_LIMIT = 8
FILE_STATUSES = {"created", "modified", "removed", "temporary", "unchanged"}
ATTEMPT_RESULTS = {"failed", "inconclusive", "succeeded"}
ACTIVE = {"in_progress", "blocked"}
TERMINAL = {"completed", "skipped"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def fail(message: str) -> None:
    raise SystemExit(f"ERROR: {message}")


def clean(value: str, label: str) -> str:
    value = value.strip()
    if not value:
        fail(f"{label} 不能为空")
    return value


def unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(x.strip() for x in items if isinstance(x, str) and x.strip()))


def absolute_paths(items: list[str], root: str | None = None) -> list[str]:
    base = Path(root).expanduser() if root else Path.cwd()
    paths = []
    for item in unique(items):
        path = Path(item).expanduser()
        paths.append(str((path if path.is_absolute() else base / path).resolve()))
    return unique(paths)


def assignments(items: list[str], label: str) -> dict[str, str]:
    result = {}
    for item in items:
        key, marker, value = item.partition("=")
        if not marker or not key.strip() or not value.strip():
            fail(f"{label} 必须使用 步骤ID=证据 格式")
        result[key.strip()] = value.strip()
    return result


def path_assignments(items: list[str], label: str, root: str) -> dict[str, str]:
    result = {}
    for item in items:
        key, marker, value = item.partition("=")
        if not marker or not key.strip() or not value.strip():
            fail(f"{label} 必须使用 路径=说明 格式")
        path = absolute_paths([key], root)[0]
        result[path] = value.strip()
    return result


def canonical_state_path(value: str) -> Path:
    path = Path(value).expanduser().resolve()
    if path.name != STATE_NAME:
        fail(f"状态文件名必须为 {STATE_NAME}；请用独立目录区分任务")
    return path


def journal_path(path: Path) -> Path:
    return path.with_name(JOURNAL_NAME)


def legacy_events_path(path: Path) -> Path:
    return path.with_name(LEGACY_EVENTS_NAME)


@contextmanager
def lock(path: Path, exclusive: bool = True):
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        yield
        fcntl.flock(handle, fcntl.LOCK_UN)


def read_dict(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        fail(f"{label}不存在：{path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"无法读取{label}：{exc}")
    if not isinstance(value, dict):
        fail(f"{label}根节点必须是 JSON 对象")
    return value


def try_read_dict(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.is_file():
        return None, "文件不存在"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, str(exc)
    if not isinstance(value, dict):
        return None, "根节点不是 JSON 对象"
    return value, None


def fsync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
        fsync_directory(path.parent)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def text_list_errors(values: Any, label: str, allow_empty: bool = True) -> list[str]:
    if not isinstance(values, list):
        return [f"{label} 必须是数组"]
    if not allow_empty and not values:
        return [f"{label} 不能为空"]
    if any(not isinstance(value, str) or not value.strip() for value in values):
        return [f"{label} 只能包含非空字符串"]
    return []


def record_list_errors(values: Any, label: str) -> list[str]:
    if not isinstance(values, list):
        return [f"{label} 必须是数组"]
    errors = []
    for index, value in enumerate(values, 1):
        if not isinstance(value, dict):
            errors.append(f"{label}[{index}] 必须是对象")
            continue
        if not isinstance(value.get("at"), str) or not value["at"].strip():
            errors.append(f"{label}[{index}].at 无效")
        if not isinstance(value.get("text"), str) or not value["text"].strip():
            errors.append(f"{label}[{index}].text 无效")
    return errors


def blocker_list_errors(values: Any) -> list[str]:
    if not isinstance(values, list):
        return ["blockers 必须是数组"]
    errors = []
    for index, value in enumerate(values, 1):
        if not isinstance(value, dict):
            errors.append(f"blockers[{index}] 必须是对象")
            continue
        if not isinstance(value.get("at"), str) or not value["at"].strip():
            errors.append(f"blockers[{index}].at 无效")
        if not isinstance(value.get("reason"), str) or not value["reason"].strip():
            errors.append(f"blockers[{index}].reason 无效")
        if not is_int(value.get("count")) or value["count"] < 1:
            errors.append(f"blockers[{index}].count 无效")
        if not isinstance(value.get("active"), bool):
            errors.append(f"blockers[{index}].active 无效")
    return errors


def attempt_list_errors(values: Any, label: str) -> list[str]:
    if not isinstance(values, list):
        return [f"{label} 必须是数组"]
    if len(values) > ATTEMPT_LIMIT:
        return [f"{label} 最多保留 {ATTEMPT_LIMIT} 条"]
    errors = []
    for index, value in enumerate(values, 1):
        if not isinstance(value, dict):
            errors.append(f"{label}[{index}] 必须是对象")
            continue
        for key in ("at", "action", "reason"):
            if not isinstance(value.get(key), str) or not value[key].strip():
                errors.append(f"{label}[{index}].{key} 无效")
        if value.get("result") not in ATTEMPT_RESULTS:
            errors.append(f"{label}[{index}].result 无效")
    return errors


def changed_file_errors(values: Any) -> list[str]:
    if not isinstance(values, list):
        return ["changed_files 必须是数组"]
    errors = []
    paths = []
    for index, value in enumerate(values, 1):
        if not isinstance(value, dict):
            errors.append(f"changed_files[{index}] 必须是对象")
            continue
        path = value.get("path")
        if isinstance(path, str):
            paths.append(path)
        if not isinstance(path, str) or not path.strip() or not Path(path).is_absolute():
            errors.append(f"changed_files[{index}].path 必须是绝对路径")
        if value.get("status") not in FILE_STATUSES:
            errors.append(f"changed_files[{index}].status 无效")
        if not isinstance(value.get("role"), str):
            errors.append(f"changed_files[{index}].role 无效")
        revision = value.get("last_seen_revision")
        if not is_int(revision) or revision < 1:
            errors.append(f"changed_files[{index}].last_seen_revision 无效")
    if len(paths) != len(set(paths)):
        errors.append("changed_files.path 必须唯一")
    return errors


def history_errors(values: Any, state_revision: Any) -> list[str]:
    if not isinstance(values, list):
        return ["recent_history 必须是数组"]
    if len(values) > HISTORY_LIMIT:
        return [f"recent_history 最多保留 {HISTORY_LIMIT} 条"]
    errors = []
    revisions = []
    for index, value in enumerate(values, 1):
        if not isinstance(value, dict):
            errors.append(f"recent_history[{index}] 必须是对象")
            continue
        revision = value.get("revision")
        revisions.append(revision)
        if not is_int(revision) or revision < 1:
            errors.append(f"recent_history[{index}].revision 无效")
        for key in ("at", "type", "summary", "next_action"):
            if not isinstance(value.get(key), str):
                errors.append(f"recent_history[{index}].{key} 无效")
        if isinstance(value.get("at"), str) and not value["at"].strip():
            errors.append(f"recent_history[{index}].at 不能为空")
        if isinstance(value.get("type"), str) and not value["type"].strip():
            errors.append(f"recent_history[{index}].type 不能为空")
        if isinstance(value.get("summary"), str) and not value["summary"].strip():
            errors.append(f"recent_history[{index}].summary 不能为空")
        if "step_id" in value and value["step_id"] is not None and (
            not isinstance(value["step_id"], str) or not value["step_id"].strip()
        ):
            errors.append(f"recent_history[{index}].step_id 无效")
        if "result" in value and value["result"] not in ATTEMPT_RESULTS:
            errors.append(f"recent_history[{index}].result 无效")
        if "changes" in value and not isinstance(value["changes"], dict):
            errors.append(f"recent_history[{index}].changes 无效")
    valid_revisions = [value for value in revisions if is_int(value)]
    if valid_revisions != sorted(valid_revisions) or len(valid_revisions) != len(set(valid_revisions)):
        errors.append("recent_history.revision 必须严格递增")
    if is_int(state_revision) and valid_revisions and valid_revisions[-1] > state_revision:
        errors.append("recent_history revision 不能领先 state")
    return errors


def task_revision_errors(values: Any) -> list[str]:
    if not isinstance(values, list):
        return ["task_revisions 必须是数组"]
    if len(values) > TASK_REVISION_LIMIT:
        return [f"task_revisions 最多保留 {TASK_REVISION_LIMIT} 条"]
    errors = []
    for index, value in enumerate(values, 1):
        if not isinstance(value, dict):
            errors.append(f"task_revisions[{index}] 必须是对象")
            continue
        for key in ("at", "reason"):
            if not isinstance(value.get(key), str) or not value[key].strip():
                errors.append(f"task_revisions[{index}].{key} 无效")
        if not isinstance(value.get("changes"), dict) or not value["changes"]:
            errors.append(f"task_revisions[{index}].changes 无效")
    return errors


def audit(state: Any) -> list[str]:
    if not isinstance(state, dict):
        return ["状态根节点必须是 JSON 对象"]
    required = {
        "schema_version", "revision", "task_id", "workspace_root", "goal",
        "scope", "constraints", "status", "steps", "current_step",
        "next_action", "last_checkpoint", "changed_files", "decisions",
        "verification", "blockers", "final_evidence", "recent_history",
        "task_revisions", "created_at", "updated_at",
    }
    missing = sorted(required - state.keys())
    if missing:
        return ["缺少字段：" + ", ".join(missing)]

    errors = []
    scalar_types = {
        "schema_version": int, "revision": int, "task_id": str,
        "workspace_root": str, "goal": str, "status": str,
        "next_action": str, "created_at": str, "updated_at": str,
    }
    for key, expected in scalar_types.items():
        value = state[key]
        if not isinstance(value, expected) or (expected is int and isinstance(value, bool)):
            errors.append(f"{key} 类型无效")
    if state["current_step"] is not None and not isinstance(state["current_step"], str):
        errors.append("current_step 类型无效")
    if not isinstance(state["last_checkpoint"], dict):
        errors.append("last_checkpoint 必须是对象")
    if not isinstance(state["steps"], list):
        errors.append("steps 必须是数组")
    errors.extend(text_list_errors(state["scope"], "scope"))
    errors.extend(text_list_errors(state["constraints"], "constraints"))
    errors.extend(changed_file_errors(state["changed_files"]))
    errors.extend(text_list_errors(state["final_evidence"], "final_evidence"))
    errors.extend(record_list_errors(state["decisions"], "decisions"))
    errors.extend(record_list_errors(state["verification"], "verification"))
    errors.extend(blocker_list_errors(state["blockers"]))
    errors.extend(history_errors(state["recent_history"], state["revision"]))
    errors.extend(task_revision_errors(state["task_revisions"]))
    if errors:
        return errors

    if state["schema_version"] in {1, 2, 3}:
        errors.append(f"schema_version {state['schema_version']} 需先运行 migrate")
    elif state["schema_version"] != SCHEMA_VERSION:
        errors.append("不支持的 schema_version")
    if state["revision"] < 1:
        errors.append("revision 必须大于等于 1")
    if is_int(state["revision"]):
        for item in state["changed_files"]:
            if isinstance(item, dict) and is_int(item.get("last_seen_revision")) and item["last_seen_revision"] > state["revision"]:
                errors.append(f"changed_files {item.get('path', '?')} revision 领先 state")
    if not state["task_id"].strip() or not state["goal"].strip():
        errors.append("task_id 和 goal 不能为空")
    if not Path(state["workspace_root"]).is_absolute():
        errors.append("workspace_root 必须是绝对路径")
    if state["status"] not in {"in_progress", "blocked", "completed"}:
        errors.append("任务状态无效")
    checkpoint = state["last_checkpoint"]
    if not isinstance(checkpoint.get("at"), str) or not checkpoint["at"].strip():
        errors.append("last_checkpoint.at 无效")
    if not isinstance(checkpoint.get("summary"), str) or not checkpoint["summary"].strip():
        errors.append("last_checkpoint.summary 无效")

    step_required = {
        "id", "title", "acceptance", "status", "evidence",
        "attempts", "completion_summary", "started_at", "completed_at", "skip_reason",
    }
    safe_steps = []
    for index, step in enumerate(state["steps"], 1):
        if not isinstance(step, dict):
            errors.append(f"steps[{index}] 必须是对象")
            continue
        missing_step = sorted(step_required - step.keys())
        if missing_step:
            errors.append(f"steps[{index}] 缺少字段：" + ", ".join(missing_step))
            continue
        if any(not isinstance(step[key], str) or not step[key].strip() for key in ("id", "title", "acceptance", "status")):
            errors.append(f"steps[{index}] 基本字段无效")
            continue
        evidence_errors = text_list_errors(step["evidence"], f"steps[{index}].evidence")
        if evidence_errors:
            errors.extend(evidence_errors)
            continue
        errors.extend(attempt_list_errors(step["attempts"], f"steps[{index}].attempts"))
        if step["completion_summary"] is not None and (
            not isinstance(step["completion_summary"], str) or not step["completion_summary"].strip()
        ):
            errors.append(f"steps[{index}].completion_summary 无效")
        if step["started_at"] is not None and not isinstance(step["started_at"], str):
            errors.append(f"steps[{index}].started_at 无效")
        if step["completed_at"] is not None and not isinstance(step["completed_at"], str):
            errors.append(f"steps[{index}].completed_at 无效")
        if step["skip_reason"] is not None and not isinstance(step["skip_reason"], str):
            errors.append(f"steps[{index}].skip_reason 无效")
        safe_steps.append(step)
    if errors:
        return errors
    if not safe_steps:
        return ["步骤必须存在"]

    ids = [step["id"] for step in safe_steps]
    if len(ids) != len(set(ids)):
        errors.append("步骤 ID 必须唯一")
    active = [step for step in safe_steps if step["status"] in ACTIVE]
    if len(active) > 1:
        errors.append("最多只能有一个活动步骤")
    active_id = active[0]["id"] if active else None
    if state["current_step"] != active_id:
        errors.append("current_step 与活动步骤不一致")
    for step in safe_steps:
        if step["status"] not in {"pending", "in_progress", "blocked", "completed", "skipped"}:
            errors.append(f"步骤 {step['id']} 状态无效")
        if step["status"] == "completed" and not step["evidence"]:
            errors.append(f"步骤 {step['id']} 缺少完成证据")
        if step["status"] in TERMINAL and not step["completion_summary"]:
            errors.append(f"步骤 {step['id']} 缺少完成摘要")
        if step["status"] not in TERMINAL and step["completion_summary"] is not None:
            errors.append(f"步骤 {step['id']} 未终结却存在完成摘要")
        if step["status"] == "skipped":
            if not step["skip_reason"] or not step["skip_reason"].strip():
                errors.append(f"步骤 {step['id']} 缺少跳过理由")
            if not step["evidence"]:
                errors.append(f"步骤 {step['id']} 缺少跳过证据")

    active_blockers = [item for item in state["blockers"] if item["active"]]
    if state["status"] in ACTIVE and not state["next_action"].strip():
        errors.append("活动任务必须有 next_action")
    if state["status"] == "in_progress":
        if active and active[0]["status"] != "in_progress":
            errors.append("in_progress 任务的活动步骤必须为 in_progress")
        if active_blockers:
            errors.append("in_progress 任务不得保留活动阻塞")
    if state["status"] == "blocked":
        if active and active[0]["status"] != "blocked":
            errors.append("blocked 任务的活动步骤必须为 blocked")
        if not active_blockers:
            errors.append("blocked 任务必须有活动阻塞记录")
    if state["status"] == "completed":
        if any(step["status"] not in TERMINAL for step in safe_steps):
            errors.append("完成任务仍有未终结步骤")
        if state["current_step"] is not None or state["next_action"]:
            errors.append("完成任务不得保留活动步骤或 next_action")
        if not state["final_evidence"]:
            errors.append("完成任务缺少最终证据")
        if not state["verification"]:
            errors.append("完成任务缺少最终验证记录")
        if not any(step["status"] == "completed" for step in safe_steps):
            errors.append("完成任务至少需要一个实际完成步骤")
        if active_blockers:
            errors.append("完成任务仍有活动阻塞")
    return errors


def journal_document(path: Path, state: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    return {
        "journal_version": 2,
        "state_path": str(path),
        "task_id": state["task_id"],
        "revision": state["revision"],
        "updated_at": state["updated_at"],
        "event": event,
        "state_after": state,
    }


def journal_errors(path: Path, journal: Any) -> list[str]:
    if not isinstance(journal, dict):
        return ["journal 根节点必须是 JSON 对象"]
    required = {"journal_version", "state_path", "task_id", "revision", "updated_at", "event", "state_after"}
    missing = sorted(required - journal.keys())
    if missing:
        return ["journal 缺少字段：" + ", ".join(missing)]
    errors = []
    if journal["journal_version"] != 2:
        errors.append("不支持的 journal_version")
    if journal["state_path"] != str(path):
        errors.append("journal 绑定的状态路径不一致")
    if not isinstance(journal["task_id"], str) or not journal["task_id"].strip():
        errors.append("journal.task_id 无效")
    if not is_int(journal["revision"]):
        errors.append("journal.revision 无效")
    if not isinstance(journal["updated_at"], str) or not journal["updated_at"].strip():
        errors.append("journal.updated_at 无效")
    if not isinstance(journal["event"], dict):
        errors.append("journal.event 必须是对象")
    snapshot = journal["state_after"]
    snapshot_errors = audit(snapshot)
    if snapshot_errors:
        errors.append("journal.state_after 无效：" + "；".join(snapshot_errors))
    elif (
        journal["task_id"] != snapshot["task_id"]
        or journal["revision"] != snapshot["revision"]
        or journal["updated_at"] != snapshot["updated_at"]
    ):
        errors.append("journal 元数据与 state_after 不一致")
    return errors


def integrity_errors(path: Path, state: dict[str, Any]) -> list[str]:
    state_errors = audit(state)
    journal, journal_read_error = try_read_dict(journal_path(path))
    if state.get("schema_version") in {1, 2, 3} and journal and isinstance(journal.get("state_after"), dict):
        snapshot = journal["state_after"]
        if snapshot.get("schema_version") == SCHEMA_VERSION and snapshot.get("task_id") == state.get("task_id"):
            return ["旧版 state 落后于新版 journal，请先运行 recover"]
    if state_errors:
        return state_errors
    if journal_read_error:
        return [f"journal 不可用：{journal_read_error}；请运行 repair"]
    errors = journal_errors(path, journal)
    if errors:
        return errors
    snapshot = journal["state_after"]
    if journal["task_id"] != state["task_id"]:
        return ["state 与 journal 属于不同任务"]
    if journal["revision"] > state["revision"]:
        return ["journal 存在未落盘修订，请运行 recover"]
    if journal["revision"] < state["revision"]:
        return ["state revision 领先 journal，请运行 repair"]
    if snapshot != state:
        return ["同 revision 的 state 与 journal 不一致；核对现场后选择 recover --force 或 repair --force"]
    return []


def save(path: Path, state: dict[str, Any], event: dict[str, Any]) -> None:
    path = canonical_state_path(str(path))
    state["revision"] += 1
    state["updated_at"] = now()
    history = {
        "revision": state["revision"],
        "at": state["updated_at"],
        "type": clean(str(event.get("type", "")), "事件类型"),
        "summary": clean(str(event.get("summary", "")), "事件摘要"),
        "next_action": state["next_action"],
    }
    if event.get("step") is not None:
        history["step_id"] = event["step"]
    if event.get("result") is not None:
        history["result"] = event["result"]
    if event.get("changes"):
        history["changes"] = event["changes"]
    state["recent_history"] = (state["recent_history"] + [history])[-HISTORY_LIMIT:]
    errors = audit(state)
    if errors:
        fail("；".join(errors))
    write_json_atomic(journal_path(path), journal_document(path, state, history))
    write_json_atomic(path, state)


def step_by_id(state: dict[str, Any], step_id: str) -> dict[str, Any]:
    for step in state["steps"]:
        if step["id"] == step_id:
            return step
    fail(f"未知步骤：{step_id}")


def next_pending(state: dict[str, Any]) -> dict[str, Any] | None:
    return next((step for step in state["steps"] if step["status"] == "pending"), None)


def parse_step(raw: str, index: int) -> dict[str, Any]:
    title, marker, acceptance = raw.partition("=>")
    title = clean(title, "步骤标题")
    acceptance = acceptance.strip() if marker and acceptance.strip() else "提供可复核证据"
    return {
        "id": f"S{index}",
        "title": title,
        "acceptance": acceptance,
        "status": "pending",
        "evidence": [],
        "attempts": [],
        "completion_summary": None,
        "started_at": None,
        "completed_at": None,
        "skip_reason": None,
    }


def next_step_number(state: dict[str, Any]) -> int:
    numbers = [
        int(step["id"][1:]) for step in state["steps"]
        if step["id"].startswith("S") and step["id"][1:].isdigit()
    ]
    return max(numbers, default=0) + 1


def update_file_records(state: dict[str, Any], args: argparse.Namespace) -> None:
    root = state["workspace_root"]
    specs = []
    for attribute, status in (
        ("changed", "modified"),
        ("created", "created"),
        ("removed", "removed"),
        ("temporary", "temporary"),
        ("unchanged", "unchanged"),
    ):
        specs.extend((path, status) for path in absolute_paths(getattr(args, attribute, []), root))
    roles = path_assignments(getattr(args, "file_role", []), "--file-role", root)
    by_path = {item["path"]: item for item in state["changed_files"]}
    for path, status in specs:
        record = by_path.get(path, {"path": path, "role": ""})
        record.update(status=status, last_seen_revision=state["revision"] + 1)
        if path in roles:
            record["role"] = roles.pop(path)
        by_path[path] = record
    for path, role in roles.items():
        if path not in by_path:
            fail(f"--file-role 未对应已登记文件：{path}")
        by_path[path]["role"] = role
        by_path[path]["last_seen_revision"] = state["revision"] + 1
    state["changed_files"] = list(by_path.values())


def add_records(state: dict[str, Any], args: argparse.Namespace) -> None:
    update_file_records(state, args)
    stamp = now()
    for text in unique(getattr(args, "decision", [])):
        state["decisions"].append({"at": stamp, "text": text})
    for text in unique(getattr(args, "verification", [])):
        state["verification"].append({"at": stamp, "text": text})


def resolve_blockers(state: dict[str, Any], resolution: str) -> None:
    stamp = now()
    for blocker in state["blockers"]:
        if blocker["active"]:
            blocker["active"] = False
            blocker["resolved_at"] = stamp
            blocker["resolution"] = resolution


def cmd_init(args: argparse.Namespace, path: Path) -> None:
    with lock(path):
        occupied = [candidate for candidate in (path, journal_path(path), legacy_events_path(path)) if candidate.exists()]
        if occupied:
            fail("拒绝覆盖已有任务元数据：" + ", ".join(str(item) for item in occupied))
        created = now()
        steps = [parse_step(raw, index) for index, raw in enumerate(args.step, 1)]
        state = {
            "schema_version": SCHEMA_VERSION,
            "revision": 0,
            "task_id": "LT-" + uuid.uuid4().hex[:12],
            "workspace_root": str(Path(args.workspace_root).expanduser().resolve()),
            "goal": clean(args.goal, "目标"),
            "scope": unique(args.scope),
            "constraints": unique(args.constraint),
            "status": "in_progress",
            "steps": steps,
            "current_step": None,
            "next_action": clean(args.next_action, "next_action") if args.next_action else f"开始 {steps[0]['id']}：{steps[0]['title']}",
            "last_checkpoint": {"at": created, "summary": "任务已初始化"},
            "changed_files": [],
            "decisions": [],
            "verification": [],
            "blockers": [],
            "final_evidence": [],
            "recent_history": [],
            "task_revisions": [],
            "created_at": created,
            "updated_at": created,
        }
        save(path, state, {"type": "init", "summary": "任务已初始化"})
    print(f"OK: 已创建 {path}")


def cmd_recover(args: argparse.Namespace, path: Path) -> None:
    with lock(path):
        journal = read_dict(journal_path(path), "journal")
        errors = journal_errors(path, journal)
        if errors:
            fail("；".join(errors))
        snapshot = journal["state_after"]
        current, current_error = try_read_dict(path)
        if current is not None:
            current_errors = audit(current)
            if current_errors:
                print("WARN: state 结构损坏，将从 journal 恢复：" + "；".join(current_errors))
            else:
                if current["task_id"] != snapshot["task_id"]:
                    fail("现有 state 属于另一任务，拒绝覆盖")
                if current["revision"] > snapshot["revision"]:
                    fail("现有 state 比 journal 更新；请检查后运行 repair")
                if current["revision"] == snapshot["revision"] and current != snapshot and not args.force:
                    fail("同 revision 内容冲突；确认采用 journal 后重试 recover --force")
                if current == snapshot:
                    print(f"OK: 无需恢复 revision={snapshot['revision']}")
                    return
        elif current_error and path.exists() and not args.force:
            print(f"WARN: state 损坏，将从 journal 恢复：{current_error}")
        write_json_atomic(path, snapshot)
        errors = integrity_errors(path, snapshot)
        if errors:
            fail("恢复后校验失败：" + "；".join(errors))
    print(f"OK: 已从 journal 恢复 revision={snapshot['revision']}")


def cmd_repair(args: argparse.Namespace, path: Path) -> None:
    with lock(path):
        state = read_dict(path, "state")
        errors = audit(state)
        if errors:
            fail("state 无效，不能据此修复 journal：" + "；".join(errors))
        journal, _ = try_read_dict(journal_path(path))
        if journal and not journal_errors(path, journal):
            snapshot = journal["state_after"]
            if journal["task_id"] != state["task_id"]:
                fail("现有 journal 属于另一任务，拒绝覆盖")
            if journal["revision"] > state["revision"] and not args.force:
                fail("journal 比 state 更新；应运行 recover，若确认舍弃 journal 则用 repair --force")
            if journal["revision"] == state["revision"] and snapshot != state and not args.force:
                fail("同 revision 内容冲突；确认采用 state 后重试 repair --force")
        document = journal_document(path, state, {"type": "repair", "summary": "由有效 state 重建 journal"})
        write_json_atomic(journal_path(path), document)
        errors = integrity_errors(path, state)
        if errors:
            fail("修复后校验失败：" + "；".join(errors))
    print(f"OK: 已由 state 修复 journal revision={state['revision']}")


def legacy_snapshot(path: Path) -> dict[str, Any] | None:
    legacy = legacy_events_path(path)
    if not legacy.is_file():
        return None
    try:
        lines = legacy.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict) and isinstance(record.get("state_after"), dict):
            return record["state_after"]
    return None


def upgrade_state(state: dict[str, Any], version: int, path: Path) -> dict[str, Any]:
    root = state.get("workspace_root") or str(path.parent.resolve())
    state["workspace_root"] = str(Path(root).expanduser().resolve())
    state.setdefault("scope", [])
    state.setdefault("constraints", [])
    state.setdefault("decisions", [])
    state.setdefault("verification", [])
    state.setdefault("blockers", [])
    state.setdefault("final_evidence", [])
    for step in state.get("steps", []):
        if not isinstance(step, dict):
            continue
        step.setdefault("attempts", [])
        if "completion_summary" not in step:
            if step.get("status") == "completed" and unique(step.get("evidence", [])):
                step["completion_summary"] = unique(step["evidence"])[-1]
            elif step.get("status") == "skipped" and isinstance(step.get("skip_reason"), str):
                step["completion_summary"] = step["skip_reason"].strip() or None
            else:
                step["completion_summary"] = None
    records = []
    for item in state.get("changed_files", []):
        if isinstance(item, dict) and isinstance(item.get("path"), str):
            record = dict(item)
            record["path"] = absolute_paths([record["path"]], state["workspace_root"])[0]
            record.setdefault("status", "modified" if Path(record["path"]).exists() else "removed")
            record.setdefault("role", "")
            record["last_seen_revision"] = state.get("revision", 0) + 1
        elif isinstance(item, str) and item.strip():
            file_path = absolute_paths([item], state["workspace_root"])[0]
            exists = Path(file_path).exists()
            record = {
                "path": file_path,
                "status": "modified" if exists else "removed",
                "role": "" if exists else f"schema {version} 迁移时路径不存在",
                "last_seen_revision": state.get("revision", 0) + 1,
            }
        else:
            continue
        records.append(record)
    state["changed_files"] = list({item["path"]: item for item in records}.values())
    state["recent_history"] = []
    state["task_revisions"] = []
    state["schema_version"] = SCHEMA_VERSION
    return state


def cmd_migrate(args: argparse.Namespace, path: Path) -> None:
    with lock(path):
        journal, journal_error = try_read_dict(journal_path(path))
        state, state_error = try_read_dict(path)
        state_was_missing = state is None
        if state is None:
            if journal and isinstance(journal.get("state_after"), dict):
                state = journal["state_after"]
            else:
                state = legacy_snapshot(path)
            if state is None:
                fail(f"没有可迁移的 state 或旧版快照：{state_error or '不存在'}")
        elif journal and isinstance(journal.get("state_after"), dict):
            snapshot = journal["state_after"]
            if journal.get("task_id") != state.get("task_id"):
                fail("state 与 journal 属于不同任务")
            journal_revision = journal.get("revision")
            state_revision = state.get("revision")
            if is_int(journal_revision) and is_int(state_revision):
                if journal_revision > state_revision:
                    if snapshot.get("schema_version") == SCHEMA_VERSION:
                        fail("journal 已包含 schema 4 未落盘状态，请先运行 recover")
                    state = snapshot
                elif journal_revision < state_revision and not args.force:
                    fail("state revision 领先 journal；核对后用 migrate --force")
                elif journal_revision == state_revision and snapshot != state and not args.force:
                    fail("同 revision 内容冲突；核对后用 migrate --force")
        elif journal_error and journal_path(path).exists() and not args.force:
            fail(f"journal 不可用：{journal_error}；核对后用 migrate --force")
        version = state.get("schema_version")
        if version == SCHEMA_VERSION:
            if state_was_missing and journal:
                fail(f"journal 已包含 schema_version {SCHEMA_VERSION}；请运行 recover")
            fail(f"状态已是 schema_version {SCHEMA_VERSION}；journal 缺失时请运行 repair")
        if version not in {1, 2, 3}:
            fail("只支持从 schema_version 1、2 或 3 迁移")
        skip_evidence = assignments(args.skip_evidence, "--skip-evidence")
        known_ids = {step.get("id") for step in state.get("steps", []) if isinstance(step, dict)}
        unknown = sorted(skip_evidence.keys() - known_ids)
        if unknown:
            fail("跳过证据包含未知步骤：" + ", ".join(unknown))
        for step in state.get("steps", []):
            if isinstance(step, dict) and step.get("status") == "skipped" and not unique(step.get("evidence", [])):
                evidence = skip_evidence.get(step.get("id"))
                if not evidence:
                    fail(f"旧版 skipped 步骤 {step.get('id')} 缺少证据；请传 --skip-evidence {step.get('id')}=...")
                step["evidence"] = [evidence]
        if state.get("status") == "completed" and not state.get("verification"):
            verification = unique(args.final_verification)
            if not verification:
                fail("旧版完成状态缺少验证；请传非空 --final-verification")
            stamp = now()
            state["verification"] = [{"at": stamp, "text": text} for text in verification]
        state = upgrade_state(state, version, path)
        summary = f"状态协议从 schema {version} 迁移至 {SCHEMA_VERSION}"
        state["decisions"].append({"at": now(), "text": summary})
        save(path, state, {"type": "migrate", "summary": summary})
    print(f"OK: migrate revision={state['revision']} schema={SCHEMA_VERSION}")


def artifact_warnings(state: dict[str, Any]) -> list[str]:
    warnings = []
    for item in state["changed_files"]:
        exists = Path(item["path"]).exists()
        if item["status"] in {"created", "modified", "unchanged"} and not exists:
            warnings.append(f"预期存在但缺失：{item['path']}")
        elif item["status"] == "removed" and exists:
            warnings.append(f"标记为 removed 但仍存在：{item['path']}")
    return warnings


def cmd_read(args: argparse.Namespace, path: Path) -> None:
    with lock(path, exclusive=False):
        state = read_dict(path, "state")
        errors = integrity_errors(path, state)
    if errors:
        fail("；".join(errors))
    if args.command == "show":
        print(json.dumps(state, ensure_ascii=False, indent=2))
        return
    if args.command == "audit":
        print(f"OK: schema={SCHEMA_VERSION} revision={state['revision']} status={state['status']}")
        for warning in artifact_warnings(state):
            print(f"WARN: {warning}")
        return
    current = step_by_id(state, state["current_step"]) if state["current_step"] else None
    print(f"状态文件: {path}")
    print(f"任务根目录: {state['workspace_root']}")
    print(f"任务: {state['goal']}")
    print("范围: " + (" | ".join(state["scope"]) if state["scope"] else "未单列"))
    print("约束: " + (" | ".join(state["constraints"]) if state["constraints"] else "未单列"))
    print(f"状态/修订: {state['status']} / {state['revision']}")
    print(f"当前步骤: {current['id'] + ' ' + current['title'] if current else '无'}")
    if current:
        print(f"当前验收条件: {current['acceptance']}")
        print("当前已有证据: " + (" | ".join(current["evidence"]) if current["evidence"] else "无"))
        attempts = current["attempts"][-3:]
        print("最近尝试: " + (" | ".join(
            f"{item['result']}:{item['action']}（{item['reason']}）" for item in attempts
        ) if attempts else "无"))
    elif state["final_evidence"]:
        print("最终阶段已有证据: " + " | ".join(state["final_evidence"]))
    print(f"最近检查点: {state['last_checkpoint']['summary']}")
    print(f"唯一下一动作: {state['next_action'] or '无（任务已完成）'}")
    remaining = [f"{step['id']}:{step['status']}:{step['title']}" for step in state["steps"] if step["status"] not in TERMINAL]
    print("未终结步骤: " + (" | ".join(remaining) if remaining else "无"))
    print("已知变更文件: " + (" | ".join(
        f"{item['status']}:{item['path']}" + (f"（{item['role']}）" if item["role"] else "")
        for item in state["changed_files"]
    ) if state["changed_files"] else "无"))
    print("近期历史: " + (" | ".join(
        f"r{item['revision']}:{item['type']}:{item['summary']}"
        for item in state["recent_history"][-5:]
    ) if state["recent_history"] else "无"))
    latest_revision = state["task_revisions"][-1] if state["task_revisions"] else None
    print("最近任务修订: " + (
        f"{latest_revision['reason']}；字段={','.join(latest_revision['changes'])}" if latest_revision else "无"
    ))
    print("关键决定: " + (" | ".join(item["text"] for item in state["decisions"][-5:]) if state["decisions"] else "无"))
    recent_checks = state["verification"][-5:]
    print("最近验证: " + (" | ".join(item["text"] for item in recent_checks) if recent_checks else "无"))
    active_blockers = [item["reason"] for item in state["blockers"] if item["active"]]
    print("活动阻塞: " + (" | ".join(active_blockers) if active_blockers else "无"))
    for warning in artifact_warnings(state):
        print(f"现场警告: {warning}")


def mutate(args: argparse.Namespace, path: Path) -> None:
    with lock(path):
        state = read_dict(path, "state")
        errors = integrity_errors(path, state)
        if errors:
            fail("现有状态无效：" + "；".join(errors))
        if state["status"] == "completed":
            fail("任务已完成，不允许继续修改状态")
        event: dict[str, Any] = {"type": args.command}

        if args.command == "revise":
            if args.goal is None and args.scope is None and args.constraint is None:
                fail("revise 至少需要修改 goal、scope 或 constraint 之一")
            changes = {}
            if args.goal is not None:
                new_goal = clean(args.goal, "目标")
                if new_goal != state["goal"]:
                    changes["goal"] = {"before": state["goal"], "after": new_goal}
                    state["goal"] = new_goal
            if args.scope is not None:
                new_scope = unique(args.scope)
                if new_scope != state["scope"]:
                    changes["scope"] = {
                        "added": [item for item in new_scope if item not in state["scope"]],
                        "removed": [item for item in state["scope"] if item not in new_scope],
                    }
                    state["scope"] = new_scope
            if args.constraint is not None:
                new_constraints = unique(args.constraint)
                if new_constraints != state["constraints"]:
                    changes["constraints"] = {
                        "added": [item for item in new_constraints if item not in state["constraints"]],
                        "removed": [item for item in state["constraints"] if item not in new_constraints],
                    }
                    state["constraints"] = new_constraints
            if not changes:
                fail("revise 未产生实际变化")
            reason = clean(args.reason, "修订原因")
            revision_record = {"at": now(), "reason": reason, "changes": changes}
            state["task_revisions"] = (state["task_revisions"] + [revision_record])[-TASK_REVISION_LIMIT:]
            decision = f"任务修订：{reason}；字段={','.join(changes)}"
            state["decisions"].append({"at": now(), "text": decision})
            state["next_action"] = clean(args.next_action, "next_action")
            state["last_checkpoint"] = {"at": now(), "summary": decision}
            event.update(summary=decision, changes=changes)
        elif args.command == "add-step":
            raw = args.title + (" => " + args.acceptance if args.acceptance else "")
            step = parse_step(raw, next_step_number(state))
            insert_at = len(state["steps"])
            target_id = args.before or args.after
            if target_id:
                target = step_by_id(state, target_id)
                target_index = state["steps"].index(target)
                insert_at = target_index if args.before else target_index + 1
            first_nonterminal = next(
                (index for index, item in enumerate(state["steps"]) if item["status"] not in TERMINAL),
                len(state["steps"]),
            )
            if insert_at < first_nonterminal:
                fail("不能把新步骤插入已经终结的历史步骤之前")
            if state["current_step"]:
                current_index = state["steps"].index(step_by_id(state, state["current_step"]))
                if insert_at <= current_index:
                    fail("不能把新步骤插入当前活动步骤之前")
            state["steps"].insert(insert_at, step)
            reason = clean(args.reason, "新增步骤原因")
            summary = f"新增步骤 {step['id']}：{step['title']}；原因：{reason}"
            state["decisions"].append({"at": now(), "text": summary})
            state["last_checkpoint"] = {"at": now(), "summary": summary}
            if state["status"] == "in_progress" and not state["current_step"]:
                pending = next_pending(state)
                state["next_action"] = f"开始 {pending['id']}：{pending['title']}"
            event.update(
                step=step["id"], summary=summary,
                changes={"position": insert_at + 1, "before": args.before, "after": args.after},
            )
        elif args.command == "begin":
            if state["status"] == "blocked" or state["current_step"]:
                fail("已有活动或阻塞步骤，请先恢复、完成、跳过或解除阻塞")
            step = step_by_id(state, args.step_id)
            if step["status"] != "pending":
                fail(f"只能开始 pending 步骤，当前为 {step['status']}")
            expected = next_pending(state)
            if not expected or expected["id"] != step["id"]:
                fail(f"必须按顺序开始最早 pending 步骤：{expected['id'] if expected else '无'}")
            step["status"] = "in_progress"
            step["started_at"] = step["started_at"] or now()
            state["current_step"] = step["id"]
            state["next_action"] = clean(args.next_action, "next_action")
            event.update(step=step["id"], summary=step["title"])
        elif args.command == "checkpoint":
            if state["status"] != "in_progress":
                fail("只有 in_progress 任务可以写工作检查点")
            summary = clean(args.summary, "检查点摘要")
            next_action = clean(args.next_action, "next_action")
            add_records(state, args)
            evidence = unique(args.evidence)
            if evidence:
                if state["current_step"]:
                    step = step_by_id(state, state["current_step"])
                    step["evidence"] = unique(step["evidence"] + evidence)
                else:
                    state["final_evidence"] = unique(state["final_evidence"] + evidence)
            state["last_checkpoint"] = {"at": now(), "summary": summary}
            state["next_action"] = next_action
            event.update(summary=summary)
        elif args.command == "attempt":
            if state["status"] != "in_progress" or not state["current_step"]:
                fail("attempt 只能记录当前 in_progress 步骤")
            step = step_by_id(state, state["current_step"])
            attempt = {
                "at": now(),
                "action": clean(args.action, "尝试动作"),
                "result": args.result,
                "reason": clean(args.reason, "尝试结论"),
            }
            step["attempts"] = (step["attempts"] + [attempt])[-ATTEMPT_LIMIT:]
            add_records(state, args)
            state["next_action"] = clean(args.next_action, "next_action")
            summary = f"尝试 {args.result}：{attempt['action']}；{attempt['reason']}"
            state["last_checkpoint"] = {"at": now(), "summary": summary}
            event.update(step=step["id"], result=args.result, summary=summary)
        elif args.command == "complete":
            step = step_by_id(state, args.step_id)
            if state["current_step"] != step["id"] or step["status"] != "in_progress":
                fail("只能完成当前 in_progress 步骤")
            evidence = unique(args.evidence)
            if not evidence:
                fail("完成证据不能为空")
            step["evidence"] = unique(step["evidence"] + evidence)
            step["status"] = "completed"
            step["completed_at"] = now()
            step["completion_summary"] = clean(args.summary, "完成摘要") if args.summary else evidence[-1]
            add_records(state, args)
            state["current_step"] = None
            following = next_pending(state)
            state["next_action"] = clean(args.next_action, "next_action") if args.next_action else (
                f"开始 {following['id']}：{following['title']}" if following else "执行最终验收并完成任务"
            )
            summary = f"已完成 {step['id']}：{step['title']}"
            state["last_checkpoint"] = {"at": now(), "summary": summary}
            event.update(step=step["id"], summary=summary)
        elif args.command == "skip":
            step = step_by_id(state, args.step_id)
            if step["status"] not in {"pending", "in_progress", "blocked"}:
                fail("只能跳过 pending、in_progress 或 blocked 步骤")
            if state["current_step"] not in {None, step["id"]}:
                fail("另有活动步骤")
            expected = next_pending(state)
            if state["current_step"] is None and (not expected or expected["id"] != step["id"]):
                fail(f"必须按顺序处理最早 pending 步骤：{expected['id'] if expected else '无'}")
            reason = clean(args.reason, "跳过理由")
            evidence = unique(args.evidence)
            if not evidence:
                fail("跳过证据不能为空")
            step["status"] = "skipped"
            step["skip_reason"] = reason
            step["evidence"] = unique(step["evidence"] + evidence)
            step["completion_summary"] = reason
            step["completed_at"] = now()
            state["current_step"] = None
            if state["status"] == "blocked":
                resolve_blockers(state, "步骤被跳过")
                state["status"] = "in_progress"
            following = next_pending(state)
            state["next_action"] = clean(args.next_action, "next_action") if args.next_action else (
                f"开始 {following['id']}：{following['title']}" if following else "执行最终验收并完成任务"
            )
            summary = f"已跳过 {step['id']}：{reason}"
            state["last_checkpoint"] = {"at": now(), "summary": summary}
            event.update(step=step["id"], summary=summary)
        elif args.command == "block":
            if state["status"] != "in_progress":
                fail("任务已处于 blocked 状态")
            reason = clean(args.reason, "阻塞原因")
            step = step_by_id(state, state["current_step"]) if state["current_step"] else next_pending(state)
            if step:
                state["current_step"] = step["id"]
                step["status"] = "blocked"
                step["started_at"] = step["started_at"] or now()
            existing = next((item for item in reversed(state["blockers"]) if item["reason"] == reason), None)
            if existing:
                existing.update(at=now(), count=existing["count"] + 1, active=True)
                existing.pop("resolved_at", None)
                existing.pop("resolution", None)
            else:
                state["blockers"].append({"at": now(), "reason": reason, "count": 1, "active": True})
            state["status"] = "blocked"
            state["next_action"] = clean(args.next_action, "next_action")
            summary = f"受阻：{reason}"
            state["last_checkpoint"] = {"at": now(), "summary": summary}
            event.update(step=step["id"] if step else None, summary=summary)
        elif args.command == "unblock":
            if state["status"] != "blocked":
                fail("任务当前未受阻")
            step = step_by_id(state, state["current_step"]) if state["current_step"] else None
            if step:
                step["status"] = "in_progress"
            resolve_blockers(state, "阻塞已解决")
            state["status"] = "in_progress"
            summary = clean(args.summary, "解除阻塞摘要")
            state["next_action"] = clean(args.next_action, "next_action")
            state["last_checkpoint"] = {"at": now(), "summary": summary}
            event.update(step=step["id"] if step else None, summary=summary)
        else:
            fail(f"未实现命令：{args.command}")
        save(path, state, event)
    print(f"OK: {args.command} revision={state['revision']} next={state['next_action']}")


def cmd_finish(args: argparse.Namespace, path: Path) -> None:
    with lock(path):
        state = read_dict(path, "state")
        errors = integrity_errors(path, state)
        if errors:
            fail("现有状态无效：" + "；".join(errors))
        if state["status"] == "completed":
            fail("任务已经完成")
        unfinished = [step["id"] for step in state["steps"] if step["status"] not in TERMINAL]
        if unfinished:
            fail("仍有未终结步骤：" + ", ".join(unfinished))
        if any(item["active"] for item in state["blockers"]):
            fail("仍有活动阻塞")
        if not any(step["status"] == "completed" for step in state["steps"]):
            fail("至少需要一个实际完成步骤，不能把全部步骤跳过后标记完成")
        evidence = unique(args.evidence)
        verification = unique(args.verification)
        if not evidence:
            fail("最终证据不能为空")
        if not verification:
            fail("最终验证不能为空")
        state["status"] = "completed"
        state["current_step"] = None
        state["next_action"] = ""
        state["final_evidence"] = unique(state["final_evidence"] + evidence)
        stamp = now()
        state["verification"].extend({"at": stamp, "text": text} for text in verification)
        state["last_checkpoint"] = {"at": now(), "summary": "任务已通过最终验收"}
        save(path, state, {"type": "finish", "summary": "任务已通过最终验收"})
    print(f"OK: finish revision={state['revision']}")


def add_file_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--changed", action="append", default=[], help="登记为 modified")
    parser.add_argument("--created", action="append", default=[])
    parser.add_argument("--removed", action="append", default=[])
    parser.add_argument("--temporary", action="append", default=[])
    parser.add_argument("--unchanged", action="append", default=[])
    parser.add_argument("--file-role", action="append", default=[], help="路径=用途说明")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", default=str(DEFAULT_STATE), help="必须以 state.json 结尾的状态路径")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init")
    init.add_argument("--goal", required=True)
    init.add_argument("--workspace-root", default=".")
    init.add_argument("--scope", action="append", default=[])
    init.add_argument("--constraint", action="append", default=[])
    init.add_argument("--step", action="append", required=True)
    init.add_argument("--next-action")

    sub.add_parser("show")
    sub.add_parser("resume")
    sub.add_parser("audit")

    recover = sub.add_parser("recover")
    recover.add_argument("--force", action="store_true")

    repair = sub.add_parser("repair")
    repair.add_argument("--force", action="store_true")

    migrate = sub.add_parser("migrate")
    migrate.add_argument("--skip-evidence", action="append", default=[])
    migrate.add_argument("--final-verification", action="append", default=[])
    migrate.add_argument("--force", action="store_true")

    begin = sub.add_parser("begin")
    begin.add_argument("step_id")
    begin.add_argument("--next-action", required=True)

    checkpoint = sub.add_parser("checkpoint")
    checkpoint.add_argument("--summary", required=True)
    checkpoint.add_argument("--next-action", required=True)
    add_file_arguments(checkpoint)
    checkpoint.add_argument("--evidence", action="append", default=[])
    checkpoint.add_argument("--decision", action="append", default=[])
    checkpoint.add_argument("--verification", action="append", default=[])

    attempt = sub.add_parser("attempt")
    attempt.add_argument("--action", required=True)
    attempt.add_argument("--result", choices=sorted(ATTEMPT_RESULTS), required=True)
    attempt.add_argument("--reason", required=True)
    attempt.add_argument("--next-action", required=True)
    add_file_arguments(attempt)
    attempt.add_argument("--decision", action="append", default=[])
    attempt.add_argument("--verification", action="append", default=[])

    complete = sub.add_parser("complete")
    complete.add_argument("step_id")
    complete.add_argument("--evidence", action="append", required=True)
    complete.add_argument("--summary")
    add_file_arguments(complete)
    complete.add_argument("--verification", action="append", default=[])
    complete.add_argument("--decision", action="append", default=[])
    complete.add_argument("--next-action")

    revise = sub.add_parser("revise")
    revise.add_argument("--goal")
    revise.add_argument("--scope", action="append")
    revise.add_argument("--constraint", action="append")
    revise.add_argument("--reason", required=True)
    revise.add_argument("--next-action", required=True)

    add = sub.add_parser("add-step")
    add.add_argument("--title", required=True)
    add.add_argument("--acceptance")
    add.add_argument("--reason", required=True)
    position = add.add_mutually_exclusive_group()
    position.add_argument("--before")
    position.add_argument("--after")

    skip = sub.add_parser("skip")
    skip.add_argument("step_id")
    skip.add_argument("--reason", required=True)
    skip.add_argument("--evidence", action="append", required=True)
    skip.add_argument("--next-action")

    block = sub.add_parser("block")
    block.add_argument("--reason", required=True)
    block.add_argument("--next-action", required=True)

    unblock = sub.add_parser("unblock")
    unblock.add_argument("--summary", required=True)
    unblock.add_argument("--next-action", required=True)

    finish = sub.add_parser("finish")
    finish.add_argument("--evidence", action="append", required=True)
    finish.add_argument("--verification", action="append", required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    path = canonical_state_path(args.state)
    if args.command == "init":
        cmd_init(args, path)
    elif args.command == "recover":
        cmd_recover(args, path)
    elif args.command == "repair":
        cmd_repair(args, path)
    elif args.command == "migrate":
        cmd_migrate(args, path)
    elif args.command in {"show", "resume", "audit"}:
        cmd_read(args, path)
    elif args.command == "finish":
        cmd_finish(args, path)
    else:
        mutate(args, path)


if __name__ == "__main__":
    main()
