import json
import subprocess
import sys
from pathlib import Path
import pytest

@pytest.fixture
def todo_script():
    """Return the path to todo.py."""
    return Path(__file__).parent.parent / "todo.py"

@pytest.fixture
def work_dir(tmp_path, monkeypatch):
    """Create a temporary working directory and set DATA_FILE accordingly."""
    monkeypatch.chdir(tmp_path)
    # Create a todo module with a patched DATA_FILE for import if needed,
    # but we'll test via subprocess to simulate real CLI usage.
    return tmp_path

class TestCLIAdd:
    def test_add_then_list_shows_task(self, work_dir, todo_script):
        """SPEC: 添加待办事项后，运行列表命令应能看到该事项。"""
        description = "Buy groceries"
        # Add the task
        result = subprocess.run(
            [sys.executable, str(todo_script), "add", description],
            cwd=work_dir, capture_output=True, text=True
        )
        assert result.returncode == 0
        # List tasks
        result = subprocess.run(
            [sys.executable, str(todo_script), "list"],
            cwd=work_dir, capture_output=True, text=True
        )
        assert result.returncode == 0
        assert description in result.stdout

    def test_add_creates_json_file(self, work_dir, todo_script):
        """SPEC: 应用退出后，应生成或更新一个JSON文件包含所有待办事项。"""
        json_path = work_dir / "todos.json"
        assert not json_path.exists()
        subprocess.run(
            [sys.executable, str(todo_script), "add", "Test task"],
            cwd=work_dir, check=True
        )
        assert json_path.exists()
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert len(data) == 1
        assert data[0]["description"] == "Test task"
        assert data[0]["done"] is False

class TestCLIList:
    def test_list_empty(self, work_dir, todo_script):
        """边界: 没有任务时list应输出特定信息。"""
        result = subprocess.run(
            [sys.executable, str(todo_script), "list"],
            cwd=work_dir, capture_output=True, text=True
        )
        assert result.returncode == 0
        assert "No tasks found." in result.stdout

    def test_list_displays_status_correctly(self, work_dir, todo_script):
        """SPEC: 列出待办事项时，应正确显示每个事项的ID、描述和完成状态。"""
        # Add two tasks
        subprocess.run(
            [sys.executable, str(todo_script), "add", "Task A"],
            cwd=work_dir, check=True
        )
        subprocess.run(
            [sys.executable, str(todo_script), "add", "Task B"],
            cwd=work_dir, check=True
        )
        # Mark the first as done
        subprocess.run(
            [sys.executable, str(todo_script), "done", "1"],
            cwd=work_dir, check=True
        )
        # List
        result = subprocess.run(
            [sys.executable, str(todo_script), "list"],
            cwd=work_dir, capture_output=True, text=True
        )
        assert result.returncode == 0
        output = result.stdout
        assert "[x] Task A" in output
        assert "[ ] Task B" in output

class TestCLIDone:
    def test_done_updates_status_and_file(self, work_dir, todo_script):
        """SPEC: 标记一个待办事项为完成后，其状态在列表中应更新为已完成；JSON文件应更新。"""
        subprocess.run(
            [sys.executable, str(todo_script), "add", "Important task"],
            cwd=work_dir, check=True
        )
        subprocess.run(
            [sys.executable, str(todo_script), "done", "1"],
            cwd=work_dir, check=True
        )
        json_path = work_dir / "todos.json"
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert len(data) == 1
        assert data[0]["done"] is True
        # Verify via list command
        result = subprocess.run(
            [sys.executable, str(todo_script), "list"],
            cwd=work_dir, capture_output=True, text=True
        )
        assert "[x] Important task" in result.stdout

    def test_done_invalid_id(self, work_dir, todo_script):
        """边界: done命令使用无效ID应打印错误信息，文件不变。"""
        subprocess.run(
            [sys.executable, str(todo_script), "add", "Task"],
            cwd=work_dir, check=True
        )
        result = subprocess.run(
            [sys.executable, str(todo_script), "done", "999"],
            cwd=work_dir, capture_output=True, text=True
        )
        assert result.returncode == 0
        assert "Error: Task with id 999 not found." in result.stdout
        # Check file unchanged
        json_path = work_dir / "todos.json"
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data[0]["done"] is False

class TestCLIPersistence:
    def test_persistence_across_invocations(self, work_dir, todo_script):
        """SPEC: 重新启动应用后，从JSON文件加载数据，列表应显示之前的待办事项。"""
        # Simulate first run: add tasks
        subprocess.run(
            [sys.executable, str(todo_script), "add", "Persistent task 1"],
            cwd=work_dir, check=True
        )
        subprocess.run(
            [sys.executable, str(todo_script), "add", "Persistent task 2"],
            cwd=work_dir, check=True
        )
        # Simulate second run (new process): list should show both
        result = subprocess.run(
            [sys.executable, str(todo_script), "list"],
            cwd=work_dir, capture_output=True, text=True
        )
        assert result.returncode == 0
        assert "Persistent task 1" in result.stdout
        assert "Persistent task 2" in result.stdout

class TestCLINoThirdPartyDeps:
    """SPEC: 所有功能实现不导入任何第三方Python包。"""
    def test_no_imports_in_source(self, todo_script):
        """检查todo.py的导入是否仅使用标准库。"""
        with open(todo_script, "r", encoding="utf-8") as f:
            content = f.read()
        # Simple check: look for common third-party import patterns
        third_party_patterns = ["import requests", "from flask", "import pandas"]
        for pattern in third_party_patterns:
            assert pattern not in content, f"Third-party import found: {pattern}"