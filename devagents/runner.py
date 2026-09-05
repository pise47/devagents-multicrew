"""执行器（SPEC §7/§8）: 真实执行产出项目，机械判定结果。

白名单命令、仅工作区内、子进程超时。判定:
- Python 项目: 工作区 .venv → pip install requirements+pytest → python -m pytest -q
- 单页前端: 有 smoke.json → http.server + requests 冒烟（GET url + expect_text 断言）
- TIMEOUT/ERROR = 基础设施类 → pipeline 判 STOPPED；FAIL 才进修复链
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import requests

TAIL_CHARS = 4000


@dataclass(frozen=True)
class TestRun:
    verdict: str  # PASS | FAIL | TIMEOUT | ERROR
    exit_code: int
    stdout_tail: str
    elapsed_s: float
    workdir: str
    detail: str = ""

    __test__ = False  # 防 pytest 收集器误判为测试类


class Runner:
    """执行器实例。同一 workspace 的依赖安装只做一次（_installed 缓存）。"""

    def __init__(self, timeout_s: int = 180, python: str | None = None):
        self.timeout_s = timeout_s
        self.python = python or sys.executable
        # venv 创建/装依赖是基础设施步骤，不吃"测试执行超时"（防慢网络误杀）
        self._setup_timeout = max(timeout_s, 300)
        self._installed: set[Path] = set()

    # ---- Python 项目 ----

    def run_python_tests(self, ws: Path) -> TestRun:
        start = time.monotonic()
        try:
            venv_py = self._ensure_venv(ws)
            self._install_deps(ws, venv_py)
            return self._run_pytest(ws, venv_py, start)
        except subprocess.CalledProcessError as e:
            out = _tail((e.stdout or b"") + (e.stderr or b""))
            return TestRun("ERROR", e.returncode, out, time.monotonic() - start, str(ws), detail="依赖安装失败")
        except OSError as e:
            return TestRun("ERROR", -1, str(e), time.monotonic() - start, str(ws), detail="执行器系统错误")

    def _ensure_venv(self, ws: Path) -> Path:
        venv = ws / ".venv"
        venv_py = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        if not venv_py.exists():
            subprocess.run(
                [self.python, "-m", "venv", str(venv)],
                cwd=ws, check=True, capture_output=True, timeout=self._setup_timeout,
            )
        return venv_py

    def _install_deps(self, ws: Path, venv_py: Path) -> None:
        if ws in self._installed:
            return
        cmd = [str(venv_py), "-m", "pip", "install", "-q", "--disable-pip-version-check"]
        req = ws / "requirements.txt"
        if req.exists():
            cmd += ["-r", str(req)]
        cmd += ["pytest"]
        subprocess.run(
            cmd, cwd=ws, check=True, capture_output=True, timeout=self._setup_timeout,
        )
        self._installed.add(ws)

    def _run_pytest(self, ws: Path, venv_py: Path, start: float) -> TestRun:
        cmd = [str(venv_py), "-m", "pytest", "-q"]
        try:
            proc = subprocess.run(
                cmd, cwd=ws, capture_output=True, timeout=self.timeout_s,
            )
        except subprocess.TimeoutExpired as e:
            return TestRun("TIMEOUT", -1, _tail(e.output), time.monotonic() - start, str(ws), detail="测试超时")
        out = _tail((proc.stdout or b"") + (proc.stderr or b""))
        verdict = "PASS" if proc.returncode == 0 else "FAIL"
        return TestRun(verdict, proc.returncode, out, time.monotonic() - start, str(ws))

    # ---- 单页前端冒烟 ----

    def run_smoke(self, ws: Path, host: str = "127.0.0.1") -> TestRun:
        start = time.monotonic()
        smoke_file = ws / "smoke.json"
        if not smoke_file.exists():
            return TestRun("FAIL", -1, "缺少 smoke.json（test-agent 未产出冒烟契约）", 0.0, str(ws))
        try:
            spec = json.loads(smoke_file.read_text(encoding="utf-8"))
            url, expects = str(spec["url"]), [str(t) for t in spec["expect_text"]]
        except (ValueError, KeyError, TypeError) as e:
            return TestRun("FAIL", -1, f"smoke.json 解析失败: {e}", 0.0, str(ws))

        port = _free_port()
        proc = subprocess.Popen(
            [self.python, "-m", "http.server", str(port), "--bind", host],
            cwd=ws, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        lines: list[str] = []
        try:
            deadline = time.monotonic() + min(self.timeout_s, 30)
            resp = None
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    return TestRun("ERROR", proc.returncode, "http.server 提前退出", time.monotonic() - start, str(ws))
                try:
                    resp = requests.get(f"http://{host}:{port}{url}", timeout=3)
                    break
                except requests.RequestException:
                    time.sleep(0.2)
            if resp is None:
                return TestRun("TIMEOUT", -1, "服务器未就绪", time.monotonic() - start, str(ws))
            lines.append(f"GET {url} → HTTP {resp.status_code}")
            if resp.status_code != 200:
                lines.append("页面不可达（非 200）")
                return TestRun("FAIL", resp.status_code, "\n".join(lines), time.monotonic() - start, str(ws))
            body = resp.content.decode("utf-8", errors="replace")
            missing = [t for t in expects if t not in body]
            if missing:
                lines.append(f"缺失关键文本: {missing}")
                return TestRun("FAIL", -1, "\n".join(lines), time.monotonic() - start, str(ws))
            lines.append(f"关键文本全部命中: {expects}")
            return TestRun("PASS", 0, "\n".join(lines), time.monotonic() - start, str(ws))
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


def _tail(raw: bytes | str | None, chars: int = TAIL_CHARS) -> str:
    if raw is None:
        return ""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    return raw[-chars:]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
