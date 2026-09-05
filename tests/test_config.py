"""config 加载测试: 默认值合并 / env 覆盖 / 首跑复制 / 缺 key 快速失败。"""

from __future__ import annotations

import os

import pytest

import devagents.config as cfg
from devagents.config import ConfigError


@pytest.fixture
def no_real_toml(tmp_path, monkeypatch):
    """把配置路径指到不存在的文件，隔离真实仓库配置。"""
    fake = tmp_path / "devagents.toml"
    monkeypatch.setenv("DEVAGENTS_CONFIG", str(fake))
    monkeypatch.delenv("MIMO_API_KEY", raising=False)
    return fake


def test_missing_toml_copies_example_then_fails_with_guidance(no_real_toml, monkeypatch):
    """缺 toml: 首跑自动复制 example，并报 ConfigError 带补配指引。"""
    with pytest.raises(ConfigError) as ei:
        cfg.load_config()
    assert no_real_toml.exists(), "应已从 example 复制出 devagents.toml"
    msg = str(ei.value)
    assert "编辑" in msg and "devagents.toml" in msg


def test_missing_key_env_fails_fast_with_red_line(no_real_toml, monkeypatch):
    """toml 在位但 key 环境变量缺失 → 快速失败，提示 key_env 名与 Token Plan 红线。"""
    no_real_toml.write_text("[llm]\nbase_url='http://x'\n", encoding="utf-8")
    with pytest.raises(ConfigError) as ei:
        cfg.load_config()
    msg = str(ei.value)
    assert "MIMO_API_KEY" in msg
    assert "Token Plan" in msg


def test_defaults_merged_and_overrides_applied(no_real_toml, monkeypatch):
    """部分段缺失时合并默认值；显式段覆盖默认值。"""
    monkeypatch.setenv("MIMO_API_KEY", "sk-test")
    no_real_toml.write_text(
        "[roles]\ncode='my-code-model'\n[pipeline]\nfix_rounds_max=3\n",
        encoding="utf-8",
    )
    conf = cfg.load_config()
    assert conf.llm.base_url == "https://api.xiaomimimo.com/v1"  # 默认
    assert conf.llm.api_key == "sk-test"
    assert conf.roles["code"] == "my-code-model"  # 覆盖
    assert conf.roles["review"] == "mimo-v2.5-pro"  # 默认保留
    assert conf.pipeline.fix_rounds_max == 3
    assert conf.pipeline.context_budget_tokens == 60000
    assert conf.prices == {}


def test_invalid_toml_reports_config_error(no_real_toml, monkeypatch):
    no_real_toml.write_text("[llm\nbroken", encoding="utf-8")
    monkeypatch.setenv("MIMO_API_KEY", "sk-test")
    with pytest.raises(ConfigError):
        cfg.load_config()


def test_unknown_sections_tolerated(no_real_toml, monkeypatch):
    """未知段容忍忽略（不崩），便于向前兼容。"""
    monkeypatch.setenv("MIMO_API_KEY", "sk-test")
    no_real_toml.write_text("[future.stuff]\nx=1\n", encoding="utf-8")
    conf = cfg.load_config()
    assert conf.roles["code"] == "mimo-v2.5"


def test_resolve_api_key_env_override_has_priority(no_real_toml, monkeypatch):
    """key_env 指向的变量缺失时, 报错信息包含具体变量名。"""
    no_real_toml.write_text("[llm]\nkey_env='CUSTOM_LLM_KEY'\n", encoding="utf-8")
    monkeypatch.setenv("CUSTOM_LLM_KEY", "sk-custom")
    conf = cfg.load_config()
    assert conf.llm.api_key == "sk-custom"


def test_anthropic_protocol_preset(no_real_toml, monkeypatch):
    no_real_toml.write_text(
        "[llm]\nprotocol='anthropic'\nkey_env='MIMO_TP_API_KEY'\n"
        "base_url='https://token-plan-cn.xiaomimimo.com/anthropic'\nmax_output_tokens=8192\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MIMO_TP_API_KEY", "tp-test")
    conf = cfg.load_config()
    assert conf.llm.protocol == "anthropic"
    assert conf.llm.api_key == "tp-test"
    assert conf.llm.max_output_tokens == 8192


def test_invalid_protocol_rejected(no_real_toml, monkeypatch):
    no_real_toml.write_text("[llm]\nprotocol='grpc'\n", encoding="utf-8")
    monkeypatch.setenv("MIMO_API_KEY", "sk")
    with pytest.raises(ConfigError) as ei:
        cfg.load_config()
    assert "protocol" in str(ei.value)


def test_protocol_defaults_to_openai(no_real_toml, monkeypatch):
    monkeypatch.setenv("MIMO_API_KEY", "sk")
    no_real_toml.write_text("", encoding="utf-8")
    assert cfg.load_config().llm.protocol == "openai"
