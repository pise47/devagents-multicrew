"""工作区上下文装配（SPEC §3 上下文交接）: 快照 → 按预算裁剪。

原则: 阶段间只传工作区里"已存在的产物文件"，不传对话历史；
token 估算用 字符数/1.5 的近似（中文约 1.5 字符/token），只用于预算控制，
与实际计费（API 返回 usage）无关。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

# 不进上下文的目录（环境/缓存/版本控制）
IGNORE_DIRS = {
    ".venv", "venv", "__pycache__", ".pytest_cache", ".git", ".idea",
    "htmlcov", "node_modules", ".mypy_cache", ".ruff_cache", ".tox",
}
IGNORE_SUFFIXES = {".pyc", ".pyo"}


@dataclass(frozen=True)
class FileSnap:
    root: Path
    relative: str  # posix 风格相对路径

    @property
    def path(self) -> Path:
        return self.root / self.relative

    def read(self) -> str:
        try:
            return self.path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            return f"[读取失败: {e}]"


def _est_tokens(text: str) -> int:
    return max(1, math.ceil(len(text) / 1.5))


def snapshot_files(root: Path) -> list[FileSnap]:
    """列出工作区文件（忽略 IGNORE_DIRS / 缓存后缀），按相对路径排序。"""
    snaps: list[FileSnap] = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        try:
            rel = p.relative_to(root).as_posix()
        except ValueError:
            continue
        first = rel.split("/", 1)[0]
        if first in IGNORE_DIRS or any(seg in IGNORE_DIRS for seg in rel.split("/")[:-1]):
            continue
        if p.suffix.lower() in IGNORE_SUFFIXES:
            continue
        snaps.append(FileSnap(root=root, relative=rel))
    return snaps


def assemble_context(
    root: Path,
    budget_tokens: int,
    file_token_limit: int,
) -> tuple[str, dict]:
    """装配上下文文本 + 元信息。

    规则: 按文件排序依次装入，单文件先按 file_token_limit 截断（带标记），
    超出剩余预算的文件跳过并记 truncated(budget)；截断的记 truncated(file_limit)。
    """
    files = snapshot_files(root)
    meta: dict = {
        "total_files": len(files),
        "included": [],
        "truncated": [],
        "est_tokens": 0,
    }
    parts = [f"# 工作区文件（共 {len(files)} 个）"]
    remaining = budget_tokens

    for snap in files:
        content = snap.read()
        if _est_tokens(content) > file_token_limit:
            max_chars = int(file_token_limit * 1.5)
            content = content[:max_chars] + "\n…[截断: 超单文件上限]"
            meta["truncated"].append({"path": snap.relative, "reason": "file_limit"})
        piece = f"\n\n--- {snap.relative} ---\n{content}"
        est = _est_tokens(piece)
        if est > remaining:
            meta["truncated"].append({"path": snap.relative, "reason": "budget"})
            continue
        parts.append(piece)
        remaining -= est
        meta["included"].append(snap.relative)

    text = "\n".join(parts)
    meta["est_tokens"] = _est_tokens(text)
    return text, meta
