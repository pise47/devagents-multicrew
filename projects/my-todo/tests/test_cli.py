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
    """Create a temporary working directory and chdir into it."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


class TestCLIAdd:
    """SPEC验收: 运行 python todo.py add '描述' 后，todos.json 应新增条目"""

    def test_add_creates_json_file(self, work_dir, todo_script):
        """SPEC验收: 应创建todos.json文件，包含自增ID、给定描述和初始未完成状态。"""
        json_path = work_dir / "todos.json"
        assert not json_path.exists()
        result = subprocess.run(
            [sys.executable, str(todo_script), "add", "Test task"],
            cwd=work_dir, capture_output=True, text=True
        )
        assert result.returncode == 0
        assert json_path.exists()
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert len(data) == 1
        assert data[0]["id"] == 1
        assert data[0]["description"] == "Test task"
        assert data[0]["done"] is False

    def test_add_then_list_shows_task(self, work_dir, todo_script):
        """SPEC验收: 添加后通过list命令应能看到该任务。"""
        description = "Buy groceries"
        subprocess.run(
            [sys.executable, str(todo_script), "add", description],
            cwd=work_dir, capture_output=True, text=True
        )
        result = subprocess.run(
            [sys.executable, str(todo_script), "list"],
            cwd=work_dir, capture_output=True, text=True
        )
        assert result.returncode == 0
        assert description in result.stdout

    def test_add_multiple_tasks_increments_id(self, work_dir, todo_script):
        """SPEC验收: 多次添加后JSON文件中ID递增。"""
        subprocess.run(
            [sys.executable, str(todo_script), "add", "Task 1"],
            cwd=work_dir, check=True
        )
        subprocess.run(
            [sys.executable, str(todo_script), "add", "Task 2"],
            cwd=work_dir, check=True
        )
        json_path = work_dir / "todos.json"
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert len(data) == 2
        assert data[0]["id"] == 1
        assert data[1]["id"] == 2


class TestCLIList:
    """SPEC验收: 运行 python todo.py list 后，标准输出应列出所有Todo项"""

    def test_list_empty(self, work_dir, todo_script):
        """边界: 没有任务时list应输出提示信息。"""
        result = subprocess.run(
            [sys.executable, str(todo_script), "list"],
            cwd=work_dir, capture_output=True, text=True
        )
        assert result.returncode == 0
        assert "No tasks found." in result.stdout

    def test_list_displays_status_correctly(self, work_dir, todo_script):
        """SPEC验收: 格式为每行显示 ID、描述和状态。"""
        subprocess.run(
            [sys.executable, str(todo_script), "add", "Task A"],
            cwd=work_dir, check=True
        )
        subprocess.run(
            [sys.executable, str(todo_script), "add", "Task B"],
            cwd=work_dir, check=True
        )
        subprocess.run(
            [sys.executable, str(todo_script), "done", "1"],
            cwd=work_dir, check=True
        )
        result = subprocess.run(
            [sys.executable, str(todo_script), "list"],
            cwd=work_dir, capture_output=True, text=True
        )
        assert result.returncode == 0
        output = result.stdout
        assert "[x] Task A" in output
        assert "[ ] Task B" in output


class TestCLIDone:
    """SPEC验收: 运行 python todo.py done <ID> 后，对应项状态应变为完成"""

    def test_done_updates_json_file(self, work_dir, todo_script):
        """SPEC验收: done操作后todos.json中对应项done字段变为True。"""
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

    def test_done_shows_in_list(self, work_dir, todo_script):
        """SPEC验收: done操作后list命令显示[x]。"""
        subprocess.run(
            [sys.executable, str(todo_script), "add", "Task"],
            cwd=work_dir, check=True
        )
        subprocess.run(
            [sys.executable, str(todo_script), "done", "1"],
            cwd=work_dir, check=True
        )
        result = subprocess.run(
            [sys.executable, str(todo_script), "list"],
            cwd=work_dir, capture_output=True, text=True
        )
        assert "[x] Task" in result.stdout

    def test_done_invalid_id(self, work_dir, todo_script):
        """边界: done命令使用无效ID应打印错误信息，文件内容不变。"""
        subprocess.run(
            [sys.executable, str(todo_script), "add", "Task"],
            cwd=work_dir, check=True
        )
        result = subprocess.run(
            [sys.executable, str(todo_script), "done", "999"],
            cwd=work_dir, capture_output=True, text=True
        )
        assert "Error: Task with id 999 not found." in result.stdout
        json_path = work_dir / "todos.json"
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data[0]["done"] is False


class TestCLIPersistence:
    """SPEC验收: Todo数据持久化到JSON文件"""

    def test_persistence_across_invocations(self, work_dir, todo_script):
        """SPEC验收: 重新启动应用后从JSON文件加载数据。"""
        subprocess.run(
            [sys.executable, str(todo_script), "add", "Persistent task 1"],
            cwd=work_dir, check=True
        )
        subprocess.run(
            [sys.executable, str(todo_script), "add", "Persistent task 2"],
            cwd=work_dir, check=True
        )
        result = subprocess.run(
            [sys.executable, str(todo_script), "list"],
            cwd=work_dir, capture_output=True, text=True
        )
        assert result.returncode == 0
        assert "Persistent task 1" in result.stdout
        assert "Persistent task 2" in result.stdout

    def test_auto_create_json_on_first_run(self, work_dir, todo_script):
        """SPEC验收: 如果todos.json不存在，首次运行应自动创建并初始化为空列表。"""
        json_path = work_dir / "todos.json"
        assert not json_path.exists()
        result = subprocess.run(
            [sys.executable, str(todo_script), "list"],
            cwd=work_dir, capture_output=True, text=True
        )
        assert result.returncode == 0
        assert "No tasks found." in result.stdout


class TestCLINoThirdPartyDeps:
    """SPEC验收: 应用代码中不导入任何第三方模块"""

    def test_no_third_party_imports(self, todo_script):
        """检查todo.py仅使用标准库模块。"""
        with open(todo_script, "r", encoding="utf-8") as f:
            content = f.read()
        allowed_modules = {"json", "argparse", "sys", "pathlib", "os", "io", "typing"}
        for line in content.split('\n'):
            stripped = line.strip()
            if stripped.startswith("import ") and not stripped.startswith("#"):
                module = stripped.split()[1].split('.')[0]
                assert module in allowed_modules, \
                    f"Non-standard-library import found: {stripped}"
            elif stripped.startswith("from ") and not stripped.startswith("#"):
                module = stripped.split()[1].split('.')[0]
                assert module in allowed_modules, \
                    f"Non-standard-library import found: {stripped}"