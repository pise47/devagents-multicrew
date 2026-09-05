"""运行报告（SPEC §4.4）: REPORT.md（人读）+ report.json（机读）+ 账单呈现。

summary 契约:
{
  "run_id", "created_at", "task", "workspace",
  "status": "SUCCESS"|"FAILED"|"STOPPED",
  "stages": [{"name","model","state","files","prompt_tokens","completion_tokens","error"}],
  "fix_rounds": {"used","max"},
  "elapsed_s", "usage": {"prompt_tokens","completion_tokens","calls"},
  "cost": float|None   # None = 单价未配置，只报 token
}
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

TERMINAL_REASON = {
    "SUCCESS": "全部阶段产物通过 gate，测试真实执行通过，无阻断项。",
    "FAILED": "修复环耗尽仍有失败（测试失败或审查阻断项未消除），业务未达成。",
    "STOPPED": "基础设施中断（API 失败 / gate 重试耗尽 / 超时 / 配置缺失），非业务原因。",
}


def new_run_id() -> str:
    """秒级时间戳 + 随机后缀: 同一秒多次 run 不互相覆盖 run 目录。"""
    import secrets

    return datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2)


def write_report(run_dir: Path, summary: dict) -> Path:
    """落盘 REPORT.md + report.json，返回 REPORT.md 路径。"""
    run_dir.mkdir(parents=True, exist_ok=True)
    md_path = run_dir / "REPORT.md"
    md_path.write_text(render_markdown(summary), encoding="utf-8")
    (run_dir / "report.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return md_path


def render_markdown(s: dict) -> str:
    status = s["status"]
    lines = [
        "# DevAgents 运行报告",
        "",
        f"- 运行 ID: `{s['run_id']}`　时间: {s['created_at']}",
        f"- 状态: **{status}**（exit code: {0 if status == 'SUCCESS' else 1 if status == 'FAILED' else 2}）",
        f"- 任务: {s['task']}",
        f"- 工作区: `{s['workspace']}`",
        f"- 耗时: {s['elapsed_s']:.1f}s　修复轮: {s['fix_rounds']['used']}/{s['fix_rounds']['max']}",
        "",
        f"> {TERMINAL_REASON.get(status, '')}",
        "",
        "## 阶段明细",
        "",
        "| 阶段 | 模型 | 状态 | 产物 | 输出 token |",
        "|------|------|------|------|-----------|",
    ]
    for st in s["stages"]:
        files = ", ".join(st["files"]) if st["files"] else "—"
        state = st["state"]
        lines.append(
            f"| {st['name']} | {st['model']} | {state} | {files} | "
            f"{st['prompt_tokens'] + st['completion_tokens']} |"
        )
        if st.get("error"):
            lines.append(f"\n**{st['name']} 阶段错误**: `{st['error']}`")
    lines += ["", "## 账单"]
    cost = s.get("cost")
    u = s["usage"]
    if cost is not None:
        lines.append(
            f"- 输入 {u['prompt_tokens']} token + 输出 {u['completion_tokens']} token"
            f"（{u['calls']} 次调用），估算费用 **¥{cost:.4f}**"
        )
    else:
        lines.append(
            f"- 输入 {u['prompt_tokens']} token + 输出 {u['completion_tokens']} token"
            f"（{u['calls']} 次调用）"
        )
        lines.append("- ⚠️ 单价未配置（devagents.toml [prices]），只报 token 不折算费用")
    lines += ["", "## 复现", "", f"```bash\npython -m devagents report {s['run_id']}\n```"]
    return "\n".join(lines)
