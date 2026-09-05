"""配置加载: devagents.toml（包根旁固定位置，env DEVAGENTS_CONFIG 可覆盖）。

规则（SPEC §5/§8）:
- 缺 toml → 自动从 devagents.toml.example 复制，然后 ConfigError 提示补配
- key 只走环境变量（key_env 指定变量名），缺失 → 快速失败，提醒 Token Plan 红线
- 未配置的段合并默认值；未知段容忍忽略
"""

from __future__ import annotations

import os
import shutil
import tomllib
from dataclasses import dataclass
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PACKAGE_ROOT / "devagents.toml"
EXAMPLE_CONFIG_PATH = PACKAGE_ROOT / "devagents.toml.example"

DEFAULTS: dict = {
    "llm": {
        "protocol": "openai",  # openai=按量兼容端 | anthropic=Token Plan 套餐端
        "base_url": "https://api.xiaomimimo.com/v1",
        "key_env": "MIMO_API_KEY",
        "timeout_s": 180,
        "max_output_tokens": 16384,  # 仅 anthropic 协议用（必填 max_tokens）
    },
    "roles": {
        "spec": "mimo-v2.5-pro",
        "arch": "mimo-v2.5-pro",
        "code": "mimo-v2.5",
        "test": "mimo-v2.5",
        "review": "mimo-v2.5-pro",
    },
    "pipeline": {
        "context_budget_tokens": 60000,
        "file_token_limit": 12000,
        "fix_rounds_max": 2,
        "gate_retry": 1,
        "transport_retry": 1,
        "runner_timeout_s": 180,
    },
    "prices": {},  # 单价表 {model: {input: 元/M, output: 元/M}}; 空 = 账单只报 token
    "storage": {"runs_dir": "runs"},
}

KNOWN_SECTIONS = {"llm", "roles", "pipeline", "prices", "storage"}


class ConfigError(RuntimeError):
    """配置层错误（含人类可读指引）。"""


@dataclass(frozen=True)
class LlmCfg:
    base_url: str
    key_env: str
    timeout_s: int
    api_key: str  # 由 key_env 解析; 空 = 未配置
    protocol: str = "openai"
    max_output_tokens: int = 16384


@dataclass(frozen=True)
class PipelineCfg:
    context_budget_tokens: int
    file_token_limit: int
    fix_rounds_max: int
    gate_retry: int
    transport_retry: int
    runner_timeout_s: int


@dataclass(frozen=True)
class Config:
    llm: LlmCfg
    roles: dict[str, str]
    pipeline: PipelineCfg
    prices: dict
    runs_dir: Path

    def price_of(self, model: str) -> tuple[float, float] | None:
        """(input, output) 元/M tokens; 未配置返回 None（账单只报 token）。"""
        entry = self.prices.get(model)
        if not entry:
            return None
        return float(entry.get("input", 0.0)), float(entry.get("output", 0.0))


def config_path() -> Path:
    """配置文件路径: env DEVAGENTS_CONFIG 优先，否则包根旁固定位置。"""
    override = os.environ.get("DEVAGENTS_CONFIG")
    if override:
        return Path(override).expanduser().resolve()
    return DEFAULT_CONFIG_PATH


def _merge_section(raw: dict | None, defaults: dict) -> dict:
    """浅合并: 用户段内缺的键取默认。"""
    out = dict(defaults)
    if raw:
        for k, v in raw.items():
            if v is not None:
                out[k] = v
    return out


def _ensure_example_linked(target: Path) -> None:
    """首跑: 从 example 复制一份到目标位置，便于用户编辑。"""
    if not EXAMPLE_CONFIG_PATH.exists():
        raise ConfigError(
            f"找不到示例配置 {EXAMPLE_CONFIG_PATH}，请手动创建 {target}"
        )
    shutil.copyfile(EXAMPLE_CONFIG_PATH, target)


def load_config() -> Config:
    """加载配置。任何配置级问题 → ConfigError（含指引），供 cli 快速失败。"""
    path = config_path()
    if not path.exists():
        _ensure_example_linked(path)
        raise ConfigError(
            f"首次运行: 已从 devagents.toml.example 生成 {path}\n"
            f"请编辑该文件（模型/单价等）后重试。密钥本身只放环境变量。"
        )

    try:
        with open(path, "rb") as fh:
            raw = tomllib.load(fh)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"配置 {path} 解析失败: {e}") from e

    raw = {k: v for k, v in raw.items() if k in KNOWN_SECTIONS}
    llm_raw = _merge_section(raw.get("llm"), DEFAULTS["llm"])
    if llm_raw["protocol"] not in ("openai", "anthropic"):
        raise ConfigError(f"未知 llm.protocol: {llm_raw['protocol']!r}（可选 openai/anthropic）")
    roles = _merge_section(raw.get("roles"), DEFAULTS["roles"])
    pipe_raw = _merge_section(raw.get("pipeline"), DEFAULTS["pipeline"])
    prices = raw.get("prices") or {}

    api_key = os.environ.get(str(llm_raw["key_env"]), "")
    if not api_key:
        raise ConfigError(
            f"缺少 API Key: 请设置环境变量 {llm_raw['key_env']}（按量 sk-key）。\n"
            f"⚠️ Token Plan key 仅限交互式使用，自动化脚本禁止（ToS 红线）。\n"
            f"Windows 可用: setx {llm_raw['key_env']} \"sk-...\"（新开终端生效）"
        )

    runs_rel = Path(str((raw.get("storage") or {}).get("runs_dir", "runs")))
    runs_dir = runs_rel if runs_rel.is_absolute() else PACKAGE_ROOT / runs_rel

    return Config(
        llm=LlmCfg(
            base_url=str(llm_raw["base_url"]),
            key_env=str(llm_raw["key_env"]),
            timeout_s=int(llm_raw["timeout_s"]),
            api_key=api_key,
            protocol=str(llm_raw["protocol"]),
            max_output_tokens=int(llm_raw["max_output_tokens"]),
        ),
        roles={r: str(m) for r, m in roles.items()},
        pipeline=PipelineCfg(
            context_budget_tokens=int(pipe_raw["context_budget_tokens"]),
            file_token_limit=int(pipe_raw["file_token_limit"]),
            fix_rounds_max=int(pipe_raw["fix_rounds_max"]),
            gate_retry=int(pipe_raw["gate_retry"]),
            transport_retry=int(pipe_raw["transport_retry"]),
            runner_timeout_s=int(pipe_raw["runner_timeout_s"]),
        ),
        prices=prices,
        runs_dir=runs_dir,
    )
