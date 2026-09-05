"""角色定义与消息组装（SPEC §3）: prompts/ 模板 + 阶段 ↔ 模型映射。

roles 不依赖 context（也不依赖 protocol）——pipeline 负责编排:
context 产出文档摘录/代码树文本 → roles 组装成 messages → llm.chat。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

# 五阶段 + 修复模式（修复 = code 角色的独立模板，模型同 code）
STAGES = ("spec", "arch", "code", "test", "review")
FIX_STAGE = "code_fix"


def available_stages() -> tuple[str, ...]:
    return STAGES + (FIX_STAGE,)


@lru_cache(maxsize=None)
def load_prompt(stage: str) -> str:
    """读取包内 prompt 模板（devagents/prompts/<stage>.md），直接编辑即生效。"""
    if stage not in available_stages():
        raise KeyError(f"未知阶段: {stage}")
    path = PROMPTS_DIR / f"{stage}.md"
    return path.read_text(encoding="utf-8")


def assemble_messages(stage: str, user_text: str) -> list[dict]:
    """组装 [system, user] 消息。user_text 由 pipeline 用 context 产物拼好。"""
    return [
        {"role": "system", "content": load_prompt(stage)},
        {"role": "user", "content": user_text},
    ]


def model_for(config, stage: str) -> str:
    """阶段 → 模型名（config.roles）；修复模式复用 code 角色模型。"""
    key = "code" if stage == FIX_STAGE else stage
    try:
        return config.roles[key]
    except KeyError as e:  # pragma: no cover - 配置缺角色的兜底
        raise KeyError(f"config.roles 缺少角色 {key!r}") from e
