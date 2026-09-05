"""命令行入口: run / report。exit code = 终态（SUCCESS=0 / FAILED=1 / STOPPED=2）。

run: 配置 → OpenAIClient/Runner → Pipeline → 报告落盘 → 控制台摘要。
测试注入点: build_llm / build_runner / run_task（可换 Fake 实现）。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from devagents import __version__, config as config_mod, report
from devagents.llm import AnthropicClient, OpenAIClient
from devagents.pipeline import Pipeline
from devagents.runner import Runner

EXIT = {"SUCCESS": 0, "FAILED": 1, "STOPPED": 2}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="devagents",
        description="多智能体代码开发系统：一条命令 + 一句需求 → 可运行、可验证的代码项目（见 SPEC.md）",
    )
    parser.add_argument("--version", action="version", version=f"devagents {__version__}")
    sub = parser.add_subparsers(dest="command")

    p_run = sub.add_parser("run", help="跑一个开发任务（spec→arch→code→test→review）")
    p_run.add_argument("task", nargs="?", help="自然语言任务描述；缺省时从 --task-file 读取")
    p_run.add_argument("--task-file", help="任务描述文件（优先于 task 参数）")
    p_run.add_argument("--out", required=True, help="工作区目录（产出代码写这里）")

    p_report = sub.add_parser("report", help="查看某次运行报告（runs/ 下，支持前缀匹配）")
    p_report.add_argument("run_id", help="运行 ID 或其前缀")

    return parser


def _utf8_streams() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def build_llm(config) -> OpenAIClient | AnthropicClient:
    """按 config.llm.protocol 选适配器: openai=按量兼容端, anthropic=Token Plan 套餐端。"""
    common = {
        "base_url": config.llm.base_url,
        "api_key": config.llm.api_key,
        "prices": config.prices,
        "timeout_s": config.llm.timeout_s,
        "transport_retry": config.pipeline.transport_retry,
    }
    if config.llm.protocol == "anthropic":
        return AnthropicClient(max_output_tokens=config.llm.max_output_tokens, **common)
    return OpenAIClient(**common)


def build_runner(config) -> Runner:
    return Runner(timeout_s=config.pipeline.runner_timeout_s)


def run_task(task: str, out: Path, config, llm, runner) -> int:
    """核心接线: 跑流水线 + 报告落盘 + 控制台摘要。返回 exit code。"""
    pipe = Pipeline(config=config, llm=llm, runner=runner, out_root=out, task=task)
    summary = pipe.run()
    runs_dir = config.runs_dir
    run_dir = runs_dir / summary["run_id"]
    md_path = report.write_report(run_dir, summary)
    status = summary["status"]
    print(f"\n=== 终态: {status} (exit {EXIT[status]}) ===")
    for st in summary["stages"]:
        mark = {"done": "✔", "PASS": "✔"}.get(st["state"], "✘")
        print(f"  {mark} {st['name']:<14} {st['state']}")
        if st.get("error"):
            print(f"      {st['error'][:300]}")
    u = summary["usage"]
    cost = summary["cost"]
    cost_txt = f"，估算费用 ¥{cost:.4f}" if cost is not None else "，单价未配置（仅报 token）"
    print(
        f"  消耗: 输入 {u['prompt_tokens']} / 输出 {u['completion_tokens']} token"
        f"（{u['calls']} 次调用）{cost_txt}"
    )
    print(f"  修复轮: {summary['fix_rounds']['used']}/{summary['fix_rounds']['max']}"
          f"　耗时: {summary['elapsed_s']}s")
    print(f"  报告: {run_dir}")
    print(f"  README 级报告: {md_path}")
    return EXIT[status]


def _locate_run(config, run_id: str) -> Path:
    """按 ID 或前缀定位 runs/<id> 目录。"""
    runs_dir = config.runs_dir
    exact = runs_dir / run_id
    if exact.is_dir():
        return exact
    hits = sorted(p for p in runs_dir.glob(f"{run_id}*") if p.is_dir())
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        raise SystemExit(f"run_id 前缀匹配到多个: {[h.name for h in hits]}")
    raise SystemExit(f"找不到运行 {run_id!r}（runs 目录: {runs_dir}）")


def cmd_report(args, config) -> int:
    run_dir = _locate_run(config, args.run_id)
    import json

    data = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    print(f"运行 {data['run_id']}  状态: {data['status']}  任务: {data['task']}")
    print(f"工作区: {data['workspace']}  修复轮: {data['fix_rounds']}")
    u = data["usage"]
    print(f"token: 输入 {u['prompt_tokens']} / 输出 {u['completion_tokens']}  耗时 {data['elapsed_s']}s")
    for st in data["stages"]:
        print(f"  [{st['state']}] {st['name']}")
        if st.get("error"):
            print(f"      {st['error'][:200]}")
    print(f"\n完整报告: {run_dir / 'REPORT.md'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    _utf8_streams()
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0
    # report 只读历史不需要 key（key 过期/轮换时照样能复盘）
    need_key = args.command == "run"
    try:
        config = config_mod.load_config(require_key=need_key)
    except config_mod.ConfigError as e:
        print(f"[devagents] 配置错误:\n{e}", file=sys.stderr)
        return 2

    if args.command == "run":
        if not config.llm.api_key:  # 双保险: run 路径必须真 key
            print("[devagents] 配置错误:\n缺少 API Key: 请设置环境变量 "
                  f"{config.llm.key_env} 后重试", file=sys.stderr)
            return 2
        task = None
        if args.task_file:
            task = Path(args.task_file).read_text(encoding="utf-8").strip()
        task = task or args.task
        if not task:
            print("[devagents] 需要任务描述（位置参数或 --task-file）", file=sys.stderr)
            return 2
        llm = build_llm(config)
        runner = build_runner(config)
        return run_task(task, Path(args.out).expanduser().resolve(), config, llm, runner)
    if args.command == "report":
        return cmd_report(args, config)
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
