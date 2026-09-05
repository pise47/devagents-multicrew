"""cli 契约: run/report 接线 + exit code = 终态 + 报告落盘（Fake 注入，不触网）。"""

from __future__ import annotations

import json

import pytest

import tests.test_pipeline as TP
from devagents import cli
from devagents.config import ConfigError
from tests.conftest import FakeLLM, make_config


def _pipe_parts(tmp_path, fix_rounds_max: int = 2):
    """真实接线但注入 FakeLLM/FakeRunner 的一整套。"""
    import tests.conftest as C

    return C.make_config(tmp_path, fix_rounds_max=fix_rounds_max)


def test_run_success_exit_zero(tmp_path, capsys, monkeypatch):
    cfg = _pipe_parts(tmp_path)
    fake = FakeLLM(script=TP.happy_script())
    runner = TP.FakeRunner(["PASS"])
    out = tmp_path / "out"
    code = cli.run_task("做一个 Todo CLI", out, cfg, fake, runner)
    assert code == 0
    # 报告落盘在 config.runs_dir 下
    run_dirs = list(cfg.runs_dir.glob("*"))
    assert len(run_dirs) == 1
    data = json.loads((run_dirs[0] / "report.json").read_text(encoding="utf-8"))
    assert data["status"] == "SUCCESS"
    capsys_text = capsys.readouterr().out
    assert "SUCCESS" in capsys_text
    assert "¥" in capsys_text or "单价未配置" in capsys_text


def test_run_failed_exit_one(tmp_path):
    cfg = _pipe_parts(tmp_path, fix_rounds_max=1)
    script = TP.happy_script()
    script["m-code"] += TP.code_n(1)
    fake = FakeLLM(script=script)
    runner = TP.FakeRunner(["FAIL", "FAIL"])
    code = cli.run_task("x", tmp_path / "out", cfg, fake, runner)
    assert code == 1


def test_run_stopped_exit_two(tmp_path):
    cfg = _pipe_parts(tmp_path)
    script = TP.happy_script()
    script["m-arch"] = []
    fake = FakeLLM(script=script)
    code = cli.run_task("x", tmp_path / "out", cfg, fake, TP.FakeRunner([]))
    assert code == 2


def test_cmd_report_prefix_match(tmp_path, capsys):
    cfg = _pipe_parts(tmp_path)
    fake = FakeLLM(script=TP.happy_script())
    assert cli.run_task("t", tmp_path / "out", cfg, fake, TP.FakeRunner(["PASS"])) == 0
    run_id = list(cfg.runs_dir.glob("*"))[0].name
    parser = cli.build_parser()
    args = parser.parse_args(["report", run_id[:8]])  # 前缀
    assert cli.cmd_report(args, cfg) == 0
    assert "SUCCESS" in capsys.readouterr().out


def test_main_run_exit_code_via_factories(tmp_path, monkeypatch, capsys):
    """走真实 main(): 配置+工厂真实，只有 LLM/Runner 换 Fake。

    FakeLLM 按模型名分键 → 脚本键重映射成真实配置的角色模型名。
    """
    from devagents.config import EXAMPLE_CONFIG_PATH, load_config

    conf_path = tmp_path / "devagents.toml"
    conf_path.write_text(EXAMPLE_CONFIG_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setenv("DEVAGENTS_CONFIG", str(conf_path))
    monkeypatch.setenv("MIMO_API_KEY", "sk-test")
    cfg = load_config()
    # 真实配置 spec/arch/review 共用一个模型、code/test 共用一个:
    # 脚本按流水线调用顺序给每个模型排一队（FakeLLM 按模型名弹脚本）
    pro = cfg.roles["spec"]  # = arch = review
    light = cfg.roles["code"]  # = test
    script = {
        pro: [TP.res(TP.S.spec_response()), TP.res(TP.S.plan_response()), TP.res(TP.S.review_response(False))],
        light: [TP.res(TP.S.code_full_response()), TP.res(TP.S.test_full_response())],
    }
    fake = FakeLLM(script=script)
    monkeypatch.setattr(cli, "build_llm", lambda cfg: fake)
    monkeypatch.setattr(cli, "build_runner", lambda cfg: TP.FakeRunner(["PASS"]))
    code = cli.main(["run", "做个 Todo", "--out", str(tmp_path / "ws")])
    assert code == 0
    out = capsys.readouterr().out
    assert "SUCCESS" in out


def test_build_llm_switches_protocol(tmp_path, monkeypatch):
    """protocol=anthropic → AnthropicClient（tp 套餐端）；openai 默认不变。"""
    from devagents.config import load_config
    from devagents.llm import AnthropicClient, OpenAIClient

    conf = tmp_path / "c.toml"
    conf.write_text(
        "[llm]\nprotocol='anthropic'\nkey_env='MIMO_TP_API_KEY'\nbase_url='http://tp'\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DEVAGENTS_CONFIG", str(conf))
    monkeypatch.setenv("MIMO_TP_API_KEY", "tp-1")
    assert isinstance(cli.build_llm(load_config()), AnthropicClient)

    conf2 = tmp_path / "o.toml"
    conf2.write_text("[llm]\nkey_env='MIMO_API_KEY'\n", encoding="utf-8")
    monkeypatch.setenv("DEVAGENTS_CONFIG", str(conf2))
    monkeypatch.setenv("MIMO_API_KEY", "sk-1")
    assert isinstance(cli.build_llm(load_config()), OpenAIClient)


def _conf_without_key_file(tmp_path) -> str:
    """一个不含 key 的配置（缺 key 快速失败路径用）。"""
    p = tmp_path / "nokey.toml"
    p.write_text("[llm]\nkey_env='MIMO_API_KEY'\n", encoding="utf-8")
    return str(p)


def test_main_missing_key_exit_two(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("DEVAGENTS_CONFIG", _conf_without_key_file(tmp_path))
    monkeypatch.delenv("MIMO_API_KEY", raising=False)
    code = cli.main(["report", "xxx"])
    assert code == 2
    assert "Token Plan" in capsys.readouterr().err
