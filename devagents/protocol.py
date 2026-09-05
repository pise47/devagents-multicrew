"""角色输出协议: ```path= 信封解析 + 工作区路径白名单（SPEC §3/§8）。

- 所有角色响应统一为信封格式，块外文本忽略
- 路径必须为工作区内相对路径: 拒绝绝对路径 / .. 段 / 盘符 / 反斜杠逃逸
- 解析失败抛 ProtocolError，由 pipeline 触发阶段重试（1 次）
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

_BLOCK_RE = re.compile(r"^```path=(.+?)\s*$")

_PATH_FORBIDDEN = ("/", "\\", ":")  # 绝对 / 盘符直接拒
_SEGMENT_BANNED = {"..", "."}
_WIN_ILLEGAL = set('<>"|?*')  # Windows 文件名字符限制（write_text 会 OSError 的提前拒）


class ProtocolError(RuntimeError):
    """信封解析或路径校验失败。"""


def validate_rel_path(raw: str) -> str:
    """归一化并校验工作区内相对路径；非法抛 ProtocolError。

    允许 `src\\mod.py`（Windows 习惯反斜杠）→ 归一化为 `src/mod.py`。
    """
    path = str(raw).strip().replace("\\", "/")
    if not path:
        raise ProtocolError("空路径")
    if path.startswith(_PATH_FORBIDDEN) or ":" in path:
        raise ProtocolError(f"非法路径（绝对/盘符）: {raw!r}")
    if any(ch in _WIN_ILLEGAL for ch in path) or any(ord(ch) < 32 for ch in path):
        raise ProtocolError(f"路径含非法字符（Windows 文件名限制）: {raw!r}")
    segments = path.split("/")
    # .. 段直接拒绝（不是过滤）——穿越必须显式失败
    if ".." in segments:
        raise ProtocolError(f"路径含 .. 逃逸: {raw!r}")
    segments = [seg for seg in segments if seg not in _SEGMENT_BANNED]  # 仅剥除 "." 等无害段
    # Windows 段尾点/空格限制要在剥除 "." 段之后再查（防误杀 ./a.py 这类前缀）
    if any(seg.endswith((" ", ".")) or seg.startswith(" ") for seg in segments):
        raise ProtocolError(f"路径段首尾空格/点不合法: {raw!r}")
    normalized = PurePosixPath(*segments).as_posix() if segments else ""
    if not normalized or normalized.startswith(_PATH_FORBIDDEN):
        raise ProtocolError(f"非法路径: {raw!r}")
    return normalized


def resolve_safe_path(root: Path, rel: str) -> Path:
    """合规相对路径 → root 内绝对路径；逃逸抛 ProtocolError。"""
    safe = validate_rel_path(rel)
    target = (root / safe).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ProtocolError(f"路径逃逸工作区: {rel!r}")
    return target


def parse_envelopes(text: str) -> list[tuple[str, str]]:
    """解析信封块列表 [(rel_path, content)]。块外文本/无 path 围栏忽略。

    行以 ```path=<p> 开始，到下一个 ``` 结束；未闭合 → ProtocolError。
    内容按行保留（\r\n 容忍），块尾换行剥除。
    """
    blocks: list[tuple[str, str]] = []
    current: tuple[str, list[str]] | None = None
    for raw_line in text.splitlines():
        line = raw_line.rstrip("\r")
        if current is None:
            m = _BLOCK_RE.match(line.strip())
            if m:
                current = (validate_rel_path(m.group(1)), [])
            continue
        path, lines = current
        # 块内任何以 ``` 起始的行都闭合（内容被约定不含三反引号，见 prompts）
        if line.lstrip().startswith("```"):
            content = "\n".join(lines).rstrip("\n")
            blocks.append((path, content))
            current = None
        else:
            lines.append(line)
    if current is not None:
        raise ProtocolError(f"信封未闭合: path={current[0]}")
    return blocks
