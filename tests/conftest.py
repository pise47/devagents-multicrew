"""共享测试基建: 假 LLM（不触网）+ workspace 工厂 + 直构 Config。

FakeLLM 以 model 为键分派响应 → 测试里给各阶段配不同模型名，
即天然按阶段编排脚本（见 make_config 的 distinct_roles）。
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from devagents.config import Config, LlmCfg, PipelineCfg
from devagents.llm import ChatResult, NetworkError, Usage


def make_config(
    tmp_path: Path,
    roles: dict[str, str] | None = None,
    fix_rounds_max: int = 2,
    prices: dict | None = None,
) -> Config:
    """直构 Config（不经 toml），unit 测试默认给五阶段分派不同模型名。"""
    distinct = {
        "spec": "m-spec",
        "arch": "m-arch",
        "code": "m-code",
        "test": "m-test",
        "review": "m-review",
    }
    return Config(
        llm=LlmCfg(
            base_url="http://fake",
            key_env="FAKE_KEY",
            timeout_s=60,
            api_key="sk-fake",
        ),
        roles={**distinct, **(roles or {})},
        pipeline=PipelineCfg(
            context_budget_tokens=60000,
            file_token_limit=12000,
            fix_rounds_max=fix_rounds_max,
            gate_retry=1,
            transport_retry=1,
            runner_timeout_s=60,
        ),
        prices=prices or {
            "m-spec": {"input": 1.0, "output": 2.0},
            "m-arch": {"input": 1.0, "output": 2.0},
            "m-code": {"input": 0.2, "output": 0.4},
        },
        runs_dir=tmp_path / "runs",
    )


class FakeLLM:
    """按 model 弹脚本响应的假 LLM，接口对齐 OpenAIClient（usage/total_cost/retries）。

    响应耗尽或缺失 → 抛 RuntimeError 模拟基础设施失败（等价真实 API 报错路径）。
    """

    def __init__(
        self,
        script: dict[str, list[ChatResult | Exception]] | None = None,
        prices: dict | None = None,
    ):
        self.script: dict[str, list[ChatResult | Exception]] = {**dict(script or {})}
        self.prices = prices or {}
        self.calls: list[dict] = []  # {"model", "messages", "result"}
        self.usage = Usage()
        self.retries: dict[str, int] = {"transport": 0}
        self._acc: list[tuple[str, int, int]] = []

    def chat(self, messages: list[dict], model: str, **kwargs) -> ChatResult:
        queue = self.script.get(model, [])
        if not queue:
            raise NetworkError(f"[FakeLLM] model={model} 无预设响应（模拟 API 失败）")
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        self.calls.append({"model": model, "messages": messages, "result": item})
        self.usage.prompt_tokens += item.prompt_tokens
        self.usage.completion_tokens += item.completion_tokens
        self.usage.calls += 1
        self._acc.append((model, item.prompt_tokens, item.completion_tokens))
        return item

    def total_cost(self) -> float | None:
        total = 0.0
        for model, pt, ct in self._acc:
            price = self.prices.get(model)
            if not price:
                return None
            total += pt / 1e6 * float(price.get("input", 0.0))
            total += ct / 1e6 * float(price.get("output", 0.0))
        return round(total, 6)


@pytest.fixture
def workspace(tmp_path):
    """workspace 工厂: 每次调用建独立新目录，避免同测试多次调用互相覆盖。"""
    counter = {"n": 0}

    def _make(files: dict[str, str]) -> Path:
        counter["n"] += 1
        root = tmp_path / f"ws{counter['n']}"
        for rel, content in files.items():
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(textwrap.dedent(content).lstrip("\n"), encoding="utf-8")
        return root

    return _make


@pytest.fixture
def fake_llm():
    return FakeLLM()
