"""report 契约: REPORT.md/report.json 渲染与终态/账单呈现。"""

from __future__ import annotations

import json

from devagents.report import render_markdown, write_report

TERMINAL_TEXT = {
    "SUCCESS": "全部阶段通过",
    "FAILED": "修复环耗尽",
    "STOPPED": "基础设施中断",
}


def _summary(status: str, **over) -> dict:
    base = {
        "run_id": "test-run-1",
        "created_at": "2026-09-05T10:00:00",
        "task": "做一个 Todo CLI",
        "workspace": "ws",
        "status": status,
        "stages": [
            {
                "name": "spec",
                "model": "m-spec",
                "state": "done",
                "files": ["SPEC.md"],
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "error": None,
            },
            {
                "name": "test",
                "model": "m-test",
                "state": "done" if status != "STOPPED" else "error",
                "files": ["tests/test_todo.py", "TEST.md"],
                "prompt_tokens": 200,
                "completion_tokens": 80,
                "error": None if status != "STOPPED" else "HTTP 500: boom",
            },
        ],
        "fix_rounds": {"used": 1 if status == "FAILED" else 0, "max": 2},
        "elapsed_s": 12.3,
        "usage": {"prompt_tokens": 300, "completion_tokens": 130, "calls": 2},
        "cost": None,
    }
    base.update(over)
    return base


def test_write_report_creates_files(tmp_path):
    md = write_report(tmp_path / "r", _summary("SUCCESS", cost=1.25))
    assert md.exists()
    assert (tmp_path / "r" / "report.json").exists()
    data = json.loads((tmp_path / "r" / "report.json").read_text(encoding="utf-8"))
    assert data["status"] == "SUCCESS"
    assert data["stages"][0]["name"] == "spec"


def test_markdown_shows_status_and_stages():
    md = render_markdown(_summary("SUCCESS", cost=1.25))
    assert "SUCCESS" in md
    assert "做一个 Todo CLI" in md
    assert "SPEC.md" in md
    assert "¥1.25" in md


def test_markdown_failed_reports_fix_rounds():
    md = render_markdown(_summary("FAILED"))
    assert "FAILED" in md
    assert "修复环耗尽" in md


def test_markdown_stopped_includes_error_text():
    md = render_markdown(_summary("STOPPED"))
    assert "STOPPED" in md
    assert "HTTP 500" in md


def test_markdown_without_prices_says_token_only():
    md = render_markdown(_summary("SUCCESS"))
    assert "单价未配置" in md
    assert "¥" not in md.replace("¥1", "")  # 无费用行


def test_report_json_preserves_all_fields(tmp_path):
    s = _summary("FAILED")
    write_report(tmp_path / "r2", s)
    data = json.loads((tmp_path / "r2" / "report.json").read_text(encoding="utf-8"))
    assert data == s
    assert data["fix_rounds"]["used"] == 1
