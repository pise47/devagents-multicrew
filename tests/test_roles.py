"""roles 契约: 模板齐备/消息组装/修复模式/关键锚点（禁条、信封、清单格式）。"""

from __future__ import annotations

import pytest

from devagents.roles import (
    FIX_STAGE,
    assemble_messages,
    available_stages,
    load_prompt,
    model_for,
)


def test_all_stage_prompts_exist():
    for stage in available_stages():
        text = load_prompt(stage)
        assert text and len(text) > 50, f"{stage} 模板缺失或过短"


@pytest.mark.parametrize("stage", available_stages())
def test_every_prompt_has_envelope_and_no_verdict_rule(stage):
    """所有模板必须教信封格式，且禁止自行宣布结论。"""
    text = load_prompt(stage)
    assert "```path=" in text, f"{stage}: 缺信封格式说明"
    assert ("不得自行宣布" in text or "不写" in text or "不宣布" in text), f"{stage}: 缺禁条"


def test_fix_prompt_keywords():
    text = load_prompt(FIX_STAGE)
    assert "修复" in text
    assert "缺陷报告" in text
    assert "不修改的文件不要重发" in text


def test_arch_prompt_pins_file_list_syntax():
    text = load_prompt("arch")
    assert "- source:" in text and "- test:" in text
    assert "smoke.json" in text  # 前端冒烟契约指引


def test_review_prompt_pins_blocking_sections():
    text = load_prompt("review")
    assert "## 阻断项" in text and "## 建议项" in text
    assert "永不导致 FAIL" in text or "不" in text


def test_spec_prompt_pins_four_sections():
    text = load_prompt("spec")
    for sec in ("# 目标", "## 功能", "## 验收标准", "## 文件布局"):
        assert sec in text


def test_code_prompt_forbids_tests_and_extra_files():
    text = load_prompt("code")
    assert "不写测试" in text
    assert "requirements.txt" in text
    assert "清单外新增源文件 = 失败" in text


def test_assemble_messages_structure():
    msgs = assemble_messages("spec", "做一个 Todo")
    assert [m["role"] for m in msgs] == ["system", "user"]
    assert "spec-agent" in msgs[0]["content"]
    assert msgs[1]["content"] == "做一个 Todo"


def test_model_for_maps_stages_to_config():
    from devagents.config import LlmCfg, PipelineCfg
    from devagents.config import Config

    conf = Config(
        llm=LlmCfg("http://x", "K", 60, "k"),
        roles={"spec": "s", "arch": "a", "code": "c", "test": "t", "review": "r"},
        pipeline=PipelineCfg(60000, 12000, 2, 1, 1, 60),
        prices={},
        runs_dir=__import__("pathlib").Path("."),
    )
    assert model_for(conf, "spec") == "s"
    assert model_for(conf, "test") == "t"
    assert model_for(conf, FIX_STAGE) == "c"  # 修复用 code 角色模型


def test_available_stages_include_fix():
    assert FIX_STAGE in available_stages()
    assert {"spec", "arch", "code", "test", "review"} <= set(available_stages())
