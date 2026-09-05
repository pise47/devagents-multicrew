"""信封解析契约: 多块解析/坏输入/路径穿越/路径归一化。"""

from __future__ import annotations

import pytest

import tests.samples as S
from devagents.protocol import (
    ProtocolError,
    parse_envelopes,
    validate_rel_path,
)


def test_parse_single_block():
    out = parse_envelopes(S.env("a.py", "x = 1"))
    assert out == [("a.py", "x = 1")]


def test_parse_multiple_blocks_ignores_surrounding_prose():
    text = "说明文字\n" + S.env("a.py", "x=1") + "中间说明\n" + S.env("b.py", "y=2")
    assert parse_envelopes(text) == [("a.py", "x=1"), ("b.py", "y=2")]


def test_parse_empty_text():
    assert parse_envelopes("") == []
    assert parse_envelopes(" 没有信封的纯文本 ") == []


def test_unclosed_fence_raises():
    with pytest.raises(ProtocolError):
        parse_envelopes(S.DAMAGED_UNCLOSED)


def test_block_without_path_ignored():
    """无 path= 的普通围栏视为正文，不产出文件（防误吞文档里的代码示例）。"""
    assert parse_envelopes(S.DAMAGED_NO_PATH) == []


def test_content_with_crlf_stripped():
    out = parse_envelopes("```path=a.py\r\nx = 1\r\n```\r\n")
    assert out == [("a.py", "x = 1")]


def test_backslash_normalized_to_posix():
    assert validate_rel_path("src\\mod.py") == "src/mod.py"


def test_leading_dot_slash_stripped():
    assert validate_rel_path("./a.py") == "a.py"


@pytest.mark.parametrize("bad", S.TRAVERSAL_CASES)
def test_traversal_rejected(bad):
    with pytest.raises(ProtocolError):
        validate_rel_path(bad)


def test_traversal_after_normalization_rejected():
    """反斜杠归一化后仍含 .. 的必须拒绝。"""
    with pytest.raises(ProtocolError):
        validate_rel_path("a\\..\\..\\evil.py")


def test_nested_safe_paths_allowed():
    assert validate_rel_path("src/pkg/mod.py") == "src/pkg/mod.py"
    assert validate_rel_path("assets/css/app.css") == "assets/css/app.css"


def test_parse_rejects_traversal_paths_in_blocks():
    with pytest.raises(ProtocolError):
        parse_envelopes(S.env("../evil.py", "x"))
    with pytest.raises(ProtocolError):
        parse_envelopes(S.env("C:\\evil.py", "x"))


def test_resolve_within_root(tmp_path):
    """合规路径能解析到 root 内; 逃逸路径解析失败。"""
    from pathlib import Path

    root = tmp_path / "ws"
    root.mkdir()
    from devagents.protocol import resolve_safe_path

    assert resolve_safe_path(root, "a/b.py") == root / "a" / "b.py"
    with pytest.raises(ProtocolError):
        resolve_safe_path(root, "../x.py")
