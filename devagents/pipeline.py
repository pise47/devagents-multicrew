"""流水线状态机（SPEC §2/§4）: 五阶段串行 + 产物 gate + 修复链 + 终态判定。

核心原则: LLM 只产内容，一切 PASS/FAIL/终态由本模块机械规则判定。
- gate 失败 / 信封解析失败 → 本阶段重试 gate_retry 次 → 仍失败 STOPPED
- 统一循环: 测试执行 → PASS 进 review；FAIL 进修复轮；修复后必回测试（test 先于 review 双门）
- review 阻断项非空 → 修复轮（携带阻断项清单）→ 回测试 → 复审
- API 失败 / TIMEOUT / ERROR → STOPPED（不消耗修复轮计数、不进 FAILED）
- code 越界新增源文件 = gate FAIL + 下次尝试前清理（_prune_out_of_plan）
"""

from __future__ import annotations

import re
import time
from pathlib import Path

from devagents import context, report, roles
from devagents.llm import LLMError
from devagents.protocol import ProtocolError, parse_envelopes, resolve_safe_path

# code/fix 阶段允许写的非清单文件（流水线自身产物与依赖清单）
_DOC_ALLOWED = {"SPEC.md", "PLAN.md", "TEST.md", "REVIEW.md", "requirements.txt"}
_SECTION_RE = re.compile(r"^-\s+(source|test):\s*(\S+)\s*(?:#.*)?$", re.MULTILINE)
_EXEMPT_DIR = re.compile(r"(^|/)(__pycache__|\.pytest_cache|\.venv|venv|htmlcov|\.git)(/|$)")


# ---------- 产物 gate（机械校验） ----------

def _read(ws: Path, name: str) -> str | None:
    p = ws / name
    if not p.exists():
        return None
    try:
        return p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def gate_spec(ws: Path) -> tuple[bool, str]:
    text = _read(ws, "SPEC.md")
    if text is None:
        return False, "缺 SPEC.md"
    missing = [m for m in ("# 目标", "## 功能", "## 验收标准", "## 文件布局") if m not in text]
    if missing:
        return False, f"SPEC.md 缺章节: {missing}"
    return True, "SPEC.md 四章节齐全"


def parse_plan_file_list(text: str) -> dict[str, list[str]]:
    """解析 PLAN 预期文件清单: `- source: a.py` / `- test: t.py`（# 注释剥除）。"""
    out: dict[str, list[str]] = {"source": [], "test": []}
    for m in _SECTION_RE.finditer(text):
        kind, path = m.group(1), m.group(2)
        if path not in out[kind]:
            out[kind].append(path)
    return out


def gate_arch(ws: Path) -> tuple[bool, str]:
    text = _read(ws, "PLAN.md")
    if text is None:
        return False, "缺 PLAN.md"
    missing = [m for m in ("# 模块拆分", "## 接口定义", "## 依赖", "## 预期文件清单") if m not in text]
    if missing:
        return False, f"PLAN.md 缺要素: {missing}"
    lst = parse_plan_file_list(text)
    if not lst["source"]:
        return False, "PLAN.md 预期文件清单缺少 source 条目"
    return True, "PLAN.md 四要素齐全"


def _ws_files(ws: Path) -> list[str]:
    """工作区相对文件清单（豁免环境/缓存目录），供越界核对。"""
    out = []
    for p in ws.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(ws).as_posix()
        if _EXEMPT_DIR.search(rel) or p.suffix in (".pyc", ".pyo"):
            continue
        out.append(rel)
    return out


def gate_code(ws: Path, plan_sources: list[str], plan_tests: list[str] | None = None) -> tuple[bool, str]:
    """缺文件 FAIL；越界新增源文件 FAIL（allowed = source ∪ test ∪ 流水线文档）。"""
    missing = [f for f in plan_sources if not (ws / f).exists()]
    if missing:
        return False, f"PLAN 清单文件缺失: {missing}"
    allowed = set(plan_sources) | set(plan_tests or []) | _DOC_ALLOWED
    extra = [rel for rel in _ws_files(ws) if rel not in allowed]
    if extra:
        return False, f"清单外新增文件（越界）: {extra}"
    return True, "清单文件齐备且无越界"


def _prune_out_of_plan(ws: Path, plan_sources: list[str], plan_tests: list[str] | None = None) -> list[str]:
    """删除 code 误产的清单外文件（gate FAIL 后，下一次尝试前清理）。"""
    allowed = set(plan_sources) | set(plan_tests or []) | _DOC_ALLOWED
    removed = []
    for rel in sorted(_ws_files(ws)):
        if rel not in allowed:
            try:
                (ws / rel).unlink()
                removed.append(rel)
            except OSError:
                pass
    return removed


def gate_test(ws: Path, plan_tests: list[str]) -> tuple[bool, str]:
    missing = [f for f in plan_tests if not (ws / f).exists()]
    if missing:
        return False, f"PLAN 测试文件缺失: {missing}"
    if not (ws / "TEST.md").exists():
        return False, "缺 TEST.md"
    return True, "测试文件齐备"


def gate_review(ws: Path) -> tuple[list[str], bool]:
    """解析 REVIEW.md → (阻断项列表, 结构是否合法)。阻断判定在本模块，LLM 不宣布。"""
    text = _read(ws, "REVIEW.md")
    if text is None:
        return [], False
    if "## 阻断项" not in text or "## 建议项" not in text:
        return [], False
    blockers: list[str] = []
    section = text.split("## 阻断项", 1)[1].split("## 建议项", 1)[0]
    for line in section.splitlines():
        line = line.strip()
        if line.startswith("- "):
            item = line[2:].strip()
            if item and item not in ("（无）", "(无)", "无"):
                blockers.append(item)
    return blockers, True


def gate_review_structure(ws: Path) -> tuple[bool, str]:
    _, ok = gate_review(ws)
    return ok, "" if ok else "REVIEW.md 结构不完整（缺 ## 阻断项 / ## 建议项）"


# ---------- 流水线 ----------

class Pipeline:
    def __init__(self, config, llm, runner, out_root: Path, task: str):
        self.cfg = config
        self.llm = llm
        self.runner = runner
        self.out_root = Path(out_root)
        self.task = task
        self.stages: list[dict] = []
        self.fix_rounds_used = 0
        self._plan_sources: list[str] = []
        self._plan_tests: list[str] = []

    # ---- 对外 ----

    def run(self) -> dict:
        started = time.monotonic()
        self.out_root.mkdir(parents=True, exist_ok=True)
        p = self.cfg.pipeline
        self._budget, self._file_limit = p.context_budget_tokens, p.file_token_limit
        self._fix_max = p.fix_rounds_max
        self._gate_retry = p.gate_retry

        # ① spec → ② arch（arch 后解析 PLAN 文件清单，锁定本轮范围）
        if self._run_llm_stage("spec", self.task, gate_spec) != "ok":
            return self._summary("STOPPED", started)
        if self._run_llm_stage("arch", self._snapshot(), gate_arch) != "ok":
            return self._summary("STOPPED", started)
        plan = _read(self.out_root, "PLAN.md") or ""
        self._plan_sources = parse_plan_file_list(plan)["source"]
        self._plan_tests = parse_plan_file_list(plan).get("test", [])

        # ③ code（越界 = gate FAIL + 尝试前清理）
        if self._run_llm_stage("code", self._snapshot(), self._gate_code_now, prune=True) != "ok":
            return self._summary("STOPPED", started)

        # ④ test-agent 设计测试（一次性；修复轮重跑同一套测试，不重新设计）
        if self._run_llm_stage("test", self._snapshot(), self._gate_test_now) != "ok":
            return self._summary("STOPPED", started)

        # ⑤ 统一验证循环: 测试执行 → review 复审（双门），修复后必回测试
        while True:
            outcome = self._execute_tests()
            if outcome.verdict in ("TIMEOUT", "ERROR"):
                return self._summary("STOPPED", started)  # 修复轮内中断不耗计数
            if outcome.verdict == "FAIL":
                st = self._enter_fix_round(f"测试失败\n{_head(outcome.stdout_tail)}")
                if st != "ok":
                    return self._summary("FAILED" if st == "budget" else "STOPPED", started)
                continue  # 修复后回测试（test 先于 review）
            # PASS → review
            if self._run_llm_stage("review", self._snapshot(), gate_review_structure) != "ok":
                return self._summary("STOPPED", started)
            blockers, _ = gate_review(self.out_root)
            if not blockers:
                return self._summary("SUCCESS", started)
            st = self._enter_fix_round("审查阻断项:\n" + "\n".join(f"- {b}" for b in blockers))
            if st != "ok":
                return self._summary("FAILED" if st == "budget" else "STOPPED", started)
            # 修复后回测试重跑 → 再复审

    # ---- 阶段执行 ----

    def _gate_code_now(self, ws: Path) -> tuple[bool, str]:
        return gate_code(ws, self._plan_sources, self._plan_tests)

    def _gate_test_now(self, ws: Path) -> tuple[bool, str]:
        return gate_test(ws, self._plan_tests)

    def _run_llm_stage(self, stage: str, user_text: str, gate_fn, prune: bool = False) -> str:
        """一次 LLM 阶段: 信封解析 + 写文件 + gate；失败按 gate_retry 重试后 STOPPED。"""
        attempts = 1 + self._gate_retry
        for attempt in range(attempts):
            if prune and (self._plan_sources or self._plan_tests):
                removed = _prune_out_of_plan(self.out_root, self._plan_sources, self._plan_tests)
                if removed:
                    user_text += f"\n[前置清理] 已删除清单外文件: {removed}"
            record = {
                "name": stage if attempt == 0 else f"{stage}(重试{attempt})",
                "model": roles.model_for(self.cfg, stage),
                "state": "error",
                "files": [],
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "error": None,
            }
            try:
                result = self.llm.chat(roles.assemble_messages(stage, user_text), model=record["model"])
            except LLMError as e:
                record["error"] = f"API 失败: {e}"
                self.stages.append(record)
                return "stopped"
            record["prompt_tokens"], record["completion_tokens"] = result.prompt_tokens, result.completion_tokens
            try:
                blocks = parse_envelopes(result.content)
                if not blocks:
                    raise ProtocolError("响应中未找到任何 ```path= 信封块")
            except ProtocolError as e:
                record["error"] = f"信封解析失败: {e}"
                if attempt < attempts - 1:
                    user_text += f"\n[阶段重试 {attempt + 1}] 上次输出信封解析失败: {e}。请严格按 ```path= 格式输出。"
                    continue
                self.stages.append(record)
                return "stopped"
            wrote: list[str] = []
            for rel, content in blocks:
                target = resolve_safe_path(self.out_root, rel)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
                wrote.append(rel)
            record["files"] = wrote
            ok, msg = gate_fn(self.out_root)
            if ok:
                record["state"] = "done"
                self.stages.append(record)
                return "ok"
            record["error"] = f"产物 gate 校验失败: {msg}"
            if attempt < attempts - 1:
                user_text += f"\n[阶段重试 {attempt + 1}] 上次产物未通过校验: {msg}。请修正后重新输出。"
        self.stages.append(record)
        return "stopped"

    def _execute_tests(self) -> object:
        outcome = (
            self.runner.run_smoke(self.out_root)
            if (self.out_root / "smoke.json").exists()
            else self.runner.run_python_tests(self.out_root)
        )
        self.stages.append({
            "name": "test:执行",
            "model": "runner",
            "state": outcome.verdict,
            "files": [],
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "error": None if outcome.verdict == "PASS" else _head(outcome.stdout_tail),
        })
        return outcome

    def _enter_fix_round(self, defect_report: str) -> str:
        """修复轮: code_fix（SPEC+PLAN+代码树+缺陷报告）→ 返回 ok/budget/stopped。"""
        if self.fix_rounds_used >= self._fix_max:
            return "budget"
        self.fix_rounds_used += 1
        user_text = self._snapshot() + "\n\n# 【缺陷报告】\n" + defect_report
        state = self._run_llm_stage(roles.FIX_STAGE, user_text, self._gate_code_now, prune=True)
        if state != "ok":
            return "stopped" if state == "stopped" else "budget"
        self.stages.append({
            "name": f"fix#{self.fix_rounds_used}",
            "model": roles.model_for(self.cfg, roles.FIX_STAGE),
            "state": "done",
            "files": [],
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "error": None,
        })
        return "ok"

    # ---- 上下文与汇总 ----

    def _snapshot(self) -> str:
        text, _ = context.assemble_context(self.out_root, self._budget, self._file_limit)
        return text

    def _summary(self, status: str, started: float) -> dict:
        u = self.llm.usage
        return {
            "run_id": report.new_run_id(),
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "task": self.task,
            "workspace": str(self.out_root),
            "status": status,
            "stages": self.stages,
            "fix_rounds": {"used": self.fix_rounds_used, "max": self._fix_max},
            "elapsed_s": round(time.monotonic() - started, 1),
            "usage": {"prompt_tokens": u.prompt_tokens, "completion_tokens": u.completion_tokens, "calls": u.calls},
            "cost": self.llm.total_cost(),
        }


def _head(text: str, chars: int = 1500) -> str:
    return (text or "")[:chars]
