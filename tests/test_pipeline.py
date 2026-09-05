"""pipeline 状态机契约: 表驱动的全链/修复链/终态矩阵（FakeLLM + FakeRunner，不触网）。"""

from __future__ import annotations

import pytest

import tests.samples as S
from devagents.config import Config
from devagents.llm import ChatResult, NetworkError
from devagents.pipeline import (
    Pipeline,
    gate_arch,
    gate_code,
    gate_review,
    gate_spec,
    parse_plan_file_list,
)
from devagents.runner import TestRun


def res(content: str, model: str = "m") -> ChatResult:
    return ChatResult(content=content, prompt_tokens=100, completion_tokens=40, model=model)


def code_n(n: int) -> list[ChatResult]:
    """修复轮会再调 code 模型，脚本需要追加份数。"""
    return [res(S.code_full_response()) for _ in range(n)]


class FakeRunner:
    """脚本化判定; 记录每次执行用的方法（python/smoke）与次数。"""

    def __init__(self, verdicts: list[str]):
        self.script = list(verdicts)
        self.calls: list[tuple[str, int]] = []

    def _next(self, kind: str) -> TestRun:
        idx = len([c for c in self.calls if c[0] == kind]) + 1
        if not self.script:
            raise AssertionError("FakeRunner 执行次数超出脚本")
        verdict = self.script.pop(0)
        self.calls.append((kind, idx))
        tail = {"PASS": "1 passed", "FAIL": "1 failed", "TIMEOUT": "TimeoutExpired"}[verdict]
        return TestRun(verdict=verdict, exit_code=0 if verdict == "PASS" else 1, stdout_tail=tail, elapsed_s=0.1, workdir=".")

    def run_python_tests(self, ws) -> TestRun:
        return self._next("python")

    def run_smoke(self, ws) -> TestRun:
        return self._next("smoke")


def happy_script() -> dict[str, list[ChatResult]]:
    return {
        "m-spec": [res(S.spec_response())],
        "m-arch": [res(S.plan_response())],
        "m-code": [res(S.code_full_response())],
        "m-test": [res(S.test_full_response())],
        "m-review": [res(S.review_response(blocker=False))],
    }


def run_pipeline(tmp_path, config: Config, llm, runner_verdicts=None, task="做一个 Todo CLI", out=None):
    runner = FakeRunner(runner_verdicts or [])
    ws = out or (tmp_path / "ws")
    pipe = Pipeline(config=config, llm=llm, runner=runner, out_root=ws, task=task)
    summary = pipe.run()
    return summary, runner, ws


def make_pipe_config(tmp_path, **kw) -> Config:
    import tests.conftest as C

    return C.make_config(tmp_path, **kw)


# ---------- 表驱动主矩阵 ----------


def test_full_chain_success(tmp_path, fake_llm):
    fake_llm.script = happy_script()  # 每次本地构建，FakeLLM 会消费队列
    summary, runner, ws = run_pipeline(tmp_path, make_pipe_config(tmp_path), fake_llm, runner_verdicts=["PASS"])
    assert summary["status"] == "SUCCESS"
    for f in ("SPEC.md", "PLAN.md", "todo.py", "requirements.txt", "test_todo.py", "TEST.md", "REVIEW.md"):
        assert (ws / f).exists(), f"缺产物 {f}"
    assert runner.calls == [("python", 1)]
    assert summary["fix_rounds"]["used"] == 0
    assert summary["usage"]["calls"] == 5
    # runner 结论机械写入 TEST.md（review 输入因此携带真实执行结果）
    assert "verdict: PASS" in (ws / "TEST.md").read_text(encoding="utf-8")


def test_review_blocker_then_fix_then_clean(tmp_path, fake_llm):
    script = happy_script()
    script["m-code"] += code_n(1)  # review 触发一轮修复
    script["m-review"] = [res(S.review_response(blocker=True)), res(S.review_response(blocker=False))]
    fake_llm.script = script
    summary, runner, ws = run_pipeline(tmp_path, make_pipe_config(tmp_path), fake_llm, runner_verdicts=["PASS", "PASS"])
    assert summary["status"] == "SUCCESS"
    assert summary["fix_rounds"]["used"] == 1
    assert runner.calls == [("python", 1), ("python", 2)]  # review 触发修复后重跑 test
    fix_call = [c for c in fake_llm.calls if c["model"] == "m-code" and len([x for x in fake_llm.calls if x["model"] == "m-code"]) > 1][-1]
    assert "缺陷报告" in fix_call["messages"][1]["content"]


def test_test_fail_then_fix_then_pass(tmp_path, fake_llm):
    script = happy_script()
    script["m-code"] += code_n(1)
    fake_llm.script = script  # code 内容一致即视为修复后版本（脚本静态）
    summary, _, _ = run_pipeline(tmp_path, make_pipe_config(tmp_path), fake_llm, runner_verdicts=["FAIL", "PASS"])
    assert summary["status"] == "SUCCESS"
    assert summary["fix_rounds"]["used"] == 1


def test_fix_budget_exhausted_failed(tmp_path, fake_llm):
    script = happy_script()
    script["m-code"] += code_n(2)
    fake_llm.script = script
    cfg = make_pipe_config(tmp_path, fix_rounds_max=2)
    summary, runner, _ = run_pipeline(tmp_path, cfg, fake_llm, runner_verdicts=["FAIL", "FAIL", "FAIL"])
    assert summary["status"] == "FAILED"
    assert summary["fix_rounds"]["used"] == 2
    assert runner.calls == [("python", 1), ("python", 2), ("python", 3)]


def test_timeout_anywhere_stopped_not_consuming_rounds(tmp_path, fake_llm, workspace):
    # 修复轮内超时 → STOPPED，修复计数不 +1
    script = happy_script()
    script["m-code"] += code_n(1)
    fake_llm.script = script
    cfg = make_pipe_config(tmp_path, fix_rounds_max=2)
    summary, _, _ = run_pipeline(tmp_path, cfg, fake_llm, runner_verdicts=["FAIL", "TIMEOUT"])
    assert summary["status"] == "STOPPED"
    assert summary["fix_rounds"]["used"] == 1  # 第一次 FAIL 已耗 1 轮，TIMEOUT 不耗第二轮


def test_api_error_stops_with_message(tmp_path, fake_llm):
    script = happy_script()
    script["m-arch"] = [NetworkError("连接失败 boom")]
    fake_llm.script = script
    summary, _, _ = run_pipeline(tmp_path, make_pipe_config(tmp_path), fake_llm, runner_verdicts=["PASS"])
    assert summary["status"] == "STOPPED"
    assert "boom" in summary["stages"][-1]["error"]


def test_frontend_full_chain_smoke(tmp_path, fake_llm):
    script = {
        "m-spec": [res(S.spec_response())],
        # 前端 PLAN: source index.html + test smoke.json
        "m-arch": [res(S.env("PLAN.md", "# 模块拆分\n- index.html: 单页\n\n## 接口定义\n- 无\n\n## 依赖\n- 无后端依赖\n\n## 预期文件清单\n- source: index.html\n- test: smoke.json\n"))],
        "m-code": [res(S.env("index.html", "<h1>番茄钟</h1>"))],
        "m-test": [res(S.env("smoke.json", '{"url": "/", "expect_text": ["番茄钟"]}') + S.env("TEST.md", S.TEST_MD_CONTENT))],
        "m-review": [res(S.review_response(blocker=False))],
    }
    fake_llm.script = script
    summary, runner, _ = run_pipeline(tmp_path, make_pipe_config(tmp_path), fake_llm, runner_verdicts=["PASS"])
    assert summary["status"] == "SUCCESS"
    assert runner.calls[0][0] == "smoke"  # 有 smoke.json → 走冒烟而非 pytest


# ---------- gate / 修复链失败路径 ----------

def test_gate_retry_once_then_stopped(tmp_path, fake_llm):
    """arch gate 持续失败 → 本阶段重试 1 次后 STOPPED。"""
    script = happy_script()
    script["m-arch"] = [res(S.env("PLAN.md", S.PLAN_MISSING_SECTIONS)), res(S.env("PLAN.md", S.PLAN_MISSING_SECTIONS))]
    fake_llm.script = script
    summary, _, _ = run_pipeline(tmp_path, make_pipe_config(tmp_path), fake_llm)
    assert summary["status"] == "STOPPED"
    arch_calls = [c for c in fake_llm.calls if c["model"] == "m-arch"]
    assert len(arch_calls) == 2  # 初始 + gate 重试 1
    assert "gate" in summary["stages"][-1]["error"].lower() or "校验" in summary["stages"][-1]["error"]


def test_gate_recovers_after_retry_with_hint(tmp_path, fake_llm):
    """越界路径 → 路径锁 ProtocolError 重试（文件未落盘）→ 第二次合规 → SUCCESS。"""
    script = happy_script()
    script["m-code"] = [res(S.CODE_ROGUE_EXTRA), res(S.code_full_response())]
    fake_llm.script = script
    summary, _, ws = run_pipeline(tmp_path, make_pipe_config(tmp_path), fake_llm, runner_verdicts=["PASS"])
    assert summary["status"] == "SUCCESS"
    assert not (ws / "rogue_extra.py").exists()
    code_calls = [c for c in fake_llm.calls if c["model"] == "m-code"]
    assert len(code_calls) == 2
    hint = code_calls[1]["messages"][1]["content"]
    assert any(k in hint for k in ("越权", "清单外", "越界"))


def test_review_cannot_rewrite_code(tmp_path, fake_llm):
    """Critical 回归: review 越权在信封里偷写代码 → 路径锁拒绝且不落盘。

    两轮都越权 → STOPPED；代码保持原样；runner 只执行过一次（无二次验证需求）。
    """
    script = happy_script()
    tampered = S.env("REVIEW.md", S.REVIEW_OK) + S.env("todo.py", "print('REVIEW WROTE THIS')")
    script["m-review"] = [res(tampered), res(tampered)]
    fake_llm.script = script
    summary, runner, ws = run_pipeline(tmp_path, make_pipe_config(tmp_path), fake_llm, runner_verdicts=["PASS"])
    assert summary["status"] == "STOPPED"
    assert "越权" in summary["stages"][-1]["error"]
    assert "REVIEW WROTE THIS" not in (ws / "todo.py").read_text(encoding="utf-8")
    assert runner.calls == [("python", 1)]  # 代码未被替换 → 没有二次执行


def test_review_tamper_retry_recovers_without_touching_code(tmp_path, fake_llm):
    """review 一次越权一次干净 → 重试恢复 SUCCESS，代码从未被碰（路径锁先于写盘）。"""
    script = happy_script()
    tampered = S.env("REVIEW.md", S.REVIEW_OK) + S.env("todo.py", "print('tamper')")
    script["m-review"] = [res(tampered), res(S.review_response(blocker=False))]
    fake_llm.script = script
    summary, _, ws = run_pipeline(tmp_path, make_pipe_config(tmp_path), fake_llm, runner_verdicts=["PASS"])
    assert summary["status"] == "SUCCESS"
    assert "tamper" not in (ws / "todo.py").read_text(encoding="utf-8")
    assert len([c for c in fake_llm.calls if c["model"] == "m-review"]) == 2


def test_test_agent_cannot_write_source(tmp_path, fake_llm):
    """test-agent 越权写 source → 路径锁拒绝 → 重试后干净通过，源文件不被碰。"""
    script = happy_script()
    rogue = S.env("test_todo.py", "x = 1") + S.env("TEST.md", S.TEST_MD_CONTENT) + S.env("todo.py", "print('tamper')")
    script["m-test"] = [res(rogue), res(S.test_full_response())]
    fake_llm.script = script
    summary, _, ws = run_pipeline(tmp_path, make_pipe_config(tmp_path), fake_llm, runner_verdicts=["PASS"])
    assert summary["status"] == "SUCCESS"
    assert "tamper" not in (ws / "todo.py").read_text(encoding="utf-8")
    assert len([c for c in fake_llm.calls if c["model"] == "m-test"]) == 2


def test_retry_attempts_all_recorded(tmp_path, fake_llm):
    """阶段重试的中间尝试也要入报告（usage 与 stage token 可对账）。"""
    script = happy_script()
    script["m-arch"] = [res(S.env("PLAN.md", S.PLAN_MISSING_SECTIONS)), res(S.plan_response())]
    fake_llm.script = script
    summary, _, _ = run_pipeline(tmp_path, make_pipe_config(tmp_path), fake_llm, runner_verdicts=["PASS"])
    assert summary["status"] == "SUCCESS"
    arch_rows = [s for s in summary["stages"] if s["name"].startswith("arch")]
    assert len(arch_rows) == 2
    assert arch_rows[0]["state"] == "error" and "gate" in arch_rows[0]["error"]
    assert arch_rows[1]["state"] == "done"


def test_parse_failure_retries_stage(tmp_path, fake_llm):
    script = happy_script()
    script["m-spec"] = [res("我直接口述，不写文件了。"), res(S.spec_response())]
    fake_llm.script = script
    summary, _, _ = run_pipeline(tmp_path, make_pipe_config(tmp_path), fake_llm, runner_verdicts=["PASS"])
    assert summary["status"] == "SUCCESS"
    assert len([c for c in fake_llm.calls if c["model"] == "m-spec"]) == 2


def test_parse_failure_exhausted_stopped(tmp_path, fake_llm):
    script = happy_script()
    script["m-spec"] = [res("没有信封。"), res("还是没有信封。")]
    fake_llm.script = script
    summary, _, _ = run_pipeline(tmp_path, make_pipe_config(tmp_path), fake_llm)
    assert summary["status"] == "STOPPED"
    assert "信封" in summary["stages"][0]["error"] or "解析" in summary["stages"][0]["error"]


# ---------- gate 与解析器直测 ----------

def test_parse_plan_file_list():
    lst = parse_plan_file_list(S.PLAN_OK)
    assert lst["source"] == ["todo.py"]
    assert lst["test"] == ["test_todo.py"]


def test_parse_plan_file_list_strips_comments_and_noise():
    text = "# 预期文件清单\n- source: a.py  # 注释\n- source: b.py\n- test: tests/test_a.py\n- 其他行忽略\n- source: c.py  # 含空格路径不允许在此测，保持简单\n"
    lst = parse_plan_file_list(text)
    assert lst["source"] == ["a.py", "b.py", "c.py"]
    assert lst["test"] == ["tests/test_a.py"]


def test_gate_spec_requires_four_sections(workspace):
    ok = workspace({"SPEC.md": S.SPEC_OK})
    assert gate_spec(ok)[0] is True
    bad = workspace({"SPEC.md": "# 目标\n啥也没有"})
    assert gate_spec(bad)[0] is False


def test_gate_arch_requires_four_elements(workspace):
    ok = workspace({"PLAN.md": S.PLAN_OK})
    assert gate_arch(ok)[0] is True
    bad = workspace({"PLAN.md": S.PLAN_MISSING_SECTIONS})
    assert gate_arch(bad)[0] is False


def test_gate_code_checks_plan_list_exactly(workspace):
    import tests.samples as S2

    ws = workspace({"PLAN.md": S2.PLAN_OK})
    plan = parse_plan_file_list(S2.PLAN_OK)
    assert gate_code(ws, plan["source"])[0] is False  # 缺 todo.py + requirements
    ws2 = workspace({"PLAN.md": S2.PLAN_OK, "todo.py": "x=1", "requirements.txt": "# ok"})
    assert gate_code(ws2, parse_plan_file_list(S2.PLAN_OK)["source"])[0] is True
    ws3 = workspace({"PLAN.md": S2.PLAN_OK, "todo.py": "x=1", "requirements.txt": "# ok", "rogue.py": "y=2"})
    assert gate_code(ws3, parse_plan_file_list(S2.PLAN_OK)["source"])[0] is False  # 越界
    ws4 = workspace({"PLAN.md": S2.PLAN_OK, "todo.py": "x=1"})  # 无 requirements → python 项目 FAIL
    assert gate_code(ws4, parse_plan_file_list(S2.PLAN_OK)["source"])[0] is False


def test_gate_review_parses_blocking_list(workspace):
    ok = workspace({"REVIEW.md": S.REVIEW_OK})
    blocked = workspace({"REVIEW.md": S.REVIEW_BLOCKER})
    assert gate_review(ok) == ([], True)  # （无）不视为阻断
    blockers, structure_ok = gate_review(blocked)
    assert structure_ok is True
    assert len(blockers) == 1
    assert blockers[0].startswith("正确性:")
