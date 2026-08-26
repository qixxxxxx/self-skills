#!/usr/bin/env python3
"""Manage schema 2 transactional, recoverable design-project state packages."""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import sys
import tempfile
import uuid
from pathlib import Path


SCHEMA_VERSION = "2"
CORE_TYPES = {
    "PROJECT.md": "project",
    "PROGRESS.md": "progress",
    "ACTIVE.md": "active",
    "DECISIONS.md": "decisions",
    "ITEMS.md": "items",
}
BASE_KEYS = {
    "schema_version",
    "document_type",
    "project_id",
    "project_title",
    "state_id",
    "state_dir",
    "checkpoint",
    "formal_version",
}
PROGRESS_KEYS = {
    "soft_checkpoint",
    "current_level",
    "current_stage",
    "stage_status",
    "project_status",
    "current_question",
    "stage_gates_done",
    "stage_gates_total",
    "project_gates_done",
    "project_gates_total",
    "blocked_count",
}
ACTIVE_KEYS = {
    "soft_checkpoint",
    "current_level",
    "current_stage",
    "current_question",
    "explanation_depth",
}
ITEMS_KEYS = {"soft_checkpoint", "current_level", "current_stage", "current_question"}
STAGE_STATUSES = {
    "not-started",
    "discussing",
    "waiting-confirmation",
    "confirmed",
    "blocked",
    "reopened",
    "completed",
}
PROJECT_STATUSES = {
    "active",
    "blocked",
    "ready-for-build",
    "building",
    "awaiting-acceptance",
    "completed",
}
ITEM_TYPES = {"question", "gate", "assumption", "deferred", "blocker", "fact", "decision"}
ITEM_STATUSES = {
    "pending",
    "active",
    "confirmed",
    "completed",
    "deferred",
    "not-applicable",
    "blocked",
    "reopened",
    "superseded",
}
TERMINAL_REQUIRED = {"confirmed", "completed", "not-applicable", "superseded"}
GATE_TERMINAL = {"completed", "not-applicable", "superseded"}
INVALID_TERMINAL_EVIDENCE = {"", "-", "无", "待补充", "待用户确认", "ACTIVE.md"}
ITEM_HEADERS = ["ID", "类型", "必需", "状态", "摘要", "阶段", "依赖", "责任人", "证据或落点"]
REQUIRED_HEADINGS = {
    "PROJECT.md": ["# 项目现行方案", "## 项目卡片", "## 顶层流程", "## 阶段索引"],
    "PROGRESS.md": ["# 项目进度", "## 当前状态", "## 门槛摘要", "## 下一动作"],
    "ACTIVE.md": ["# 当前讨论快照", "## 当前确认点", "## 待确认", "## 当前确认点流水"],
    "DECISIONS.md": ["# 决定记录"],
    "ITEMS.md": ["# 讨论项总账", "## 讨论项"],
}
STAGE_HEADINGS = [
    "## 输入",
    "## 前置条件",
    "## 动作",
    "## 输出",
    "## 完成条件",
    "## 评价方式",
    "## 异常回退",
    "## 责任边界",
]
ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
STATE_ID_RE = re.compile(r"^DPS-[0-9a-f]{12}$")
CP_RE = re.compile(r"^CP-\d{4,}$")
SC_RE = re.compile(r"^SC-\d{4,}$")
VERSION_RE = re.compile(r"^v\d{4,}$")
QUESTION_RE = re.compile(r"^Q-\d{4,}$")
ITEM_ID_RE = re.compile(r"^(?:Q-\d{4,}|G-\d{2,}-\d{2,}|[ABFT]-\d{4,}|D-\d{3,})$")
STAGE_ID_RE = re.compile(r"^stage-[a-z0-9]+(?:-[a-z0-9]+)*$")
STAGE_LINK_RE = re.compile(r"stages/[^)\s]+\.md")
STATE_META_DIR = ".project-state"


class StateError(Exception):
    pass


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def quoted(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def render(meta: dict[str, str], body: str) -> str:
    lines = ["---", *(f"{key}: {quoted(value)}" for key, value in meta.items()), "---", "", body.rstrip(), ""]
    return "\n".join(lines)


def parse_frontmatter_text(text: str, source: str) -> tuple[dict[str, str], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise StateError(f"{source}: 缺少 YAML frontmatter")
    try:
        end = next(i for i, line in enumerate(lines[1:], 1) if line.strip() == "---")
    except StopIteration as exc:
        raise StateError(f"{source}: frontmatter 未闭合") from exc
    meta: dict[str, str] = {}
    for line in lines[1:end]:
        if not line.strip():
            continue
        if ":" not in line:
            raise StateError(f"{source}: 非法元数据行 {line!r}")
        key, value = (part.strip() for part in line.split(":", 1))
        if key in meta:
            raise StateError(f"{source}: 元数据字段重复 {key}")
        if not (value.startswith('"') and value.endswith('"')):
            raise StateError(f"{source}: {key} 必须是带双引号的字符串")
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise StateError(f"{source}: {key} 不是合法字符串") from exc
        if not isinstance(parsed, str):
            raise StateError(f"{source}: {key} 必须是字符串")
        meta[key] = parsed
    return meta, "\n".join(lines[end + 1 :]).lstrip("\n")


def parse_frontmatter(path: Path) -> tuple[dict[str, str], str]:
    return parse_frontmatter_text(path.read_text(encoding="utf-8"), str(path))


def update_text_meta(text: str, source: str, updates: dict[str, str]) -> str:
    meta, body = parse_frontmatter_text(text, source)
    meta.update(updates)
    return render(meta, body)


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except Exception:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
        raise


def atomic_json(path: Path, value: object) -> None:
    atomic_write(path, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise StateError(f"{path}: JSON 无法读取: {exc}") from exc
    if not isinstance(value, dict):
        raise StateError(f"{path}: JSON 根节点必须是对象")
    return value


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def package_files(base: Path, tolerate_missing: bool = False) -> dict[str, str]:
    files: dict[str, str] = {}
    for name in CORE_TYPES:
        path = base / name
        if path.is_file():
            files[name] = path.read_text(encoding="utf-8")
        elif not tolerate_missing:
            raise StateError(f"{path}: 文件不存在")
    stages = base / "stages"
    if stages.is_dir():
        for path in sorted(stages.glob("*.md")):
            files[path.relative_to(base).as_posix()] = path.read_text(encoding="utf-8")
    elif not tolerate_missing:
        raise StateError(f"{stages}: 目录不存在")
    return files


def write_package(base: Path, files: dict[str, str], progress_last: bool = False) -> None:
    order = sorted(files)
    if progress_last and "PROGRESS.md" in order:
        order.remove("PROGRESS.md")
        order.append("PROGRESS.md")
    for relative in order:
        atomic_write(base / relative, files[relative])


def hash_files(files: dict[str, str]) -> dict[str, str]:
    return {name: sha256(text) for name, text in sorted(files.items())}


def formal_files(files: dict[str, str]) -> dict[str, str]:
    return {
        name: text
        for name, text in files.items()
        if name in {"PROJECT.md", "DECISIONS.md"} or name.startswith("stages/")
    }


def digest_hashes(hashes: dict[str, str]) -> str:
    return sha256(json.dumps(hashes, sort_keys=True, separators=(",", ":")))


def increment(value: str, pattern: re.Pattern[str], prefix: str) -> str:
    if not pattern.fullmatch(value):
        raise StateError(f"无法递增非法编号 {value}")
    match = re.search(r"\d+$", value)
    if match is None:
        raise StateError(f"无法递增编号 {value}")
    number = int(match.group()) + 1
    width = max(4, len(str(number)))
    return f"{prefix}{number:0{width}d}"


def require_keys(path: Path, meta: dict[str, str], keys: set[str], errors: list[str]) -> None:
    missing = sorted(keys - meta.keys())
    if missing:
        errors.append(f"{path}: 缺少字段 {', '.join(missing)}")


def require_headings(path: Path, body: str, headings: list[str], errors: list[str]) -> None:
    for heading in headings:
        if heading not in body:
            errors.append(f"{path}: 缺少正文栏目 {heading}")


def require_body_marker(path: Path, body: str, label: str, expected: str, errors: list[str]) -> None:
    match = re.search(rf"^- {re.escape(label)}：(.*)$", body, flags=re.MULTILINE)
    if match is None:
        errors.append(f"{path}: 缺少正文状态标记 {label}")
    elif match.group(1).strip() != expected:
        errors.append(f"{path}: 正文 {label}={match.group(1).strip()}，应为 {expected}")


def sync_progress_body(body: str, meta: dict[str, str]) -> str:
    replacements = {
        "当前确认点": meta["current_question"],
        "当前阶段": f"{meta['stage_gates_done']}/{meta['stage_gates_total']}",
        "全项目": f"{meta['project_gates_done']}/{meta['project_gates_total']}",
    }
    for label, value in replacements.items():
        pattern = rf"^- {re.escape(label)}：.*$"
        if re.search(pattern, body, flags=re.MULTILINE):
            body = re.sub(pattern, f"- {label}：{value}", body, count=1, flags=re.MULTILINE)
            continue
        heading = "## 当前状态" if label == "当前确认点" else "## 门槛摘要"
        body = body.replace(heading, f"{heading}\n\n- {label}：{value}", 1)
    return body


def sync_active_question(body: str, question: str) -> str:
    if re.search(r"^- 编号：.*$", body, flags=re.MULTILINE):
        return re.sub(r"^- 编号：.*$", f"- 编号：{question}", body, count=1, flags=re.MULTILINE)
    return body.replace("## 当前确认点", f"## 当前确认点\n\n- 编号：{question}", 1)


def parse_items(path: Path, body: str, errors: list[str]) -> list[dict[str, str]]:
    lines = body.splitlines()
    try:
        start = lines.index("## 讨论项") + 1
    except ValueError:
        return []
    table_lines = [line for line in lines[start:] if line.strip().startswith("|")]
    if len(table_lines) < 2:
        errors.append(f"{path}: 讨论项表格不存在")
        return []

    def cells(line: str) -> list[str]:
        return [cell.strip() for cell in line.strip().strip("|").split("|")]

    if cells(table_lines[0]) != ITEM_HEADERS:
        errors.append(f"{path}: 讨论项表头或顺序错误")
        return []
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for line in table_lines[2:]:
        values = cells(line)
        if len(values) != len(ITEM_HEADERS):
            errors.append(f"{path}: 讨论项列数错误 {line}")
            continue
        item = dict(zip(ITEM_HEADERS, values))
        item_id = item["ID"]
        if not ITEM_ID_RE.fullmatch(item_id):
            errors.append(f"{path}: 讨论项 ID 格式错误 {item_id}")
        if item_id in seen:
            errors.append(f"{path}: 讨论项 ID 重复 {item_id}")
        seen.add(item_id)
        if item["类型"] not in ITEM_TYPES:
            errors.append(f"{path}: {item_id} 类型非法")
        if item["必需"] not in {"yes", "no"}:
            errors.append(f"{path}: {item_id} 必需字段应为 yes/no")
        if item["状态"] not in ITEM_STATUSES:
            errors.append(f"{path}: {item_id} 状态非法")
        if not STAGE_ID_RE.fullmatch(item["阶段"]):
            errors.append(f"{path}: {item_id} 阶段格式错误")
        if not item["摘要"] or not item["责任人"] or not item["证据或落点"]:
            errors.append(f"{path}: {item_id} 存在空白关键字段")
        rows.append(item)
    ids = {row["ID"] for row in rows}
    by_id = {row["ID"]: row for row in rows}
    for row in rows:
        dependencies = [] if row["依赖"] in {"-", "无"} else [part.strip() for part in row["依赖"].split(",")]
        missing = [item_id for item_id in dependencies if item_id not in ids]
        if missing:
            errors.append(f"{path}: {row['ID']} 引用了不存在的依赖 {', '.join(missing)}")
        elif row["状态"] in {"active", "confirmed", "completed", "not-applicable"}:
            unresolved = [item_id for item_id in dependencies if not required_item_closed(by_id[item_id])]
            if unresolved:
                errors.append(f"{path}: {row['ID']} 的活动或终结状态依赖未关闭项目 {', '.join(unresolved)}")
        if row["状态"] in TERMINAL_REQUIRED and row["证据或落点"] in INVALID_TERMINAL_EVIDENCE:
            errors.append(f"{path}: {row['ID']} 已终结但没有有效证据或决定依据")
    return rows


def required_item_closed(row: dict[str, str]) -> bool:
    terminal = GATE_TERMINAL if row["类型"] == "gate" else TERMINAL_REQUIRED
    return row["状态"] in terminal


def parse_decision_blocks(body: str) -> dict[str, str]:
    matches = list(re.finditer(r"^## (D-\d{3,})(?:\s|：|$).*", body, flags=re.MULTILINE))
    return {
        match.group(1): body[match.start() : matches[index + 1].start() if index + 1 < len(matches) else len(body)]
        for index, match in enumerate(matches)
    }


def validate_package(base: Path, state_root: Path) -> tuple[list[str], dict[str, dict[str, str]], list[dict[str, str]]]:
    errors: list[str] = []
    metas: dict[str, dict[str, str]] = {}
    bodies: dict[str, str] = {}
    for name, doc_type in CORE_TYPES.items():
        path = base / name
        if not path.is_file():
            errors.append(f"{path}: 文件不存在")
            continue
        try:
            meta, body = parse_frontmatter(path)
        except (OSError, UnicodeError, StateError) as exc:
            errors.append(str(exc))
            continue
        metas[name], bodies[name] = meta, body
        require_keys(path, meta, BASE_KEYS, errors)
        if meta.get("schema_version") != SCHEMA_VERSION:
            errors.append(f"{path}: schema_version 应为 {SCHEMA_VERSION}")
        if meta.get("document_type") != doc_type:
            errors.append(f"{path}: document_type 应为 {doc_type}")
        if name == "PROGRESS.md":
            require_keys(path, meta, PROGRESS_KEYS, errors)
        elif name == "ACTIVE.md":
            require_keys(path, meta, ACTIVE_KEYS, errors)
        elif name == "ITEMS.md":
            require_keys(path, meta, ITEMS_KEYS, errors)
        require_headings(path, body, REQUIRED_HEADINGS[name], errors)

    stages = base / "stages"
    if not stages.is_dir():
        errors.append(f"{stages}: 目录不存在")
    if len(metas) != len(CORE_TYPES):
        return errors, metas, []

    progress = metas["PROGRESS.md"]
    active = metas["ACTIVE.md"]
    items_meta = metas["ITEMS.md"]
    expected = {key: progress.get(key) for key in BASE_KEYS - {"schema_version", "document_type"}}
    for name, meta in metas.items():
        for key, value in expected.items():
            if meta.get(key) != value:
                errors.append(f"{base / name}: {key} 与 PROGRESS.md 不一致")
    if progress.get("state_dir") != str(state_root.resolve()):
        errors.append(f"{base / 'PROGRESS.md'}: state_dir 与实际目录不一致")
    if not ID_RE.fullmatch(progress.get("project_id", "")):
        errors.append(f"{base / 'PROGRESS.md'}: project_id 格式错误")
    if not STATE_ID_RE.fullmatch(progress.get("state_id", "")):
        errors.append(f"{base / 'PROGRESS.md'}: state_id 格式错误")
    if not progress.get("project_title", "").strip():
        errors.append(f"{base / 'PROGRESS.md'}: project_title 不能为空")
    if not CP_RE.fullmatch(progress.get("checkpoint", "")):
        errors.append(f"{base / 'PROGRESS.md'}: checkpoint 格式错误")
    if not VERSION_RE.fullmatch(progress.get("formal_version", "")):
        errors.append(f"{base / 'PROGRESS.md'}: formal_version 格式错误")
    if not SC_RE.fullmatch(progress.get("soft_checkpoint", "")):
        errors.append(f"{base / 'PROGRESS.md'}: soft_checkpoint 格式错误")
    question = progress.get("current_question", "")
    if question != "none" and not QUESTION_RE.fullmatch(question):
        errors.append(f"{base / 'PROGRESS.md'}: current_question 格式错误")
    if progress.get("stage_status") not in STAGE_STATUSES:
        errors.append(f"{base / 'PROGRESS.md'}: stage_status 非法")
    if progress.get("project_status") not in PROJECT_STATUSES:
        errors.append(f"{base / 'PROGRESS.md'}: project_status 非法")
    if progress.get("project_status") == "completed" and question != "none":
        errors.append(f"{base / 'PROGRESS.md'}: 完成项目的 current_question 必须为 none")
    if progress.get("project_status") != "completed" and question == "none":
        errors.append(f"{base / 'PROGRESS.md'}: 未完成项目必须保留唯一 current_question")
    if progress.get("project_status") == "completed" and progress.get("stage_status") != "completed":
        errors.append(f"{base / 'PROGRESS.md'}: 完成项目的 stage_status 必须为 completed")
    for key in ("soft_checkpoint", "current_level", "current_stage", "current_question"):
        if active.get(key) != progress.get(key):
            errors.append(f"{base / 'ACTIVE.md'}: {key} 与 PROGRESS.md 不一致")
        if items_meta.get(key) != progress.get(key):
            errors.append(f"{base / 'ITEMS.md'}: {key} 与 PROGRESS.md 不一致")
    depth = active.get("explanation_depth")
    if depth not in {"L1", "L2", "L3"}:
        errors.append(f"{base / 'ACTIVE.md'}: explanation_depth 非法")
    if depth in {"L2", "L3"}:
        require_headings(base / "ACTIVE.md", bodies["ACTIVE.md"], ["## 面向用户的完整说明", "### 实际过程", "### 正常例子", "### 影响、代价和限制"], errors)
    if depth == "L3":
        require_headings(base / "ACTIVE.md", bodies["ACTIVE.md"], ["### 边界例子", "### 异常例子"], errors)

    item_rows = parse_items(base / "ITEMS.md", bodies["ITEMS.md"], errors)
    decision_headings = re.findall(r"^## (D-\d{3,})(?:\s|：|$)", bodies["DECISIONS.md"], flags=re.MULTILINE)
    decision_ids = set(decision_headings)
    duplicate_decisions = sorted({item_id for item_id in decision_headings if decision_headings.count(item_id) > 1})
    if duplicate_decisions:
        errors.append(f"{base / 'DECISIONS.md'}: 决定编号重复 {', '.join(duplicate_decisions)}")
    decision_rows = {row["ID"] for row in item_rows if row["类型"] == "decision"}
    missing_decision_bodies = sorted(decision_rows - decision_ids)
    if missing_decision_bodies:
        errors.append(f"{base / 'ITEMS.md'}: 决定项目缺少 DECISIONS.md 正文 {', '.join(missing_decision_bodies)}")
    unindexed_decisions = sorted(decision_ids - decision_rows)
    if unindexed_decisions:
        errors.append(f"{base / 'DECISIONS.md'}: 决定未登记到 ITEMS.md {', '.join(unindexed_decisions)}")
    for row in item_rows:
        evidence_decisions = set(re.findall(r"D-\d{3,}", row["证据或落点"]))
        missing_decisions = sorted(evidence_decisions - decision_ids)
        if missing_decisions:
            errors.append(f"{base / 'ITEMS.md'}: {row['ID']} 引用了不存在的决定 {', '.join(missing_decisions)}")
        needs_decision = row["状态"] in {"not-applicable", "superseded"} or (row["类型"] == "question" and row["状态"] in {"confirmed", "completed"})
        if needs_decision and not evidence_decisions:
            errors.append(f"{base / 'ITEMS.md'}: {row['ID']} 的终结状态必须引用 DECISIONS.md 中的决定")
    active_questions = [row["ID"] for row in item_rows if row["类型"] == "question" and row["状态"] == "active"]
    if question == "none":
        if active_questions:
            errors.append(f"{base / 'ITEMS.md'}: current_question 为 none 时不能有 active question")
    elif active_questions != [question]:
        errors.append(f"{base / 'ITEMS.md'}: 必须且只能有一个与 current_question 一致的 active question")
    else:
        active_row = next(row for row in item_rows if row["ID"] == question)
        if active_row["阶段"] != progress.get("current_stage"):
            errors.append(f"{base / 'ITEMS.md'}: 当前问题阶段与 current_stage 不一致")
    gates = [row for row in item_rows if row["类型"] == "gate" and row["状态"] not in {"not-applicable", "superseded"}]
    stage_gates = [row for row in gates if row["阶段"] == progress.get("current_stage")]
    blockers = [row for row in item_rows if row["状态"] == "blocked"]
    expected_counts = {
        "stage_gates_done": sum(row["状态"] == "completed" for row in stage_gates),
        "stage_gates_total": len(stage_gates),
        "project_gates_done": sum(row["状态"] == "completed" for row in gates),
        "project_gates_total": len(gates),
        "blocked_count": len(blockers),
    }
    for key, expected_count in expected_counts.items():
        try:
            actual = int(progress[key])
        except (KeyError, ValueError):
            errors.append(f"{base / 'PROGRESS.md'}: {key} 不是整数")
            continue
        if actual != expected_count:
            errors.append(f"{base / 'PROGRESS.md'}: {key}={actual}，应由 ITEMS.md 复算为 {expected_count}")
    require_body_marker(base / "PROGRESS.md", bodies["PROGRESS.md"], "当前确认点", question, errors)
    require_body_marker(base / "PROGRESS.md", bodies["PROGRESS.md"], "当前阶段", f"{progress['stage_gates_done']}/{progress['stage_gates_total']}", errors)
    require_body_marker(base / "PROGRESS.md", bodies["PROGRESS.md"], "全项目", f"{progress['project_gates_done']}/{progress['project_gates_total']}", errors)
    require_body_marker(base / "ACTIVE.md", bodies["ACTIVE.md"], "编号", question, errors)
    if progress.get("project_status") in {"ready-for-build", "building", "awaiting-acceptance", "completed"}:
        if expected_counts["project_gates_done"] != expected_counts["project_gates_total"]:
            errors.append(f"{base / 'PROGRESS.md'}: {progress.get('project_status')} 要求全部有效门槛关闭")
    if blockers and progress.get("project_status") != "blocked":
        errors.append(f"{base / 'PROGRESS.md'}: 存在 blocked 项目时 project_status 必须为 blocked")
    if not blockers and progress.get("project_status") == "blocked":
        errors.append(f"{base / 'PROGRESS.md'}: project_status=blocked 但 ITEMS.md 没有 blocked 项目")

    try:
        _, project_body = parse_frontmatter(base / "PROJECT.md")
    except StateError:
        project_body = ""
    for link in sorted(set(STAGE_LINK_RE.findall(project_body))):
        if not (base / link).is_file():
            errors.append(f"{base / 'PROJECT.md'}: 阶段引用不存在 {link}")
    if stages.is_dir():
        seen_stage_ids: set[str] = set()
        for path in sorted(stages.glob("*.md")):
            try:
                meta, body = parse_frontmatter(path)
            except (OSError, UnicodeError, StateError) as exc:
                errors.append(str(exc))
                continue
            require_keys(path, meta, BASE_KEYS | {"stage_id"}, errors)
            if meta.get("document_type") != "stage":
                errors.append(f"{path}: document_type 应为 stage")
            stage_id = meta.get("stage_id", "")
            if not STAGE_ID_RE.fullmatch(stage_id):
                errors.append(f"{path}: stage_id 格式错误")
            if stage_id in seen_stage_ids:
                errors.append(f"{path}: stage_id 重复 {stage_id}")
            seen_stage_ids.add(stage_id)
            for key, value in expected.items():
                if meta.get(key) != value:
                    errors.append(f"{path}: {key} 与 PROGRESS.md 不一致")
            require_headings(path, body, STAGE_HEADINGS, errors)
    return errors, metas, item_rows


def snapshot_manifest(files: dict[str, str], progress: dict[str, str]) -> dict:
    hashes = hash_files(files)
    return {
        "schema_version": 1,
        "state_id": progress["state_id"],
        "checkpoint": progress["checkpoint"],
        "formal_version": progress["formal_version"],
        "files": hashes,
        "formal_digest": digest_hashes(hash_files(formal_files(files))),
        "created_at": utc_now(),
    }


def current_manifest(root: Path, files: dict[str, str], revision: int, formal_digest: str | None = None, history_start_version: str | None = None) -> dict:
    progress, _ = parse_frontmatter_text(files["PROGRESS.md"], "PROGRESS.md")
    if formal_digest is None:
        snap_path = root / "versions" / progress["formal_version"] / ".manifest.json"
        formal_digest = read_json(snap_path).get("formal_digest", "")
    if history_start_version is None:
        manifest_path = meta_dir(root) / "manifest.json"
        history_start_version = read_json(manifest_path).get("history_start_version", "v0000") if manifest_path.is_file() else "v0000"
    start_number = int(history_start_version[1:])
    current_number = int(progress["formal_version"][1:])
    snapshot_index = {
        f"v{number:04d}": sha256((root / "versions" / f"v{number:04d}" / ".manifest.json").read_text(encoding="utf-8"))
        for number in range(start_number, current_number + 1)
    }
    return {
        "schema_version": 1,
        "state_id": progress["state_id"],
        "state_dir": str(root.resolve()),
        "revision": revision,
        "checkpoint": progress["checkpoint"],
        "formal_version": progress["formal_version"],
        "soft_checkpoint": progress["soft_checkpoint"],
        "history_start_version": history_start_version,
        "snapshot_manifest_hashes": snapshot_index,
        "files": hash_files(files),
        "formal_snapshot_digest": formal_digest,
        "updated_at": utc_now(),
    }


def meta_dir(root: Path) -> Path:
    return root / STATE_META_DIR


@contextlib.contextmanager
def state_lock(root: Path):
    lock_path = meta_dir(root) / "state.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def write_snapshot(root: Path, files: dict[str, str]) -> None:
    try:
        progress, _ = parse_frontmatter_text(files["PROGRESS.md"], "PROGRESS.md")
    except (KeyError, StateError):
        return "保存现场并人工判断"
    destination = root / "versions" / progress["formal_version"]
    manifest = snapshot_manifest(files, progress)
    if destination.exists():
        existing = package_files(destination)
        existing_manifest = read_json(destination / ".manifest.json")
        if hash_files(existing) != manifest["files"] or existing_manifest.get("formal_digest") != manifest["formal_digest"]:
            raise StateError(f"{destination}: 已存在不同内容的版本快照")
        return
    staging = meta_dir(root) / "snapshot-staging" / f"{progress['formal_version']}-{uuid.uuid4().hex[:8]}"
    (staging / "stages").mkdir(parents=True)
    write_package(staging, files)
    atomic_json(staging / ".manifest.json", manifest)
    errors, _, _ = validate_package(staging, root)
    if errors:
        raise StateError("版本快照暂存校验失败:\n" + "\n".join(errors))
    destination.parent.mkdir(parents=True, exist_ok=True)
    os.replace(staging, destination)
    directory_fd = os.open(destination.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def snapshot_bundle(root: Path, version: str) -> tuple[dict[str, str], dict]:
    directory = root / "versions" / version
    return package_files(directory), read_json(directory / ".manifest.json")


def restore_snapshot(root: Path, version: str, files: dict[str, str], manifest: dict) -> None:
    if manifest.get("files") != hash_files(files):
        raise StateError("journal 中的版本快照与快照 manifest 不一致")
    staging = meta_dir(root) / "snapshot-staging" / f"restore-{version}-{uuid.uuid4().hex[:8]}"
    (staging / "stages").mkdir(parents=True)
    write_package(staging, files)
    atomic_json(staging / ".manifest.json", manifest)
    errors, _, _ = validate_package(staging, root)
    if errors:
        raise StateError("待恢复版本快照校验失败:\n" + "\n".join(errors))
    os.replace(staging, root / "versions" / version)


def initial_documents(root: Path, project_id: str, title: str, state_id: str) -> dict[str, str]:
    common = {
        "schema_version": SCHEMA_VERSION,
        "project_id": project_id,
        "project_title": title,
        "state_id": state_id,
        "state_dir": str(root.resolve()),
        "checkpoint": "CP-0000",
        "formal_version": "v0000",
    }
    project = render(
        {**common, "document_type": "project"},
        """# 项目现行方案

## 项目卡片

| 项目项 | 当前内容 | 状态 |
|---|---|---|
| 项目目标 | 待确认 | 待确认 |
| 使用者 | 待确认 | 待确认 |
| 输入 | 待确认 | 待确认 |
| 输出 | 待确认 | 待确认 |
| 范围 | 待确认 | 待确认 |
| 非目标 | 待确认 | 待确认 |
| 约束 | 待确认 | 待确认 |

## 顶层流程

待确认。

## 阶段索引

暂无。""",
    )
    progress_meta = {
        **common,
        "document_type": "progress",
        "soft_checkpoint": "SC-0000",
        "current_level": "project-card",
        "current_stage": "stage-design",
        "stage_status": "waiting-confirmation",
        "project_status": "active",
        "current_question": "Q-0001",
        "stage_gates_done": "0",
        "stage_gates_total": "9",
        "project_gates_done": "0",
        "project_gates_total": "9",
        "blocked_count": "0",
    }
    progress = render(
        progress_meta,
        """# 项目进度

## 当前状态

- 当前结论：状态包已初始化，等待确认项目目标和边界。
- 当前确认点：Q-0001

## 门槛摘要

- 当前阶段：0/9
- 全项目：0/9
- 详细项目见 `ITEMS.md`。

## 下一动作

完整解释并确认项目最终要解决的问题、交付结果和边界。""",
    )
    active = render(
        {
            **common,
            "document_type": "active",
            "soft_checkpoint": "SC-0000",
            "current_level": "project-card",
            "current_stage": "stage-design",
            "current_question": "Q-0001",
            "explanation_depth": "L3",
        },
        """# 当前讨论快照

## 当前确认点

- 编号：Q-0001
- 目的：确认项目目标和边界。
- 本轮不确认：具体阶段步骤、算法和实现方案。

## 面向用户的完整说明

### 实际过程

待结合用户需求补充。

### 正常例子

待结合用户项目补充。

### 边界例子

待结合用户项目补充。

### 异常例子

待结合用户项目补充。

### 影响、代价和限制

未确认目标和边界前，不展开具体流程或创建目标 Skill。

## 待确认

项目最终必须解决什么问题、交付什么结果，以及明确不处理什么。

## 当前确认点流水

- SC-0000：初始化状态包。""",
    )
    decisions = render({**common, "document_type": "decisions"}, "# 决定记录\n\n当前没有已确认决定。")
    items = render(
        {
            **common,
            "document_type": "items",
            "soft_checkpoint": "SC-0000",
            "current_level": "project-card",
            "current_stage": "stage-design",
            "current_question": "Q-0001",
        },
        """# 讨论项总账

## 讨论项

| ID | 类型 | 必需 | 状态 | 摘要 | 阶段 | 依赖 | 责任人 | 证据或落点 |
|---|---|---|---|---|---|---|---|---|
| Q-0001 | question | yes | active | 确认项目目标、交付结果和边界 | stage-design | - | 用户 | ACTIVE.md |
| G-01-01 | gate | yes | pending | 目标、用户、成功标准和非目标明确 | stage-design | Q-0001 | 用户与 AI | 待用户确认 |
| G-02-01 | gate | yes | pending | 正向触发、负向触发和具体示例明确 | stage-design | G-01-01 | 用户与 AI | 待用户确认 |
| G-03-01 | gate | yes | pending | 输入、输出、模板、来源和空值规则明确 | stage-design | G-02-01 | 用户与 AI | 待用户确认 |
| G-04-01 | gate | yes | pending | 工具、环境、资料目录和权限明确 | stage-design | G-03-01 | 用户与 AI | 待用户确认 |
| G-05-01 | gate | yes | pending | 顶层流程、阶段契约、状态和责任明确 | stage-design | G-04-01 | 用户与 AI | 待用户确认 |
| G-06-01 | gate | yes | pending | 外部副作用、安全、并发和停止条件明确 | stage-design | G-05-01 | 用户与 AI | 待用户确认 |
| G-07-01 | gate | yes | pending | 异常恢复、兼容、迁移和性能约束明确 | stage-design | G-06-01 | 用户与 AI | 待用户确认 |
| G-08-01 | gate | yes | pending | 测试、验收、前向验证和维护方式明确 | stage-design | G-07-01 | 用户与 AI | 待用户确认 |
| G-09-01 | gate | yes | pending | Skill 名称、目录、资源结构和元数据明确 | stage-design | G-08-01 | 用户与 AI | 待用户确认 |""",
    )
    return {"PROJECT.md": project, "PROGRESS.md": progress, "ACTIVE.md": active, "DECISIONS.md": decisions, "ITEMS.md": items}


def init_state(root: Path, project_id: str, title: str) -> None:
    if not ID_RE.fullmatch(project_id):
        raise StateError("project_id 只能包含小写字母、数字和连字符")
    if not title.strip():
        raise StateError("title 不能为空")
    if root.exists() and any(root.iterdir()):
        raise StateError(f"{root}: 目录非空，拒绝覆盖")
    root.mkdir(parents=True, exist_ok=True)
    (root / "stages").mkdir()
    (root / "versions").mkdir()
    (root / "recovery").mkdir()
    (meta_dir(root) / "transactions").mkdir(parents=True)
    state_id = f"DPS-{uuid.uuid4().hex[:12]}"
    files = initial_documents(root, project_id, title.strip(), state_id)
    write_package(root, files, progress_last=True)
    write_snapshot(root, files)
    manifest = current_manifest(root, files, 0)
    snapshot_files, snapshot_meta = snapshot_bundle(root, "v0000")
    atomic_json(meta_dir(root) / "manifest.json", manifest)
    atomic_json(meta_dir(root) / "journal.json", {"schema_version": 1, "state_id": state_id, "state_dir": str(root.resolve()), "revision": 0, "transaction_id": "INIT", "manifest_after": manifest, "state_after": files, "snapshot_after": snapshot_files, "snapshot_manifest_after": snapshot_meta, "written_at": utc_now()})
    atomic_json(meta_dir(root) / "active-transaction.json", {"active": False, "last_transaction": "INIT"})
    errors = audit_state(root)
    if errors:
        raise StateError("初始化校验失败:\n" + "\n".join(errors))


def active_transaction(root: Path) -> dict:
    path = meta_dir(root) / "active-transaction.json"
    return read_json(path) if path.is_file() else {"active": False}


def next_transaction_id(root: Path) -> str:
    transactions = meta_dir(root) / "transactions"
    number = 1
    while (transactions / f"TX-{number:04d}").exists():
        number += 1
    return f"TX-{number:04d}"


def begin_transaction(root: Path, kind: str, reason: str) -> Path:
    with state_lock(root):
        errors = audit_state(root)
        if errors:
            raise StateError("当前状态未通过 audit，不能开始事务:\n" + "\n".join(errors))
        active = active_transaction(root)
        if active.get("active"):
            raise StateError(f"已有活动事务 {active.get('transaction_id')}，先完成或恢复")
        manifest = read_json(meta_dir(root) / "manifest.json")
        files = package_files(root)
        progress, _ = parse_frontmatter_text(files["PROGRESS.md"], "PROGRESS.md")
        if progress["project_status"] == "completed" and kind != "reopen":
            raise StateError("项目已完成；如需修改，必须使用 reopen")
        transaction_id = next_transaction_id(root)
        transaction_dir = meta_dir(root) / "transactions" / transaction_id
        before_dir, work_dir = transaction_dir / "before", transaction_dir / "work"
        (before_dir / "stages").mkdir(parents=True)
        (work_dir / "stages").mkdir(parents=True)
        write_package(before_dir, files)
        updates = {"soft_checkpoint": increment(progress["soft_checkpoint"], SC_RE, "SC-")}
        if kind in {"hard", "reopen"}:
            updates.update({"checkpoint": increment(progress["checkpoint"], CP_RE, "CP-"), "formal_version": increment(progress["formal_version"], VERSION_RE, "v")})
        work_files: dict[str, str] = {}
        for name, text in files.items():
            per_file = {key: value for key, value in updates.items() if key != "soft_checkpoint" or name in {"PROGRESS.md", "ACTIVE.md", "ITEMS.md"}}
            work_files[name] = update_text_meta(text, name, per_file)
        write_package(work_dir, work_files)
        transaction = {"schema_version": 1, "transaction_id": transaction_id, "kind": kind, "reason": reason.strip() or "未说明", "status": "preparing", "base_revision": manifest["revision"], "base_checkpoint": progress["checkpoint"], "base_formal_version": progress["formal_version"], "base_soft_checkpoint": progress["soft_checkpoint"], "work_dir": str(work_dir.resolve()), "created_at": utc_now()}
        atomic_json(transaction_dir / "transaction.json", transaction)
        atomic_json(meta_dir(root) / "active-transaction.json", {"active": True, "transaction_id": transaction_id, "kind": kind, "work_dir": str(work_dir.resolve())})
        return work_dir


def validate_transition(root: Path, transaction: dict, current: dict[str, str], work: dict[str, str]) -> None:
    current_progress, _ = parse_frontmatter_text(current["PROGRESS.md"], "current/PROGRESS.md")
    work_progress, _ = parse_frontmatter_text(work["PROGRESS.md"], "work/PROGRESS.md")
    current_status = current_progress["project_status"]
    work_status = work_progress["project_status"]
    expected_sc = increment(current_progress["soft_checkpoint"], SC_RE, "SC-")
    if work_progress["soft_checkpoint"] != expected_sc:
        raise StateError(f"事务 soft_checkpoint 应为 {expected_sc}")
    if set(current) - set(work):
        raise StateError("事务工作区缺少现有文件，不允许通过省略文件删除状态")
    if work_status == "building" and current_status != "building":
        if transaction["kind"] != "hard" or current_status != "ready-for-build":
            raise StateError("只有 ready-for-build 的落地授权硬检查点才能进入 building")
    if work_status == "awaiting-acceptance" and current_status != "awaiting-acceptance":
        if transaction["kind"] != "hard" or current_status != "building":
            raise StateError("只有 building 的内部验证硬检查点才能进入 awaiting-acceptance")
    if work_status == "completed" and current_status != "completed":
        if transaction["kind"] != "hard" or current_status != "awaiting-acceptance":
            raise StateError("只有 awaiting-acceptance 的用户验收硬检查点才能进入 completed")
    if current_status == "completed" and work_status != "completed" and transaction["kind"] != "reopen":
        raise StateError("已完成项目只能通过 reopen 重新打开")
    if current_status == "ready-for-build" and work_status in {"active", "blocked"}:
        if transaction["kind"] != "reopen":
            raise StateError("定稿状态返回设计讨论必须使用 reopen")
    if current_status in {"building", "awaiting-acceptance"} and work_status in {"active", "blocked", "ready-for-build"}:
        if transaction["kind"] != "reopen":
            raise StateError("落地或验收阶段返回设计讨论必须使用 reopen")
    _, _, before_items = validate_package(meta_dir(root) / "transactions" / transaction["transaction_id"] / "before", root)
    _, _, after_items = validate_package(meta_dir(root) / "transactions" / transaction["transaction_id"] / "work", root)
    before_by_id = {row["ID"]: row for row in before_items}
    after_by_id = {row["ID"]: row for row in after_items}
    removed_items = sorted(set(before_by_id) - set(after_by_id))
    if removed_items:
        raise StateError(f"事务不能删除既有讨论项: {', '.join(removed_items)}")
    reopened_gates = [
        item_id
        for item_id, old in before_by_id.items()
        if old["类型"] == "gate" and old["状态"] in GATE_TERMINAL and after_by_id[item_id]["状态"] == "reopened"
    ]
    if transaction["kind"] == "reopen" and not reopened_gates:
        raise StateError("reopen 必须把至少一个已终结门槛改为 reopened")
    if transaction["kind"] != "reopen":
        illegal_reopens = [
            item_id
            for item_id, old in before_by_id.items()
            if old["状态"] in TERMINAL_REQUIRED and after_by_id[item_id]["状态"] == "reopened"
        ]
        if illegal_reopens:
            raise StateError(f"重新打开已终结项目必须使用 reopen: {', '.join(illegal_reopens)}")
    if transaction["kind"] == "soft":
        if set(current) != set(work):
            raise StateError("软检查点不能新增或删除正式阶段文件")
        if formal_files(current) != formal_files(work):
            raise StateError("软检查点不能修改 PROJECT.md、DECISIONS.md 或 stages/")
        for key in ("checkpoint", "formal_version"):
            if work_progress[key] != current_progress[key]:
                raise StateError(f"软检查点不能修改 {key}")
        for row in after_items:
            old = before_by_id.get(row["ID"])
            if row["类型"] == "gate" and row["状态"] in GATE_TERMINAL and (old is None or old["状态"] not in GATE_TERMINAL):
                raise StateError(f"软检查点不能正式关闭门槛 {row['ID']}")
            if row["类型"] == "question" and row["状态"] in {"confirmed", "completed", "not-applicable"} and (old is None or old["状态"] not in TERMINAL_REQUIRED):
                raise StateError(f"软检查点不能确认或完成问题 {row['ID']}")
        return
    if current["DECISIONS.md"] == work["DECISIONS.md"]:
        raise StateError("硬事务必须在 DECISIONS.md 记录本次决定或重开依据")
    _, current_decision_body = parse_frontmatter_text(current["DECISIONS.md"], "current/DECISIONS.md")
    _, work_decision_body = parse_frontmatter_text(work["DECISIONS.md"], "work/DECISIONS.md")
    current_blocks = parse_decision_blocks(current_decision_body)
    work_blocks = parse_decision_blocks(work_decision_body)
    new_decisions = sorted(set(work_blocks) - set(current_blocks))
    if not new_decisions:
        raise StateError("硬事务必须新增可追溯的决定编号")
    for item_id in new_decisions:
        for heading in ("### 决定", "### 证据", "### 影响"):
            if heading not in work_blocks[item_id]:
                raise StateError(f"新决定 {item_id} 缺少 {heading}")
    expected_cp = increment(current_progress["checkpoint"], CP_RE, "CP-")
    expected_version = increment(current_progress["formal_version"], VERSION_RE, "v")
    if work_progress["checkpoint"] != expected_cp or work_progress["formal_version"] != expected_version:
        raise StateError(f"硬检查点必须提交 {expected_cp}/{expected_version}")
    before_question = current_progress["current_question"]
    if before_question != "none":
        after = next((row for row in after_items if row["ID"] == before_question), None)
        if after is None or after["状态"] not in TERMINAL_REQUIRED:
            raise StateError(f"硬检查点必须关闭原确认点 {before_question}")
        referenced = set(re.findall(r"D-\d{3,}", after["证据或落点"]))
        referenced_new = sorted(referenced & set(new_decisions))
        if not referenced_new:
            raise StateError(f"原确认点 {before_question} 必须引用本次新增决定")
        current_active, _ = parse_frontmatter_text(current["ACTIVE.md"], "current/ACTIVE.md")
        depth_headings = {
            "L1": [],
            "L2": ["### 实际过程", "### 正常例子"],
            "L3": ["### 实际过程", "### 正常例子", "### 边界例子", "### 异常例子"],
        }
        for item_id in referenced_new:
            for heading in depth_headings[current_active["explanation_depth"]]:
                if heading not in work_blocks[item_id]:
                    raise StateError(f"新决定 {item_id} 未保留 {current_active['explanation_depth']} 的 {heading}")
    if work_progress["project_status"] != "completed":
        active_questions = [row for row in after_items if row["类型"] == "question" and row["状态"] == "active"]
        if len(active_questions) != 1:
            raise StateError("硬检查点后必须准备唯一的下一确认点")
    if not before_items:
        raise StateError("硬检查点前的 ITEMS.md 无法解析")


def commit_transaction(root: Path, fail_after: str | None = None) -> str:
    with state_lock(root):
        active = active_transaction(root)
        if not active.get("active"):
            raise StateError("没有活动事务")
        transaction_id = active["transaction_id"]
        transaction_dir = meta_dir(root) / "transactions" / transaction_id
        transaction_path = transaction_dir / "transaction.json"
        transaction = read_json(transaction_path)
        manifest = read_json(meta_dir(root) / "manifest.json")
        if manifest["revision"] != transaction["base_revision"]:
            raise StateError("事务基线 revision 已变化，拒绝覆盖较新状态")
        current = package_files(root)
        work_dir = Path(transaction["work_dir"])
        work = package_files(work_dir)
        errors, _, _ = validate_package(work_dir, root)
        if errors:
            raise StateError("事务工作区校验失败:\n" + "\n".join(errors))
        validate_transition(root, transaction, current, work)
        if transaction["kind"] in {"hard", "reopen"}:
            write_snapshot(root, work)
        new_manifest = current_manifest(root, work, int(manifest["revision"]) + 1)
        work_progress, _ = parse_frontmatter_text(work["PROGRESS.md"], "work/PROGRESS.md")
        snapshot_files, snapshot_meta = snapshot_bundle(root, work_progress["formal_version"])
        journal = {"schema_version": 1, "state_id": new_manifest["state_id"], "state_dir": str(root.resolve()), "revision": new_manifest["revision"], "transaction_id": transaction_id, "manifest_after": new_manifest, "state_after": work, "snapshot_after": snapshot_files, "snapshot_manifest_after": snapshot_meta, "written_at": utc_now()}
        atomic_json(meta_dir(root) / "journal.json", journal)
        transaction["status"] = "journaled"
        transaction["journaled_at"] = utc_now()
        atomic_json(transaction_path, transaction)
        if fail_after == "journal":
            raise StateError("测试注入：journal 写入后中断")
        order = sorted(work)
        order.remove("PROGRESS.md")
        order.append("PROGRESS.md")
        for index, relative in enumerate(order, 1):
            atomic_write(root / relative, work[relative])
            if fail_after == f"file:{index}":
                raise StateError(f"测试注入：写入第 {index} 个文件后中断")
        atomic_json(meta_dir(root) / "manifest.json", new_manifest)
        if fail_after == "manifest":
            raise StateError("测试注入：manifest 写入后中断")
        transaction["status"] = "committed"
        transaction["committed_at"] = utc_now()
        atomic_json(transaction_path, transaction)
        atomic_json(meta_dir(root) / "active-transaction.json", {"active": False, "last_transaction": transaction_id})
        errors = audit_state(root)
        if errors:
            raise StateError("提交后 audit 失败:\n" + "\n".join(errors))
        return transaction_id


def next_recovery_id(root: Path) -> str:
    number = 1
    while (root / "recovery" / f"REC-{number:04d}").exists():
        number += 1
    return f"REC-{number:04d}"


def preserve_current(root: Path, event: Path) -> None:
    before = event / "before"
    (before / "stages").mkdir(parents=True)
    write_package(before, package_files(root, tolerate_missing=True))


def recover_state(root: Path) -> str:
    with state_lock(root):
        journal = read_json(meta_dir(root) / "journal.json")
        if journal.get("state_dir") != str(root.resolve()):
            raise StateError("journal 绑定了其他状态目录")
        files = journal.get("state_after")
        manifest = journal.get("manifest_after")
        snapshot_files = journal.get("snapshot_after")
        snapshot_meta = journal.get("snapshot_manifest_after")
        if not isinstance(files, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in files.items()):
            raise StateError("journal.state_after 非法")
        if not isinstance(manifest, dict) or manifest.get("files") != hash_files(files):
            raise StateError("journal 内容与 manifest_after 不一致")
        if not isinstance(snapshot_files, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in snapshot_files.items()):
            raise StateError("journal.snapshot_after 非法")
        if not isinstance(snapshot_meta, dict) or snapshot_meta.get("files") != hash_files(snapshot_files):
            raise StateError("journal 快照内容与 snapshot_manifest_after 不一致")
        recovery_id = next_recovery_id(root)
        event = root / "recovery" / recovery_id
        preserve_current(root, event)
        candidate = event / "candidate"
        (candidate / "stages").mkdir(parents=True)
        write_package(candidate, files)
        errors, _, _ = validate_package(candidate, root)
        if errors:
            raise StateError("journal 候选状态校验失败:\n" + "\n".join(errors))
        current = package_files(root, tolerate_missing=True)
        unexpected = sorted(set(current) - set(files))
        for relative in unexpected:
            source = root / relative
            destination = event / "unexpected" / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(source, destination)
        progress, _ = parse_frontmatter_text(files["PROGRESS.md"], "journal/PROGRESS.md")
        version = progress["formal_version"]
        current_number = int(version[1:])
        moved_future_snapshots: list[str] = []
        versions_dir = root / "versions"
        if versions_dir.is_dir():
            for directory in sorted(path for path in versions_dir.iterdir() if path.is_dir()):
                if VERSION_RE.fullmatch(directory.name) and int(directory.name[1:]) > current_number:
                    destination = event / "future-snapshots" / directory.name
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(directory, destination)
                    moved_future_snapshots.append(directory.name)
        snapshot_directory = root / "versions" / version
        snapshot_matches = False
        if snapshot_directory.is_dir():
            try:
                current_snapshot_files, current_snapshot_meta = snapshot_bundle(root, version)
                snapshot_matches = current_snapshot_files == snapshot_files and current_snapshot_meta == snapshot_meta
            except StateError:
                snapshot_matches = False
        if not snapshot_matches and snapshot_directory.exists():
            snapshot_before = event / "snapshot-before" / version
            snapshot_before.parent.mkdir(parents=True, exist_ok=True)
            os.replace(snapshot_directory, snapshot_before)
        if not snapshot_matches:
            restore_snapshot(root, version, snapshot_files, snapshot_meta)
        write_package(root, files, progress_last=True)
        atomic_json(meta_dir(root) / "manifest.json", manifest)
        try:
            active = active_transaction(root)
        except StateError:
            active = {"active": False}
        if active.get("active"):
            transaction_path = meta_dir(root) / "transactions" / active["transaction_id"] / "transaction.json"
            if transaction_path.is_file():
                transaction = read_json(transaction_path)
                transaction["status"] = "recovered"
                transaction["recovered_at"] = utc_now()
                atomic_json(transaction_path, transaction)
        atomic_json(meta_dir(root) / "active-transaction.json", {"active": False, "last_recovery": recovery_id})
        atomic_json(event / "recovery.json", {"recovery_id": recovery_id, "journal_revision": journal["revision"], "transaction_id": journal.get("transaction_id"), "unexpected_files_moved": unexpected, "future_snapshots_moved": moved_future_snapshots, "recovered_at": utc_now()})
        errors = audit_state(root)
        if errors:
            raise StateError("恢复后 audit 失败:\n" + "\n".join(errors))
        return recovery_id


def repair_journal(root: Path) -> str:
    with state_lock(root):
        files = package_files(root)
        errors, metas, item_rows = validate_package(root, root)
        if errors:
            raise StateError("现行状态结构无效，不能 repair:\n" + "\n".join(errors))
        manifest = read_json(meta_dir(root) / "manifest.json")
        progress = metas["PROGRESS.md"]
        if manifest.get("state_dir") != str(root.resolve()) or manifest.get("state_id") != progress["state_id"]:
            raise StateError("manifest 状态身份不一致，不能 repair")
        if not isinstance(manifest.get("revision"), int):
            raise StateError("manifest revision 非法，不能 repair")
        if manifest.get("files") != hash_files(files):
            raise StateError("manifest 与现行文件哈希不一致，不能 repair")
        active = active_transaction(root)
        if active.get("active"):
            raise StateError("存在活动事务，不能 repair；应先 recover 或继续事务")
        snapshot_errors, snapshot_files, snapshot_meta = audit_snapshots(root, progress, None, manifest.get("history_start_version", "v0000"))
        if snapshot_errors or snapshot_files is None or snapshot_meta is None:
            raise StateError("版本快照无效，不能 repair:\n" + "\n".join(snapshot_errors))
        if hash_files(formal_files(files)) != hash_files(formal_files(snapshot_files)):
            raise StateError("现行正式规则与当前快照不一致，不能 repair")
        snapshot_digest = digest_hashes(hash_files(formal_files(snapshot_files)))
        if manifest.get("formal_snapshot_digest") != snapshot_digest:
            raise StateError("manifest 未绑定当前正式快照，不能 repair")
        if progress["project_status"] == "completed":
            unresolved = [row["ID"] for row in item_rows if row["必需"] == "yes" and not required_item_closed(row)]
            if unresolved:
                raise StateError(f"项目已完成但仍有必需项目未终结: {', '.join(unresolved)}")
        recovery_id = next_recovery_id(root)
        event = root / "recovery" / recovery_id
        preserve_current(root, event)
        atomic_json(event / "manifest-current.json", manifest)
        journal_path = meta_dir(root) / "journal.json"
        old_journal = event / "journal-before"
        if journal_path.exists():
            os.replace(journal_path, old_journal)
        candidate = {
            "schema_version": 1,
            "state_id": progress["state_id"],
            "state_dir": str(root.resolve()),
            "revision": manifest["revision"],
            "transaction_id": f"REPAIR-{recovery_id}",
            "manifest_after": manifest,
            "state_after": files,
            "snapshot_after": snapshot_files,
            "snapshot_manifest_after": snapshot_meta,
            "written_at": utc_now(),
        }
        atomic_json(journal_path, candidate)
        audit_errors = audit_state(root)
        if audit_errors:
            failed = event / "journal-candidate-failed.json"
            os.replace(journal_path, failed)
            if old_journal.exists():
                os.replace(old_journal, journal_path)
            raise StateError("repair 候选未通过 audit:\n" + "\n".join(audit_errors))
        atomic_json(event / "repair.json", {"recovery_id": recovery_id, "revision": manifest["revision"], "repaired_at": utc_now()})
        return recovery_id


def inspect_active_transaction(root: Path, manifest: dict) -> tuple[list[str], dict, str | None]:
    errors: list[str] = []
    try:
        active = active_transaction(root)
    except StateError as exc:
        return [str(exc)], {"active": False}, None
    if not isinstance(active.get("active"), bool):
        return ["active-transaction.json 的 active 必须为布尔值"], active, None
    if not active["active"]:
        return errors, active, None
    transaction_id = active.get("transaction_id")
    if not isinstance(transaction_id, str) or not re.fullmatch(r"TX-\d{4,}", transaction_id):
        return ["活动事务编号非法"], active, None
    transaction_dir = meta_dir(root) / "transactions" / transaction_id
    transaction_path = transaction_dir / "transaction.json"
    work_dir = transaction_dir / "work"
    if not transaction_path.is_file():
        errors.append(f"活动事务缺少 {transaction_path}")
        return errors, active, None
    try:
        transaction = read_json(transaction_path)
    except StateError as exc:
        return [str(exc)], active, None
    if transaction.get("transaction_id") != transaction_id:
        errors.append("活动事务编号与 transaction.json 不一致")
    if transaction.get("schema_version") != 1:
        errors.append("活动事务 schema_version 非法")
    if transaction.get("kind") not in {"soft", "hard", "reopen"} or active.get("kind") != transaction.get("kind"):
        errors.append("活动事务 kind 不一致或非法")
    expected_work = str(work_dir.resolve())
    if active.get("work_dir") != expected_work or transaction.get("work_dir") != expected_work:
        errors.append("活动事务工作目录绑定不一致")
    if not work_dir.is_dir():
        errors.append(f"活动事务工作目录不存在: {work_dir}")
        return errors, active, None
    status = transaction.get("status")
    if status not in {"preparing", "journaled", "committed"}:
        errors.append(f"活动事务状态非法: {status}")
    base_revision = transaction.get("base_revision")
    revision = manifest.get("revision")
    if not isinstance(base_revision, int) or not isinstance(revision, int):
        errors.append("活动事务或 manifest revision 非法")
    elif revision == base_revision + 1:
        errors.append("活动事务已写入新 revision 但尚未收尾，必须 recover")
    elif revision != base_revision:
        errors.append("活动事务基线 revision 与现行 manifest 不一致")
    try:
        work_progress, _ = parse_frontmatter(work_dir / "PROGRESS.md")
        future_version = work_progress.get("formal_version")
    except (OSError, UnicodeError, StateError) as exc:
        errors.append(f"活动事务 PROGRESS.md 无法读取: {exc}")
        future_version = None
    return errors, active, future_version


def audit_snapshots(root: Path, current_progress: dict[str, str], allowed_future: str | None, history_start_version: str) -> tuple[list[str], dict[str, str] | None, dict | None]:
    errors: list[str] = []
    versions_dir = root / "versions"
    if not versions_dir.is_dir():
        return [f"{versions_dir}: 目录不存在"], None, None
    current_version = current_progress["formal_version"]
    current_number = int(current_version[1:])
    if not VERSION_RE.fullmatch(history_start_version) or int(history_start_version[1:]) > current_number:
        return ["manifest.history_start_version 非法"], None, None
    history_start_number = int(history_start_version[1:])
    snapshot_dirs = sorted(path for path in versions_dir.iterdir() if path.is_dir())
    for path in sorted(versions_dir.iterdir()):
        if not path.is_dir():
            errors.append(f"versions/ 存在非目录条目: {path.name}")
    names = {path.name for path in snapshot_dirs}
    for number in range(history_start_number, current_number + 1):
        expected = f"v{number:04d}"
        if expected not in names:
            errors.append(f"历史版本快照缺失: {expected}")
    current_files: dict[str, str] | None = None
    current_manifest: dict | None = None
    for directory in snapshot_dirs:
        version = directory.name
        if not VERSION_RE.fullmatch(version):
            errors.append(f"versions/ 存在非法目录: {version}")
            continue
        number = int(version[1:])
        if number < history_start_number:
            errors.append(f"存在早于当前迁移基线的活动版本快照: {version}")
        if number > current_number and version != allowed_future:
            errors.append(f"存在未绑定活动事务的未来版本快照: {version}")
        try:
            files = package_files(directory)
            manifest = read_json(directory / ".manifest.json")
        except StateError as exc:
            errors.append(str(exc))
            continue
        allowed_entries = set(CORE_TYPES) | {"stages", ".manifest.json"}
        unexpected_entries = sorted(path.name for path in directory.iterdir() if path.name not in allowed_entries)
        if unexpected_entries:
            errors.append(f"版本快照 {version}: 存在未登记条目 {', '.join(unexpected_entries)}")
        stages_dir = directory / "stages"
        if stages_dir.is_dir():
            unexpected_stages = sorted(path.name for path in stages_dir.iterdir() if not path.is_file() or path.suffix != ".md")
            if unexpected_stages:
                errors.append(f"版本快照 {version}: stages/ 存在非法条目 {', '.join(unexpected_stages)}")
        snapshot_errors, metas, _ = validate_package(directory, root)
        errors.extend(f"版本快照 {version}: {item}" for item in snapshot_errors)
        progress = metas.get("PROGRESS.md", {})
        if manifest.get("schema_version") != 1:
            errors.append(f"版本快照 {version}: manifest schema_version 非法")
        if progress.get("formal_version") != version or manifest.get("formal_version") != version:
            errors.append(f"版本快照 {version}: formal_version 与目录名不一致")
        if progress.get("state_id") != current_progress["state_id"] or manifest.get("state_id") != current_progress["state_id"]:
            errors.append(f"版本快照 {version}: state_id 与现行状态不一致")
        if manifest.get("checkpoint") != progress.get("checkpoint"):
            errors.append(f"版本快照 {version}: checkpoint 与快照正文不一致")
        if manifest.get("files") != hash_files(files):
            errors.append(f"版本快照 {version}: 内容被修改")
        formal_digest = digest_hashes(hash_files(formal_files(files)))
        if manifest.get("formal_digest") != formal_digest:
            errors.append(f"版本快照 {version}: formal_digest 非法")
        if version == current_version:
            current_files, current_manifest = files, manifest
    if current_files is None or current_manifest is None:
        errors.append(f"当前版本快照不存在或无法读取: {current_version}")
    return errors, current_files, current_manifest


def audit_state(root: Path) -> list[str]:
    errors, metas, item_rows = validate_package(root, root)
    if errors:
        return errors
    try:
        files = package_files(root)
        manifest = read_json(meta_dir(root) / "manifest.json")
        journal = read_json(meta_dir(root) / "journal.json")
    except StateError as exc:
        return [str(exc)]
    progress = metas["PROGRESS.md"]
    if manifest.get("schema_version") != 1:
        errors.append("manifest schema_version 非法")
    if not isinstance(manifest.get("revision"), int) or manifest.get("revision", -1) < 0:
        errors.append("manifest revision 非法")
    for key in ("checkpoint", "formal_version", "soft_checkpoint"):
        if manifest.get(key) != progress.get(key):
            errors.append(f"manifest 的 {key} 与现行状态不一致")
    if not isinstance(manifest.get("snapshot_manifest_hashes"), dict):
        errors.append("manifest 缺少历史快照 manifest 索引")
    if manifest.get("state_dir") != str(root.resolve()) or manifest.get("state_id") != progress["state_id"]:
        errors.append("manifest 的状态身份不一致")
    if manifest.get("files") != hash_files(files):
        errors.append("现行文件哈希与 manifest 不一致")
    if journal.get("schema_version") != 1:
        errors.append("journal schema_version 非法")
    if not isinstance(journal.get("revision"), int):
        errors.append("journal revision 非法")
    if journal.get("revision") != manifest.get("revision"):
        errors.append("journal 与 manifest revision 不一致，需要 recover 或修复")
    if journal.get("state_dir") != str(root.resolve()) or journal.get("state_id") != progress["state_id"]:
        errors.append("journal 的状态身份不一致")
    if journal.get("manifest_after") != manifest or journal.get("state_after") != files:
        errors.append("journal 保存的最新状态与现行状态不一致")
    transaction_errors, active, active_version = inspect_active_transaction(root, manifest)
    errors.extend(transaction_errors)
    allowed_future = active_version if active.get("active") else None
    snapshot_errors, snapshot_files, snap_manifest = audit_snapshots(root, progress, allowed_future, manifest.get("history_start_version", "v0000"))
    errors.extend(snapshot_errors)
    if snapshot_files is None or snap_manifest is None:
        return errors
    if "snapshot_manifest_hashes" in manifest:
        start_number = int(manifest.get("history_start_version", "v0000")[1:])
        current_number = int(progress["formal_version"][1:])
        try:
            expected_snapshot_index = {
                f"v{number:04d}": sha256((root / "versions" / f"v{number:04d}" / ".manifest.json").read_text(encoding="utf-8"))
                for number in range(start_number, current_number + 1)
            }
        except (OSError, UnicodeError) as exc:
            errors.append(f"历史版本快照 manifest 无法读取: {exc}")
        else:
            if manifest.get("snapshot_manifest_hashes") != expected_snapshot_index:
                errors.append("历史版本快照 manifest 与现行索引不一致")
    if journal.get("snapshot_after") != snapshot_files or journal.get("snapshot_manifest_after") != snap_manifest:
        errors.append("journal 保存的当前版本快照与磁盘不一致")
    snapshot_formal_digest = digest_hashes(hash_files(formal_files(snapshot_files)))
    if manifest.get("formal_snapshot_digest") != snapshot_formal_digest:
        errors.append("manifest 未绑定当前正式快照")
    if hash_files(formal_files(files)) != hash_files(formal_files(snapshot_files)):
        errors.append("现行正式规则与当前版本快照不一致")
    snapshot_progress, _ = parse_frontmatter_text(snapshot_files["PROGRESS.md"], "当前版本快照/PROGRESS.md")
    for key in ("project_id", "state_id", "checkpoint", "formal_version"):
        if snapshot_progress.get(key) != progress.get(key):
            errors.append(f"当前版本快照: {key} 与现行状态不一致")
    if progress["project_status"] == "completed":
        unresolved = [row["ID"] for row in item_rows if row["必需"] == "yes" and not required_item_closed(row)]
        if unresolved:
            errors.append(f"项目已完成但仍有必需项目未终结: {', '.join(unresolved)}")
        if progress["project_gates_done"] != progress["project_gates_total"]:
            errors.append("项目已完成但有效门槛未全部完成")
    return errors


def recovery_hint(root: Path) -> str:
    try:
        active = active_transaction(root)
        if active.get("active"):
            return "运行 recover"
    except StateError:
        pass
    try:
        manifest = read_json(meta_dir(root) / "manifest.json")
    except StateError:
        return "运行 recover" if (meta_dir(root) / "journal.json").is_file() else "保存现场并人工判断"
    try:
        files = package_files(root)
        manifest_matches = manifest.get("files") == hash_files(files)
    except (OSError, UnicodeError, StateError):
        manifest_matches = False
        files = {}
    try:
        journal = read_json(meta_dir(root) / "journal.json")
    except StateError:
        return "运行 repair" if manifest_matches else "保存现场并人工判断"
    journal_revision = journal.get("revision")
    manifest_revision = manifest.get("revision")
    if isinstance(journal_revision, int) and isinstance(manifest_revision, int):
        if journal_revision > manifest_revision:
            return "运行 recover"
        if journal_revision < manifest_revision:
            return "运行 repair" if manifest_matches else "运行 recover"
    if not manifest_matches:
        return "运行 recover"
    if journal.get("manifest_after") != manifest or journal.get("state_after") != files:
        return "运行 repair"
    try:
        progress, _ = parse_frontmatter_text(files["PROGRESS.md"], "PROGRESS.md")
    except (KeyError, StateError):
        return "保存现场并人工判断"
    try:
        snapshot_files, snapshot_meta = snapshot_bundle(root, progress["formal_version"])
    except StateError:
        return "运行 recover"
    if journal.get("snapshot_after") != snapshot_files or journal.get("snapshot_manifest_after") != snapshot_meta:
        return "运行 recover"
    return "保存现场并人工判断"


def resume_state(root: Path) -> tuple[int, str]:
    errors = audit_state(root)
    if errors:
        hint = recovery_hint(root)
        return 1, "状态异常:\n" + "\n".join(f"- {item}" for item in errors) + f"\n下一动作：{hint}"
    active = active_transaction(root)
    progress, _ = parse_frontmatter(root / "PROGRESS.md")
    lines = [f"状态有效：{progress['formal_version']} | {progress['checkpoint']} | {progress['soft_checkpoint']}", f"阶段：{progress['current_stage']} ({progress['stage_status']})", f"项目状态：{progress['project_status']}", f"当前确认点：{progress['current_question']}", f"门槛：{progress['project_gates_done']}/{progress['project_gates_total']}"]
    if active.get("active"):
        lines.extend([f"活动事务：{active['transaction_id']} ({active['kind']})", f"工作目录：{active['work_dir']}", "下一动作：完成工作目录内容后运行 commit；若 journal 已领先则运行 recover。"])
    elif progress["project_status"] == "completed":
        if finish_record_matches(root):
            lines.append("下一动作：项目已通过 finish；如需修改，使用 reopen。")
        else:
            lines.append("下一动作：运行 finish 持久化最终门禁结果，然后使用 T-12。")
    else:
        lines.append("下一动作：依据 ACTIVE.md 与 ITEMS.md 处理唯一确认点。")
    return 0, "\n".join(lines)


def ensure_sections(body: str, headings: list[str]) -> str:
    additions = [f"{heading}\n\n从 schema 1 迁移，需结合原文复核。" for heading in headings if heading not in body]
    return body.rstrip() + ("\n\n" + "\n\n".join(additions) if additions else "")


def legacy_gate_rows(progress_body: str, stage: str) -> list[list[str]]:
    status_map = {"等待确认": "pending", "讨论中": "active", "已完成": "completed", "阻塞": "blocked", "重新打开": "reopened", "不适用": "not-applicable"}
    rows: list[list[str]] = []
    for line in progress_body.splitlines():
        if not line.strip().startswith("| G-"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 5:
            continue
        item_id, row_stage, summary, evidence, status = cells[:5]
        normalized = status_map.get(status, "pending")
        if normalized in GATE_TERMINAL and evidence in INVALID_TERMINAL_EVIDENCE:
            normalized = "reopened"
        rows.append([item_id, "gate", "yes", normalized, summary, row_stage or stage, "-", "待确认", evidence or "需人工复核"])
    return rows


def migrate_state(root: Path) -> None:
    if not root.is_dir():
        raise StateError(f"{root}: 状态包目录不存在")
    progress_meta, progress_body = parse_frontmatter(root / "PROGRESS.md")
    if progress_meta.get("schema_version") == SCHEMA_VERSION:
        raise StateError("状态包已经是 schema 2")
    if progress_meta.get("schema_version") != "1":
        raise StateError("只支持从 schema 1 迁移")
    recovery_id = next_recovery_id(root)
    event = root / "recovery" / recovery_id
    preserve_current(root, event)
    current = package_files(root, tolerate_missing=True)
    state_id = f"DPS-{uuid.uuid4().hex[:12]}"
    new_cp = increment(progress_meta["checkpoint"], CP_RE, "CP-")
    new_version = increment(progress_meta["formal_version"], VERSION_RE, "v")
    new_sc = increment(progress_meta.get("soft_checkpoint", "SC-0000"), SC_RE, "SC-")
    common = {"schema_version": SCHEMA_VERSION, "state_id": state_id, "state_dir": str(root.resolve()), "checkpoint": new_cp, "formal_version": new_version}
    target: dict[str, str] = {}
    for name, text in current.items():
        meta, body = parse_frontmatter_text(text, name)
        updates = dict(common)
        if name in {"PROGRESS.md", "ACTIVE.md"}:
            updates["soft_checkpoint"] = new_sc
        if name == "PROGRESS.md":
            updates["project_status"] = "active"
        if name == "ACTIVE.md":
            updates["explanation_depth"] = meta.get("explanation_depth", "L3")
        body = ensure_sections(body, REQUIRED_HEADINGS.get(name, STAGE_HEADINGS if name.startswith("stages/") else []))
        target[name] = render({**meta, **updates}, body)
    question = progress_meta.get("current_question", "Q-0001")
    if not QUESTION_RE.fullmatch(question):
        question = "Q-0001"
    stage = progress_meta.get("current_stage", "stage-1")
    gate_rows = legacy_gate_rows(progress_body, stage)
    total = int(progress_meta.get("project_gates_total", "0") or 0)
    while len(gate_rows) < total:
        index = len(gate_rows) + 1
        gate_rows.append([f"G-99-{index:02d}", "gate", "yes", "reopened", f"schema 1 未结构化门槛 {index}", stage, "-", "用户与 AI", "需人工核对原 PROGRESS.md"])
    _, decision_body = parse_frontmatter_text(target["DECISIONS.md"], "DECISIONS.md")
    legacy_decisions = sorted(set(re.findall(r"^## (D-\d{3,})(?:\s|：|$)", decision_body, flags=re.MULTILINE)))
    decision_rows = [[item_id, "decision", "yes", "completed", f"迁移决定 {item_id}", stage, "-", "历史迁移", "DECISIONS.md"] for item_id in legacy_decisions]
    rows = [[question, "question", "yes", "active", "恢复 schema 1 当前确认点", stage, "-", "用户", "ACTIVE.md"], *gate_rows, *decision_rows]
    items_body = "# 讨论项总账\n\n## 讨论项\n\n| " + " | ".join(ITEM_HEADERS) + " |\n|" + "|".join("---" for _ in ITEM_HEADERS) + "|\n" + "\n".join("| " + " | ".join(row) + " |" for row in rows)
    base = {"schema_version": SCHEMA_VERSION, "document_type": "items", "project_id": progress_meta["project_id"], "project_title": progress_meta["project_title"], "state_id": state_id, "state_dir": str(root.resolve()), "checkpoint": new_cp, "formal_version": new_version, "soft_checkpoint": new_sc, "current_level": progress_meta.get("current_level", "project-card"), "current_stage": stage, "current_question": question}
    target["ITEMS.md"] = render(base, items_body)
    done = sum(row[3] == "completed" for row in gate_rows)
    blocked = sum(row[3] == "blocked" for row in gate_rows)
    progress_target_meta, progress_target_body = parse_frontmatter_text(target["PROGRESS.md"], "PROGRESS.md")
    progress_target_meta.update({"stage_gates_done": str(sum(row[3] == "completed" and row[5] == stage for row in gate_rows)), "stage_gates_total": str(sum(row[5] == stage and row[3] not in {"not-applicable", "superseded"} for row in gate_rows)), "project_gates_done": str(done), "project_gates_total": str(sum(row[3] not in {"not-applicable", "superseded"} for row in gate_rows)), "blocked_count": str(blocked), "project_status": "blocked" if blocked else "active", "stage_status": "blocked" if blocked else progress_target_meta.get("stage_status", "waiting-confirmation"), "current_question": question})
    target["PROGRESS.md"] = render(progress_target_meta, sync_progress_body(progress_target_body, progress_target_meta))
    active_meta, active_body = parse_frontmatter_text(target["ACTIVE.md"], "ACTIVE.md")
    active_meta["current_question"] = question
    active_body = sync_active_question(active_body, question)
    target["ACTIVE.md"] = render(active_meta, active_body)
    (meta_dir(root) / "transactions").mkdir(parents=True, exist_ok=True)
    legacy_versions: list[str] = []
    versions_dir = root / "versions"
    if versions_dir.is_dir():
        for source in sorted(versions_dir.iterdir()):
            destination = event / "legacy-versions" / source.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(source, destination)
            legacy_versions.append(source.name)
    write_snapshot(root, target)
    write_package(root, target, progress_last=True)
    manifest = current_manifest(root, target, 1, history_start_version=new_version)
    snapshot_files, snapshot_meta = snapshot_bundle(root, new_version)
    atomic_json(meta_dir(root) / "manifest.json", manifest)
    atomic_json(meta_dir(root) / "journal.json", {"schema_version": 1, "state_id": state_id, "state_dir": str(root.resolve()), "revision": 1, "transaction_id": f"MIGRATE-{recovery_id}", "manifest_after": manifest, "state_after": target, "snapshot_after": snapshot_files, "snapshot_manifest_after": snapshot_meta, "written_at": utc_now()})
    atomic_json(meta_dir(root) / "active-transaction.json", {"active": False, "last_transaction": f"MIGRATE-{recovery_id}"})
    atomic_json(event / "migration.json", {"from_schema": "1", "to_schema": SCHEMA_VERSION, "legacy_versions_moved": legacy_versions, "history_start_version": new_version, "migrated_at": utc_now()})
    errors = audit_state(root)
    if errors:
        raise StateError("迁移后 audit 失败:\n" + "\n".join(errors))


def finish_binding(root: Path) -> dict:
    manifest = read_json(meta_dir(root) / "manifest.json")
    progress, _ = parse_frontmatter(root / "PROGRESS.md")
    return {
        "schema_version": 1,
        "state_id": progress["state_id"],
        "state_dir": str(root.resolve()),
        "revision": manifest["revision"],
        "checkpoint": progress["checkpoint"],
        "formal_version": progress["formal_version"],
        "state_digest": digest_hashes(manifest["files"]),
        "formal_snapshot_digest": manifest["formal_snapshot_digest"],
    }


def finish_record_matches(root: Path) -> bool:
    path = meta_dir(root) / "finish.json"
    if not path.is_file():
        return False
    try:
        record = read_json(path)
        binding = finish_binding(root)
    except (OSError, UnicodeError, StateError, KeyError):
        return False
    return all(record.get(key) == value for key, value in binding.items())


def finish_state(root: Path) -> Path:
    with state_lock(root):
        errors = audit_state(root)
        if errors:
            raise StateError("状态未通过 audit:\n" + "\n".join(errors))
        progress, _ = parse_frontmatter(root / "PROGRESS.md")
        if progress["project_status"] != "completed" or progress["current_question"] != "none":
            raise StateError("只有完成最终用户验收并提交 project_status=completed/current_question=none 后才能 finish")
        path = meta_dir(root) / "finish.json"
        if not finish_record_matches(root):
            atomic_json(path, {**finish_binding(root), "finished_at": utc_now()})
        return path


def self_test() -> None:
    base = Path(tempfile.mkdtemp(prefix="design-project-state-"))

    def new_state(name: str) -> Path:
        root = base / name
        init_state(root, f"{name}-project", "示例项目")
        if audit_state(root):
            raise StateError(f"{name}: 初始 audit 失败")
        return root

    def set_item(text: str, item_id: str, status: str, evidence: str) -> str:
        lines = text.splitlines()
        for index, line in enumerate(lines):
            if not line.startswith(f"| {item_id} |"):
                continue
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            cells[3], cells[8] = status, evidence
            lines[index] = "| " + " | ".join(cells) + " |"
            return "\n".join(lines) + "\n"
        raise StateError(f"自测找不到讨论项 {item_id}")

    def set_progress(path: Path, updates: dict[str, str]) -> None:
        meta, body = parse_frontmatter(path)
        meta.update(updates)
        atomic_write(path, render(meta, sync_progress_body(body, meta)))

    def decision_block(item_id: str, summary: str) -> str:
        return f"""
## {item_id}

### 决定

{summary}

### 实际过程

按本次决定继续下一确认点。

### 正常例子

正常情况按决定执行。

### 边界例子

边界情况保留证据后询问。

### 异常例子

异常时停止推进并恢复。

### 证据

自测确认。

### 影响

更新对应门槛和下一动作。
"""

    root = new_state("transaction")
    work = begin_transaction(root, "soft", "测试软检查点")
    active_path = work / "ACTIVE.md"
    active_text = active_path.read_text(encoding="utf-8").replace("- SC-0000：初始化状态包。", "- SC-0000：初始化状态包。\n- SC-0001：保存新的事实。")
    atomic_write(active_path, active_text)
    try:
        commit_transaction(root, "journal")
        raise StateError("故障注入未触发")
    except StateError as exc:
        if "测试注入" not in str(exc):
            raise
    recover_state(root)
    if "保存新的事实" not in (root / "ACTIVE.md").read_text(encoding="utf-8"):
        raise StateError("journal 恢复没有保留软检查点内容")

    root = new_state("partial-file-write")
    work = begin_transaction(root, "soft", "测试部分文件写入中断")
    active = work / "ACTIVE.md"
    atomic_write(active, active.read_text(encoding="utf-8").replace("- SC-0000：初始化状态包。", "- SC-0000：初始化状态包。\n- SC-0001：测试部分文件写入。"))
    try:
        commit_transaction(root, "file:2")
        raise StateError("部分文件故障注入未触发")
    except StateError as exc:
        if "测试注入" not in str(exc):
            raise
    code, output = resume_state(root)
    if code == 0 or "recover" not in output:
        raise StateError("部分文件写入中断后 resume 未指向 recover")
    recover_state(root)
    if audit_state(root):
        raise StateError("部分文件写入中断后恢复失败")

    root = new_state("formal-drift")
    atomic_write(root / "PROJECT.md", (root / "PROJECT.md").read_text(encoding="utf-8") + "\n未经检查点的正式修改。\n")
    if not audit_state(root):
        raise StateError("正式规则漂移未被识别")

    root = new_state("content-loss")
    active = root / "ACTIVE.md"
    atomic_write(active, active.read_text(encoding="utf-8").replace("### 边界例子", "### 被删除的栏目"))
    if not audit_state(root):
        raise StateError("L3 内容缺失未被识别")

    root = new_state("gate-mismatch")
    progress = root / "PROGRESS.md"
    atomic_write(progress, progress.read_text(encoding="utf-8").replace('project_gates_done: "0"', 'project_gates_done: "1"'))
    if not audit_state(root):
        raise StateError("门槛计数漂移未被识别")

    root = new_state("snapshot-mutation")
    snapshot = root / "versions" / "v0000" / "PROJECT.md"
    atomic_write(snapshot, snapshot.read_text(encoding="utf-8") + "\n快照被篡改。\n")
    if not audit_state(root):
        raise StateError("快照篡改未被识别")
    recover_state(root)
    if audit_state(root):
        raise StateError("快照篡改后未能由 journal 恢复")

    root = new_state("second-transaction")
    begin_transaction(root, "soft", "第一个事务")
    try:
        begin_transaction(root, "soft", "第二个事务")
        raise StateError("并发事务未被阻止")
    except StateError as exc:
        if "已有活动事务" not in str(exc):
            raise

    root = new_state("soft-gate-closure")
    work = begin_transaction(root, "soft", "错误地用软检查点关闭门槛")
    items = work / "ITEMS.md"
    items_text = items.read_text(encoding="utf-8") + "| G-10-01 | gate | yes | completed | 软事务新增并关闭门槛 | stage-design | - | AI | PROJECT.md |\n"
    atomic_write(items, items_text)
    progress = work / "PROGRESS.md"
    set_progress(progress, {"stage_gates_done": "1", "stage_gates_total": "10", "project_gates_done": "1", "project_gates_total": "10"})
    try:
        commit_transaction(root)
        raise StateError("软检查点关闭门槛未被阻止")
    except StateError as exc:
        if "软检查点不能正式关闭门槛" not in str(exc):
            raise

    root = new_state("terminal-evidence")
    work = begin_transaction(root, "hard", "测试终结依据")
    items = work / "ITEMS.md"
    atomic_write(items, set_item(items.read_text(encoding="utf-8"), "G-01-01", "not-applicable", "待用户确认"))
    errors, _, _ = validate_package(work, root)
    if not any("没有有效证据或决定依据" in error for error in errors):
        raise StateError("无依据终结讨论项未被识别")

    root = new_state("item-deletion")
    work = begin_transaction(root, "soft", "错误地删除讨论项")
    items = work / "ITEMS.md"
    items_text = "\n".join(line for line in items.read_text(encoding="utf-8").splitlines() if not line.startswith("| G-09-01 |")) + "\n"
    atomic_write(items, items_text)
    set_progress(work / "PROGRESS.md", {"stage_gates_total": "8", "project_gates_total": "8"})
    try:
        commit_transaction(root)
        raise StateError("删除既有讨论项未被阻止")
    except StateError as exc:
        if "不能删除既有讨论项" not in str(exc):
            raise

    root = new_state("direct-completion")
    work = begin_transaction(root, "hard", "错误地直接完成项目")
    decisions = work / "DECISIONS.md"
    atomic_write(decisions, decisions.read_text(encoding="utf-8") + decision_block("D-000", "测试直接完成。"))
    items = work / "ITEMS.md"
    items_text = set_item(items.read_text(encoding="utf-8"), "Q-0001", "confirmed", "D-000")
    for gate_id in range(1, 10):
        items_text = set_item(items_text, f"G-{gate_id:02d}-01", "not-applicable", "D-000")
    items_text += "| D-000 | decision | yes | completed | 测试直接完成决定 | stage-design | Q-0001 | 用户 | DECISIONS.md |\n"
    atomic_write(items, update_text_meta(items_text, "ITEMS.md", {"current_question": "none"}))
    progress = work / "PROGRESS.md"
    set_progress(progress, {"current_question": "none", "project_status": "completed", "stage_status": "completed", "stage_gates_total": "0", "project_gates_total": "0"})
    active = work / "ACTIVE.md"
    atomic_write(active, update_text_meta(active.read_text(encoding="utf-8").replace("Q-0001", "none"), "ACTIVE.md", {"current_question": "none", "explanation_depth": "L1"}))
    try:
        commit_transaction(root)
        raise StateError("项目直接跳到 completed 未被阻止")
    except StateError as exc:
        if "awaiting-acceptance" not in str(exc):
            raise

    root = new_state("manifest-interruption")
    work = begin_transaction(root, "soft", "测试 manifest 写入后中断")
    active = work / "ACTIVE.md"
    atomic_write(active, active.read_text(encoding="utf-8").replace("- SC-0000：初始化状态包。", "- SC-0000：初始化状态包。\n- SC-0001：测试 manifest 中断。"))
    try:
        commit_transaction(root, "manifest")
        raise StateError("manifest 故障注入未触发")
    except StateError as exc:
        if "测试注入" not in str(exc):
            raise
    code, output = resume_state(root)
    if code == 0 or "recover" not in output:
        raise StateError("manifest 中断后 resume 未指向 recover")
    recover_state(root)
    if audit_state(root):
        raise StateError("manifest 中断后恢复失败")

    root = new_state("journal-repair")
    atomic_write(meta_dir(root) / "journal.json", "{broken journal\n")
    code, output = resume_state(root)
    if code == 0 or "repair" not in output:
        raise StateError("journal 损坏后 resume 未指向 repair")
    repair_journal(root)
    if audit_state(root):
        raise StateError("journal repair 后 audit 失败")

    root = new_state("orphan-snapshot")
    work = begin_transaction(root, "hard", "测试未提交未来快照")
    write_snapshot(root, package_files(work))
    recover_state(root)
    if (root / "versions" / "v0001").exists() or audit_state(root):
        raise StateError("恢复没有隔离未提交的未来快照")

    root = base / "migration"
    (root / "stages").mkdir(parents=True)
    (root / "versions" / "v0000").mkdir(parents=True)
    (root / "recovery").mkdir()
    legacy = initial_documents(root, "migration-project", "迁移示例", "DPS-000000000000")
    legacy.pop("ITEMS.md")
    for name, text in list(legacy.items()):
        meta, body = parse_frontmatter_text(text, name)
        meta["schema_version"] = "1"
        if name == "PROGRESS.md":
            meta.update({"project_gates_total": "1", "project_gates_done": "0", "stage_gates_total": "1", "stage_gates_done": "0"})
            body = sync_progress_body(body + "\n| G-01-01 | stage-1 | 迁移阻塞门槛 | legacy-error | 阻塞 |\n", meta)
        legacy[name] = render(meta, body)
    write_package(root, legacy, progress_last=True)
    atomic_write(root / "versions" / "v0000" / "legacy.txt", "legacy snapshot\n")
    migrate_state(root)
    migrated_progress, _ = parse_frontmatter(root / "PROGRESS.md")
    migrated_manifest = read_json(meta_dir(root) / "manifest.json")
    if audit_state(root) or migrated_progress["project_status"] != "blocked" or migrated_progress["blocked_count"] != "1":
        raise StateError("schema 1 阻塞状态迁移失败")
    if migrated_manifest.get("history_start_version") != "v0001" or (root / "versions" / "v0000").exists():
        raise StateError("schema 1 历史版本没有迁入恢复事件")

    root = new_state("hard-commit")
    work = begin_transaction(root, "hard", "确认项目目标并进入下一确认点")
    project = work / "PROJECT.md"
    atomic_write(project, project.read_text(encoding="utf-8").replace("| 项目目标 | 待确认 | 待确认 |", "| 项目目标 | 设计可恢复的新 Skill | 已确认 |"))
    decisions = work / "DECISIONS.md"
    atomic_write(decisions, decisions.read_text(encoding="utf-8") + decision_block("D-001", "确认项目目标。"))
    items = work / "ITEMS.md"
    items_text = items.read_text(encoding="utf-8")
    items_text = set_item(items_text, "Q-0001", "confirmed", "D-001")
    items_text = set_item(items_text, "G-01-01", "completed", "D-001")
    items_text += "| D-001 | decision | yes | completed | 确认项目目标 | stage-design | Q-0001 | 用户 | DECISIONS.md |\n"
    items_text += "| Q-0002 | question | yes | active | 确认顶层流程 | stage-design | G-01-01 | 用户 | ACTIVE.md |\n"
    atomic_write(items, update_text_meta(items_text, "ITEMS.md", {"current_question": "Q-0002"}))
    progress = work / "PROGRESS.md"
    set_progress(progress, {"current_question": "Q-0002", "stage_gates_done": "1", "project_gates_done": "1"})
    active = work / "ACTIVE.md"
    atomic_write(active, update_text_meta(active.read_text(encoding="utf-8").replace("Q-0001", "Q-0002"), "ACTIVE.md", {"current_question": "Q-0002"}))
    commit_transaction(root)
    if audit_state(root) or not (root / "versions" / "v0001" / ".manifest.json").is_file():
        raise StateError("硬检查点未形成有效版本快照")

    work = begin_transaction(root, "hard", "设计定稿并请求落地授权")
    items = work / "ITEMS.md"
    items_text = set_item(items.read_text(encoding="utf-8"), "Q-0002", "confirmed", "D-002")
    for gate_id in range(2, 10):
        items_text = set_item(items_text, f"G-{gate_id:02d}-01", "not-applicable", "D-002")
    items_text += "| D-002 | decision | yes | completed | 设计定稿 | stage-design | Q-0002 | 用户 | DECISIONS.md |\n"
    items_text += "| Q-0003 | question | yes | active | 授权制作目标 Skill | stage-design | G-09-01 | 用户 | ACTIVE.md |\n"
    atomic_write(items, update_text_meta(items_text, "ITEMS.md", {"current_question": "Q-0003"}))
    decisions = work / "DECISIONS.md"
    atomic_write(decisions, decisions.read_text(encoding="utf-8") + decision_block("D-002", "设计定稿并确认其余门槛不适用。"))
    progress = work / "PROGRESS.md"
    set_progress(progress, {"current_question": "Q-0003", "project_status": "ready-for-build", "stage_status": "completed", "stage_gates_total": "1", "project_gates_total": "1"})
    active = work / "ACTIVE.md"
    atomic_write(active, update_text_meta(active.read_text(encoding="utf-8").replace("Q-0002", "Q-0003"), "ACTIVE.md", {"current_question": "Q-0003"}))
    commit_transaction(root)

    work = begin_transaction(root, "soft", "错误地从定稿状态直接返回设计")
    set_progress(work / "PROGRESS.md", {"project_status": "active", "stage_status": "reopened"})
    try:
        commit_transaction(root)
        raise StateError("ready-for-build 直接返回设计未被阻止")
    except StateError as exc:
        if "必须使用 reopen" not in str(exc):
            raise
    recover_state(root)

    work = begin_transaction(root, "hard", "用户授权制作目标 Skill")
    items = work / "ITEMS.md"
    items_text = set_item(items.read_text(encoding="utf-8"), "Q-0003", "confirmed", "D-003")
    items_text += "| D-003 | decision | yes | completed | 用户授权制作目标 Skill | stage-design | Q-0003 | 用户 | DECISIONS.md |\n"
    items_text += "| Q-0004 | question | yes | active | 完成目标 Skill 制作与内部验证 | stage-design | Q-0003 | AI | ACTIVE.md |\n"
    atomic_write(items, update_text_meta(items_text, "ITEMS.md", {"current_question": "Q-0004"}))
    decisions = work / "DECISIONS.md"
    atomic_write(decisions, decisions.read_text(encoding="utf-8") + decision_block("D-003", "用户授权制作目标 Skill。"))
    progress = work / "PROGRESS.md"
    set_progress(progress, {"current_question": "Q-0004", "project_status": "building"})
    active = work / "ACTIVE.md"
    atomic_write(active, update_text_meta(active.read_text(encoding="utf-8").replace("Q-0003", "Q-0004"), "ACTIVE.md", {"current_question": "Q-0004"}))
    commit_transaction(root)

    work = begin_transaction(root, "soft", "错误地把落地阶段直接改为阻塞设计")
    items = work / "ITEMS.md"
    atomic_write(items, items.read_text(encoding="utf-8") + "| B-0001 | blocker | yes | blocked | 构建阶段测试阻塞 | stage-design | Q-0003 | AI | 构建阶段阻塞测试 |\n")
    set_progress(work / "PROGRESS.md", {"project_status": "blocked", "stage_status": "blocked", "blocked_count": "1"})
    try:
        commit_transaction(root)
        raise StateError("building 直接返回 blocked 未被阻止")
    except StateError as exc:
        if "必须使用 reopen" not in str(exc):
            raise
    recover_state(root)

    work = begin_transaction(root, "hard", "内部验证完成并等待用户验收")
    items = work / "ITEMS.md"
    items_text = set_item(items.read_text(encoding="utf-8"), "Q-0004", "completed", "D-004")
    items_text += "| D-004 | decision | yes | completed | 内部验证完成 | stage-design | Q-0004 | AI | DECISIONS.md |\n"
    items_text += "| Q-0005 | question | yes | active | 用户最终验收目标 Skill | stage-design | Q-0004 | 用户 | ACTIVE.md |\n"
    atomic_write(items, update_text_meta(items_text, "ITEMS.md", {"current_question": "Q-0005"}))
    decisions = work / "DECISIONS.md"
    atomic_write(decisions, decisions.read_text(encoding="utf-8") + decision_block("D-004", "目标 Skill 已完成内部验证。"))
    progress = work / "PROGRESS.md"
    set_progress(progress, {"current_question": "Q-0005", "project_status": "awaiting-acceptance"})
    active = work / "ACTIVE.md"
    atomic_write(active, update_text_meta(active.read_text(encoding="utf-8").replace("Q-0004", "Q-0005"), "ACTIVE.md", {"current_question": "Q-0005"}))
    commit_transaction(root)

    work = begin_transaction(root, "hard", "用户最终验收")
    items = work / "ITEMS.md"
    items_text = set_item(items.read_text(encoding="utf-8"), "Q-0005", "confirmed", "D-005")
    items_text += "| D-005 | decision | yes | completed | 用户接受目标 Skill | stage-design | Q-0005 | 用户 | DECISIONS.md |\n"
    atomic_write(items, update_text_meta(items_text, "ITEMS.md", {"current_question": "none"}))
    decisions = work / "DECISIONS.md"
    atomic_write(decisions, decisions.read_text(encoding="utf-8") + decision_block("D-005", "用户接受目标 Skill。"))
    progress = work / "PROGRESS.md"
    set_progress(progress, {"current_question": "none", "project_status": "completed", "stage_status": "completed"})
    active = work / "ACTIVE.md"
    atomic_write(active, update_text_meta(active.read_text(encoding="utf-8").replace("Q-0005", "none"), "ACTIVE.md", {"current_question": "none", "explanation_depth": "L1"}))
    commit_transaction(root)
    finish_state(root)
    code, output = resume_state(root)
    if code != 0 or not finish_record_matches(root) or "已通过 finish" not in output:
        raise StateError("finish 结果没有形成可恢复证据")
    work = begin_transaction(root, "reopen", "错误地不重开门槛")
    items = work / "ITEMS.md"
    items_text = items.read_text(encoding="utf-8") + "| Q-0006 | question | yes | active | 修改已完成项目 | stage-design | Q-0005 | 用户 | ACTIVE.md |\n"
    atomic_write(items, update_text_meta(items_text, "ITEMS.md", {"current_question": "Q-0006"}))
    set_progress(work / "PROGRESS.md", {"current_question": "Q-0006", "project_status": "active", "stage_status": "reopened"})
    active = work / "ACTIVE.md"
    atomic_write(active, update_text_meta(sync_active_question(active.read_text(encoding="utf-8"), "Q-0006"), "ACTIVE.md", {"current_question": "Q-0006", "explanation_depth": "L1"}))
    try:
        commit_transaction(root)
        raise StateError("空 reopen 未被阻止")
    except StateError as exc:
        if "至少一个已终结门槛" not in str(exc):
            raise
    recover_state(root)
    old_manifest_path = root / "versions" / "v0000" / ".manifest.json"
    old_manifest_text = old_manifest_path.read_text(encoding="utf-8")
    old_manifest = json.loads(old_manifest_text)
    old_manifest["created_at"] = "2000-01-01T00:00:00+00:00"
    atomic_json(old_manifest_path, old_manifest)
    if not any("manifest 与现行索引不一致" in error for error in audit_state(root)):
        raise StateError("历史快照 manifest 篡改未被识别")
    atomic_write(old_manifest_path, old_manifest_text)
    if audit_state(root):
        raise StateError("恢复历史快照 manifest 后 audit 失败")
    snapshot = root / "versions" / "v0000" / "PROJECT.md"
    atomic_write(snapshot, snapshot.read_text(encoding="utf-8") + "\n历史快照被篡改。\n")
    if not any("版本快照 v0000" in error for error in audit_state(root)):
        raise StateError("历史快照篡改未被识别")
    print(f"自测现场已保留: {base}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, help="也可放在子命令之后")
    sub = parser.add_subparsers(dest="command", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--state-dir", dest="command_state_dir", type=Path)

    def command(name: str, help_text: str) -> argparse.ArgumentParser:
        return sub.add_parser(name, help=help_text, parents=[common])

    init_parser = command("init", "初始化 schema 2 状态包，不覆盖已有内容")
    init_parser.add_argument("--project-id", required=True)
    init_parser.add_argument("--title", required=True)
    command("resume", "执行恢复门并打印唯一下一动作")
    validate_parser = command("validate", "校验现行 Markdown 状态或指定版本快照")
    validate_parser.add_argument("--snapshot")
    validate_parser.add_argument("--json", action="store_true")
    command("audit", "校验结构、正文、总账、哈希、journal 和正式快照")
    command("show", "输出紧凑状态摘要")
    begin_parser = command("begin", "创建隔离事务工作区")
    begin_parser.add_argument("--kind", choices=("soft", "hard"), required=True)
    begin_parser.add_argument("--reason", required=True)
    reopen_parser = command("reopen", "为修改已确认规则创建硬事务")
    reopen_parser.add_argument("--reason", required=True)
    commit_parser = command("commit", "校验并提交当前事务")
    commit_parser.add_argument("--fail-after", help=argparse.SUPPRESS)
    command("recover", "由最新 journal 恢复现行状态并保存异常现场")
    command("repair", "在 manifest 与现行状态可信时重建缺失或损坏的 journal")
    command("migrate", "把 schema 1 状态迁移到 schema 2，保留旧现场")
    command("finish", "验证最终用户验收和全部完成门禁")
    command("self-test", "运行事务、恢复和反例测试")
    args = parser.parse_args()
    state_dir = getattr(args, "command_state_dir", None) or args.state_dir
    if state_dir is None and args.command != "self-test":
        parser.error("必须提供 --state-dir")
    root = state_dir.resolve() if state_dir else Path.cwd()
    try:
        if args.command == "init":
            init_state(root, args.project_id, args.title)
            print(f"状态包已初始化并通过 audit: {root}")
        elif args.command == "resume":
            code, output = resume_state(root)
            print(output)
            return code
        elif args.command == "validate":
            target = root / "versions" / args.snapshot if args.snapshot else root
            if args.snapshot and not VERSION_RE.fullmatch(args.snapshot):
                errors = [f"{args.snapshot}: 快照版本格式错误"]
            else:
                errors, _, _ = validate_package(target, root)
                manifest_path = target / ".manifest.json"
                if args.snapshot and manifest_path.is_file():
                    snapshot_files = package_files(target)
                    if read_json(manifest_path).get("files") != hash_files(snapshot_files):
                        errors.append("版本快照内容与 .manifest.json 不一致")
            result = {"ok": not errors, "errors": errors}
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            elif errors:
                print("校验失败:\n" + "\n".join(f"- {item}" for item in errors))
            else:
                print("校验通过")
            return 0 if not errors else 1
        elif args.command == "audit":
            errors = audit_state(root)
            if errors:
                print("audit 失败:\n" + "\n".join(f"- {item}" for item in errors))
                return 1
            print("audit 通过")
        elif args.command == "show":
            code, output = resume_state(root)
            print(output)
            return code
        elif args.command == "begin":
            work = begin_transaction(root, args.kind, args.reason)
            print(f"事务工作目录: {work}")
        elif args.command == "reopen":
            work = begin_transaction(root, "reopen", args.reason)
            print(f"重新打开事务工作目录: {work}")
        elif args.command == "commit":
            transaction_id = commit_transaction(root, args.fail_after)
            print(f"事务已提交并通过 audit: {transaction_id}")
        elif args.command == "recover":
            recovery_id = recover_state(root)
            print(f"状态已恢复并通过 audit: {recovery_id}")
        elif args.command == "repair":
            recovery_id = repair_journal(root)
            print(f"journal 已修复并通过 audit: {recovery_id}")
        elif args.command == "migrate":
            migrate_state(root)
            print("schema 1 已迁移到 schema 2 并通过 audit")
        elif args.command == "finish":
            finish_path = finish_state(root)
            print(f"最终完成门禁通过并已持久化: {finish_path}")
        else:
            self_test()
            print("自测通过")
    except (OSError, UnicodeError, StateError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
