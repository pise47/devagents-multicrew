"""runner 契约: 真子进程执行（venv+pytest / http.server 冒烟）/ 超时 / 判定。

注: Python 项目用例会真建 venv + 装 pytest（走网络，各 ~10s），数量克制。
"""

from __future__ import annotations

import json
import time

import pytest

from devagents.runner import Runner, TestRun


def _py_ws(workspace) -> object:
    """一个可通过 pytest 的真实 Python 夹具项目。"""
    return workspace(
        {
            "todo.py": (
                "import json, sys\n"
                "from pathlib import Path\n"
                "DB = Path('todos.json')\n"
                "def load():\n"
                "    return json.loads(DB.read_text(encoding='utf-8')) if DB.exists() else []\n"
                "def save(todos):\n"
                "    DB.write_text(json.dumps(todos, ensure_ascii=False), encoding='utf-8')\n"
            ),
            "tests/test_todo.py": (
                "from pathlib import Path\n"
                "from todo import save, load\n"
                "def test_roundtrip(tmp_path, monkeypatch):\n"
                "    monkeypatch.setattr('todo.DB', tmp_path / 't.json')\n"
                "    save([{'title': 'x', 'done': False}])\n"
                "    assert load()[0]['title'] == 'x'\n"
            ),
            "requirements.txt": "# 无第三方依赖\n",
        }
    )


def _failing_ws(workspace) -> object:
    ws = _py_ws(workspace)
    (ws / "tests" / "test_todo.py").write_text(
        "def test_will_fail():\n    assert 1 == 2\n", encoding="utf-8"
    )
    return ws


def test_python_tests_pass(workspace):
    result: TestRun = Runner(timeout_s=180).run_python_tests(_py_ws(workspace))
    assert result.verdict == "PASS"
    assert result.exit_code == 0
    assert "1 passed" in result.stdout_tail


def test_python_tests_fail(workspace):
    result = Runner(timeout_s=180).run_python_tests(_failing_ws(workspace))
    assert result.verdict == "FAIL"
    assert result.exit_code != 0
    assert "1 failed" in result.stdout_tail


def test_timeout_verdict_timout(workspace):
    ws = workspace(
        {
            "sleep_test.py": "",
            "tests/test_slow.py": "import time\n\ndef test_slow():\n    time.sleep(30)\n",
        }
    )
    result = Runner(timeout_s=3).run_python_tests(ws)
    assert result.verdict == "TIMEOUT"


def _fe_ws(workspace, texts=None, url="/") -> object:
    return workspace(
        {
            "index.html": "<h1>番茄钟</h1><div id='clock'>25:00</div>",
            "smoke.json": json.dumps({"url": url, "expect_text": texts or ["番茄钟", "25:00"]}),
        }
    )


def test_frontend_smoke_pass(workspace):
    result = Runner(timeout_s=30).run_smoke(_fe_ws(workspace))
    assert result.verdict == "PASS"
    assert result.exit_code == 0


def test_frontend_smoke_fail_missing_text(workspace):
    ws = _fe_ws(workspace, texts=["番茄钟", "不存在的文案"])
    result = Runner(timeout_s=30).run_smoke(ws)
    assert result.verdict == "FAIL"
    assert "不存在的文案" in result.stdout_tail


def test_frontend_smoke_fail_404(workspace):
    ws = _fe_ws(workspace, url="/no-such-page")
    result = Runner(timeout_s=30).run_smoke(ws)
    assert result.verdict == "FAIL"
    assert "404" in result.stdout_tail


def test_frontend_smoke_missing_smoke_json(workspace):
    ws = workspace({"index.html": "<h1>x</h1>"})
    result = Runner(timeout_s=30).run_smoke(ws)
    assert result.verdict == "FAIL"
    assert "smoke.json" in result.stdout_tail
