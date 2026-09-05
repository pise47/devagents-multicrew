"""context 契约: 目录快照/忽略集/单文件截断/总预算/截断报告。"""

from __future__ import annotations

import pytest

from devagents.context import snapshot_files, assemble_context


def test_snapshot_lists_only_ignored_free_files(workspace):
    root = workspace(
        {
            "SPEC.md": "# S",
            "todo.py": "x = 1",
            "src/util.py": "y = 2",
            ".venv/Lib/site-packages/huge.py": "z",
            "__pycache__/c.pyc": "bin",
            ".pytest_cache/README.md": "meta",
            "sub/.git/config": "git",
        }
    )
    files = snapshot_files(root)
    rels = sorted(f.relative for f in files)
    assert rels == ["SPEC.md", "src/util.py", "todo.py"]


def test_assemble_respects_total_budget(workspace):
    """总预算: 超出的文件被裁剪且进 truncated 报告。预算按估算 token(≈字符数/1.5)计。"""
    root = workspace({"big1.py": "a" * 9000, "big2.py": "b" * 9000, "small.py": "c" * 10})
    text, meta = assemble_context(root, budget_tokens=3000, file_token_limit=100000)
    assert meta["truncated"]  # 必有文件被裁
    # 头文件 + 尽量多的小文件进入后必须不超预算（单文件超限除外）
    assert meta["est_tokens"] <= 3000 + 20  # 允许尾差


def test_single_file_over_file_limit_truncated(workspace):
    """单文件超 file_token_limit → 截断并带标记，不整体丢弃。"""
    root = workspace({"huge.py": "x" * 40000})
    text, meta = assemble_context(root, budget_tokens=100000, file_token_limit=1000)
    assert "huge.py" in text
    assert "…" in text or "[截断]" in text
    assert "huge.py" in [t["path"] for t in meta["truncated"]]
    assert meta["est_tokens"] <= 100000


def test_empty_workspace_ok(workspace):
    root = workspace({})
    text, meta = assemble_context(root, budget_tokens=10000, file_token_limit=1000)
    assert text != ""
    assert meta["total_files"] == 0
    assert meta["est_tokens"] < 100


def test_assemble_includes_tree_header_and_paths(workspace):
    root = workspace({"SPEC.md": "# 规格", "a.py": "pass"})
    text, _ = assemble_context(root, budget_tokens=10000, file_token_limit=1000)
    assert "SPEC.md" in text and "a.py" in text
    assert "规格" in text
