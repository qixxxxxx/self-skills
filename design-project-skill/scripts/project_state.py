#!/usr/bin/env python3
"""Initialize and validate durable design-project state packages."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path


CORE_TYPES = {
    "PROJECT.md": "project",
    "PROGRESS.md": "progress",
    "ACTIVE.md": "active",
    "DECISIONS.md": "decisions",
}
BASE_KEYS = {
    "schema_version",
    "document_type",
    "project_id",
    "project_title",
    "checkpoint",
    "formal_version",
}
PROGRESS_KEYS = {
    "soft_checkpoint",
    "current_level",
    "current_stage",
    "stage_status",
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
}
STAGE_STATUSES = {
    "not-started",
    "discussing",
    "waiting-confirmation",
    "confirmed",
    "blocked",
    "reopened",
    "completed",
}
ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
CP_RE = re.compile(r"^CP-\d{4,}$")
SC_RE = re.compile(r"^SC-\d{4,}$")
VERSION_RE = re.compile(r"^v\d{4,}$")
QUESTION_RE = re.compile(r"^Q-\d{4,}$")
STAGE_LINK_RE = re.compile(r"stages/[^)\s]+\.md")


class StateError(Exception):
    pass


def quoted(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def render(meta: dict[str, str], body: str) -> str:
    lines = ["---", *(f"{key}: {quoted(value)}" for key, value in meta.items()), "---", "", body.rstrip(), ""]
    return "\n".join(lines)


def write_doc(path: Path, meta: dict[str, str], body: str) -> None:
    path.write_text(render(meta, body), encoding="utf-8")


def parse_frontmatter(path: Path) -> tuple[dict[str, str], str]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise StateError(f"{path}: 缺少 YAML frontmatter")
    try:
        end = next(i for i, line in enumerate(lines[1:], 1) if line.strip() == "---")
    except StopIteration as exc:
        raise StateError(f"{path}: frontmatter 未闭合") from exc
    meta: dict[str, str] = {}
    for line in lines[1:end]:
        if not line.strip():
            continue
        if ":" not in line:
            raise StateError(f"{path}: 非法元数据行 {line!r}")
        key, value = line.split(":", 1)
        key, value = key.strip(), value.strip()
        if value.startswith('"') and value.endswith('"'):
            try:
                value = json.loads(value)
            except json.JSONDecodeError as exc:
                raise StateError(f"{path}: {key} 不是合法字符串") from exc
        meta[key] = str(value)
    return meta, "\n".join(lines[end + 1 :])


def require_keys(path: Path, meta: dict[str, str], keys: set[str], errors: list[str]) -> None:
    missing = sorted(keys - meta.keys())
    if missing:
        errors.append(f"{path}: 缺少字段 {', '.join(missing)}")


def validate_package(base: Path) -> tuple[list[str], dict[str, dict[str, str]]]:
    errors: list[str] = []
    metas: dict[str, dict[str, str]] = {}
    for name, doc_type in CORE_TYPES.items():
        path = base / name
        if not path.is_file():
            errors.append(f"{path}: 文件不存在")
            continue
        try:
            meta, _ = parse_frontmatter(path)
        except (OSError, UnicodeError, StateError) as exc:
            errors.append(str(exc))
            continue
        metas[name] = meta
        require_keys(path, meta, BASE_KEYS, errors)
        if meta.get("schema_version") != "1":
            errors.append(f"{path}: schema_version 仅支持 1")
        if meta.get("document_type") != doc_type:
            errors.append(f"{path}: document_type 应为 {doc_type}")
        if name == "PROGRESS.md":
            require_keys(path, meta, PROGRESS_KEYS, errors)
        elif name == "ACTIVE.md":
            require_keys(path, meta, ACTIVE_KEYS, errors)

    stages = base / "stages"
    if not stages.is_dir():
        errors.append(f"{stages}: 目录不存在")

    if len(metas) != len(CORE_TYPES):
        return errors, metas

    progress = metas["PROGRESS.md"]
    active = metas["ACTIVE.md"]
    project = metas["PROJECT.md"]
    expected = {
        "project_id": progress.get("project_id"),
        "project_title": progress.get("project_title"),
        "checkpoint": progress.get("checkpoint"),
        "formal_version": progress.get("formal_version"),
    }
    for name, meta in metas.items():
        for key, value in expected.items():
            if meta.get(key) != value:
                errors.append(f"{base / name}: {key} 与 PROGRESS.md 不一致")

    if not ID_RE.fullmatch(progress.get("project_id", "")):
        errors.append(f"{base / 'PROGRESS.md'}: project_id 格式错误")
    if not CP_RE.fullmatch(progress.get("checkpoint", "")):
        errors.append(f"{base / 'PROGRESS.md'}: checkpoint 格式错误")
    if not VERSION_RE.fullmatch(progress.get("formal_version", "")):
        errors.append(f"{base / 'PROGRESS.md'}: formal_version 格式错误")
    if not SC_RE.fullmatch(progress.get("soft_checkpoint", "")):
        errors.append(f"{base / 'PROGRESS.md'}: soft_checkpoint 格式错误")
    if not QUESTION_RE.fullmatch(progress.get("current_question", "")):
        errors.append(f"{base / 'PROGRESS.md'}: current_question 格式错误")
    if progress.get("stage_status") not in STAGE_STATUSES:
        errors.append(f"{base / 'PROGRESS.md'}: stage_status 非法")

    for key in ("soft_checkpoint", "current_level", "current_stage", "current_question"):
        if active.get(key) != progress.get(key):
            errors.append(f"{base / 'ACTIVE.md'}: {key} 与 PROGRESS.md 不一致")

    for done_key, total_key in (
        ("stage_gates_done", "stage_gates_total"),
        ("project_gates_done", "project_gates_total"),
    ):
        try:
            done, total = int(progress[done_key]), int(progress[total_key])
            if done < 0 or total < 0 or done > total:
                raise ValueError
        except (KeyError, ValueError):
            errors.append(f"{base / 'PROGRESS.md'}: {done_key}/{total_key} 计数非法")
    try:
        if int(progress["blocked_count"]) < 0:
            raise ValueError
    except (KeyError, ValueError):
        errors.append(f"{base / 'PROGRESS.md'}: blocked_count 非法")

    try:
        _, project_body = parse_frontmatter(base / "PROJECT.md")
    except StateError:
        project_body = ""
    for link in sorted(set(STAGE_LINK_RE.findall(project_body))):
        if not (base / link).is_file():
            errors.append(f"{base / 'PROJECT.md'}: 阶段引用不存在 {link}")

    if stages.is_dir():
        for path in sorted(stages.glob("*.md")):
            try:
                meta, _ = parse_frontmatter(path)
            except (OSError, UnicodeError, StateError) as exc:
                errors.append(str(exc))
                continue
            require_keys(path, meta, BASE_KEYS | {"stage_id"}, errors)
            if meta.get("document_type") != "stage":
                errors.append(f"{path}: document_type 应为 stage")
            for key, value in expected.items():
                if meta.get(key) != value:
                    errors.append(f"{path}: {key} 与 PROGRESS.md 不一致")

    return errors, metas


def validate_state(root: Path, snapshot: str | None) -> list[str]:
    if not root.is_dir():
        return [f"{root}: 状态包目录不存在"]
    if snapshot:
        if not VERSION_RE.fullmatch(snapshot):
            return [f"{snapshot}: 快照版本格式错误"]
        base = root / "versions" / snapshot
        errors, metas = validate_package(base)
        if metas and metas.get("PROGRESS.md", {}).get("formal_version") != snapshot:
            errors.append(f"{base}: 快照目录名与 formal_version 不一致")
        return errors

    for directory in ("stages", "versions", "recovery"):
        if not (root / directory).is_dir():
            return [f"{root / directory}: 目录不存在"]
    errors, metas = validate_package(root)
    progress = metas.get("PROGRESS.md", {})
    version = progress.get("formal_version")
    if version and VERSION_RE.fullmatch(version):
        snapshot_errors, snapshot_metas = validate_package(root / "versions" / version)
        errors.extend(f"当前版本快照: {item}" for item in snapshot_errors)
        snapshot_progress = snapshot_metas.get("PROGRESS.md", {})
        for key in ("project_id", "checkpoint", "formal_version"):
            if snapshot_progress and snapshot_progress.get(key) != progress.get(key):
                errors.append(f"当前版本快照: {key} 与现行 PROGRESS.md 不一致")
    return errors


def initial_documents(project_id: str, title: str) -> dict[str, tuple[dict[str, str], str]]:
    common = {
        "schema_version": "1",
        "project_id": project_id,
        "project_title": title,
        "checkpoint": "CP-0000",
        "formal_version": "v0000",
    }
    project = (
        {"schema_version": "1", "document_type": "project", **{k: v for k, v in common.items() if k != "schema_version"}},
        "# 项目现行方案\n\n## 项目卡片\n\n| 项目项 | 当前内容 | 状态 |\n|---|---|---|\n| 项目目标 | 待确认 | 待确认 |\n| 使用者 | 待确认 | 待确认 |\n| 输入 | 待确认 | 待确认 |\n| 输出 | 待确认 | 待确认 |\n| 范围 | 待确认 | 待确认 |\n| 非目标 | 待确认 | 待确认 |\n| 约束 | 待确认 | 待确认 |\n\n## 顶层流程\n\n待确认。\n\n## 阶段索引\n\n暂无。",
    )
    progress_meta = {
        **common,
        "document_type": "progress",
        "soft_checkpoint": "SC-0000",
        "current_level": "project-card",
        "current_stage": "stage-1",
        "stage_status": "waiting-confirmation",
        "current_question": "Q-0001",
        "stage_gates_done": "0",
        "stage_gates_total": "1",
        "project_gates_done": "0",
        "project_gates_total": "1",
        "blocked_count": "0",
    }
    progress = (
        progress_meta,
        "# 项目进度\n\n- 当前结论：状态包已初始化，等待确认项目目标和边界。\n- 当前确认点：Q-0001\n- 下一步：完成项目卡片。\n\n## 门槛\n\n| 编号 | 阶段 | 完成条件 | 证据 | 状态 |\n|---|---|---|---|---|\n| G-01-01 | stage-1 | 项目目标和边界得到确认 | 待补充 | 等待确认 |",
    )
    active = (
        {
            **common,
            "document_type": "active",
            "soft_checkpoint": "SC-0000",
            "current_level": "project-card",
            "current_stage": "stage-1",
            "current_question": "Q-0001",
        },
        "# 当前讨论快照\n\n## 当前确认点\n\n- 编号：Q-0001\n- 目的：确认项目目标和边界。\n- 解释深度：L3；目标和范围会影响后续全部阶段。\n- 本轮确认：项目最终必须解决的问题和交付结果。\n- 本轮不确认：具体阶段步骤、算法和实现方案。\n- 用户只需回答：项目最终必须解决什么问题并交付什么结果？\n\n## 已知事实\n\n暂无。\n\n## 面向用户的完整说明\n\n### 实际过程\n\n待补充。\n\n### 正常例子\n\n待补充。\n\n### 边界例子\n\n待补充。\n\n### 异常例子\n\n待补充。\n\n### 影响、代价和限制\n\n待补充。\n\n### 算法或数字规则\n\n当前不适用；后续涉及时记录输入、单位、步骤、示例计算、结果含义、边界、限制和公式。\n\n## AI 建议\n\n暂无。\n\n## 待确认\n\n项目目标、范围和非目标。\n\n## 当前确认点流水\n\n- SC-0000：初始化状态包。",
    )
    decisions = (
        {**common, "document_type": "decisions"},
        "# 决定记录\n\n当前没有已确认决定。",
    )
    return {
        "PROJECT.md": project,
        "PROGRESS.md": progress,
        "ACTIVE.md": active,
        "DECISIONS.md": decisions,
    }


def init_state(root: Path, project_id: str, title: str) -> None:
    if not ID_RE.fullmatch(project_id):
        raise StateError("project_id 只能包含小写字母、数字和连字符")
    if not title.strip():
        raise StateError("title 不能为空")
    if root.exists() and any(root.iterdir()):
        raise StateError(f"{root}: 目录非空，拒绝覆盖")
    root.mkdir(parents=True, exist_ok=True)
    (root / "stages").mkdir()
    (root / "versions" / "v0000" / "stages").mkdir(parents=True)
    (root / "recovery").mkdir()
    documents = initial_documents(project_id, title.strip())
    for name, (meta, body) in documents.items():
        write_doc(root / name, meta, body)
        shutil.copy2(root / name, root / "versions" / "v0000" / name)
    errors = validate_state(root, None)
    if errors:
        raise StateError("初始化校验失败:\n" + "\n".join(errors))


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="design-project-state-") as temp:
        root = Path(temp) / "state"
        init_state(root, "sample-project", "示例项目")
        if validate_state(root, None):
            raise StateError("有效状态包校验失败")
        active = root / "ACTIVE.md"
        text = active.read_text(encoding="utf-8")
        required_sections = (
            "解释深度：L3",
            "## 面向用户的完整说明",
            "### 实际过程",
            "### 正常例子",
            "### 边界例子",
            "### 异常例子",
            "### 影响、代价和限制",
            "### 算法或数字规则",
        )
        if any(section not in text for section in required_sections):
            raise StateError("初始化 ACTIVE.md 缺少人类可读说明栏目")
        text = text.replace('checkpoint: "CP-0000"', 'checkpoint: "CP-9999"', 1)
        active.write_text(text, encoding="utf-8")
        if not validate_state(root, None):
            raise StateError("损坏状态包未被识别")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    init_parser = sub.add_parser("init", help="初始化新状态包，不覆盖已有内容")
    init_parser.add_argument("--state-dir", required=True, type=Path)
    init_parser.add_argument("--project-id", required=True)
    init_parser.add_argument("--title", required=True)

    validate_parser = sub.add_parser("validate", help="校验现行状态或指定快照")
    validate_parser.add_argument("--state-dir", required=True, type=Path)
    validate_parser.add_argument("--snapshot")
    validate_parser.add_argument("--json", action="store_true")

    sub.add_parser("self-test", help="运行内置正反例测试")
    args = parser.parse_args()

    try:
        if args.command == "init":
            init_state(args.state_dir.resolve(), args.project_id, args.title)
            print(f"状态包已初始化并通过校验: {args.state_dir.resolve()}")
        elif args.command == "validate":
            errors = validate_state(args.state_dir.resolve(), args.snapshot)
            result = {"ok": not errors, "errors": errors}
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            elif errors:
                print("校验失败:")
                print("\n".join(f"- {item}" for item in errors))
            else:
                target = f"快照 {args.snapshot}" if args.snapshot else "现行状态"
                print(f"校验通过: {target}")
            return 0 if not errors else 1
        else:
            self_test()
            print("自测通过")
    except (OSError, UnicodeError, StateError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
