import json
import inspect
import pytest
from pathlib import Path
from todo import load_tasks, save_tasks, add_task, done_task, list_tasks


@pytest.fixture
def temp_file(tmp_path):
    """Provide a temporary file path for tests."""
    return tmp_path / "test_tasks.json"


class TestLoadTasks:
    """Tests for load_tasks - SPEC: 文件不存在则返回空列表"""

    def test_load_tasks_file_not_found(self, temp_file):
        """SPEC验收: 如果todos.json文件不存在，应返回空列表。"""
        result = load_tasks(temp_file)
        assert result == []

    def test_load_tasks_valid_json_list(self, temp_file):
        """加载包含有效任务列表的JSON文件。"""
        data = [{"id": 1, "description": "Test", "done": False}]
        temp_file.write_text(json.dumps(data), encoding="utf-8")
        result = load_tasks(temp_file)
        assert result == data

    def test_load_tasks_invalid_json_syntax(self, temp_file):
        """边界: 文件内容不是有效JSON语法。"""
        temp_file.write_text("{not valid json", encoding="utf-8")
        result = load_tasks(temp_file)
        assert result == []

    def test_load_tasks_not_a_list(self, temp_file):
        """边界: JSON文件内容是字典而非列表。"""
        data = {"id": 1, "description": "Test"}
        temp_file.write_text(json.dumps(data), encoding="utf-8")
        result = load_tasks(temp_file)
        assert result == []

    def test_load_tasks_empty_list(self, temp_file):
        """边界: JSON文件内容为空列表。"""
        temp_file.write_text("[]", encoding="utf-8")
        result = load_tasks(temp_file)
        assert result == []

    def test_load_tasks_multiple_items(self, temp_file):
        """加载包含多个任务的文件，验证所有字段正确还原。"""
        data = [
            {"id": 1, "description": "A", "done": False},
            {"id": 2, "description": "B", "done": True},
        ]
        temp_file.write_text(json.dumps(data), encoding="utf-8")
        result = load_tasks(temp_file)
        assert len(result) == 2
        assert result[0]["done"] is False
        assert result[1]["done"] is True


class TestSaveTasks:
    """Tests for save_tasks - SPEC: 应生成或更新一个JSON文件"""

    def test_save_tasks_creates_new_file(self, temp_file):
        """SPEC验收: 保存后应生成JSON文件。"""
        tasks = [{"id": 1, "description": "Task", "done": False}]
        save_tasks(tasks, temp_file)
        assert temp_file.exists()
        with open(temp_file, "r", encoding="utf-8") as f:
            saved = json.load(f)
        assert saved == tasks

    def test_save_tasks_updates_existing_file(self, temp_file):
        """SPEC验收: 保存后应更新已有JSON文件。"""
        initial = [{"id": 1, "description": "A", "done": False}]
        save_tasks(initial, temp_file)
        updated = [{"id": 1, "description": "A", "done": True}]
        save_tasks(updated, temp_file)
        with open(temp_file, "r", encoding="utf-8") as f:
            saved = json.load(f)
        assert saved == updated

    def test_save_tasks_empty_list(self, temp_file):
        """边界: 保存空列表应写入有效的空JSON数组。"""
        save_tasks([], temp_file)
        assert temp_file.exists()
        with open(temp_file, "r", encoding="utf-8") as f:
            saved = json.load(f)
        assert saved == []

    def test_save_tasks_signature_no_default(self):
        """PLAN验收: save_tasks(tasks, filepath) 签名中 filepath 不得有默认值。"""
        sig = inspect.signature(save_tasks)
        params = list(sig.parameters.keys())
        assert params == ["tasks", "filepath"]
        for name in params:
            param = sig.parameters[name]
            assert param.default is inspect.Parameter.empty, \
                f"Parameter '{name}' should not have a default value"


class TestAddTask:
    """Tests for add_task - SPEC: 添加新的Todo项，ID自增"""

    def test_add_task_to_empty_list(self):
        """SPEC验收: 向空列表添加任务，ID从1开始，初始未完成。"""
        tasks = add_task([], "First task")
        assert len(tasks) == 1
        assert tasks[0]["id"] == 1
        assert tasks[0]["description"] == "First task"
        assert tasks[0]["done"] is False

    def test_add_task_increments_id(self):
        """SPEC验收: 多次添加后ID递增。"""
        tasks = add_task([], "Task 1")
        tasks = add_task(tasks, "Task 2")
        assert tasks[0]["id"] == 1
        assert tasks[1]["id"] == 2

    def test_add_task_id_from_max(self):
        """边界: ID从当前最大值递增，而非列表长度。"""
        existing = [{"id": 5, "description": "Old", "done": True}]
        tasks = add_task(existing, "New")
        assert len(tasks) == 2
        assert tasks[1]["id"] == 6

    def test_add_task_preserves_existing(self):
        """边界: 添加任务不应修改现有任务的内容。"""
        existing = [{"id": 1, "description": "Old", "done": True}]
        original_desc = existing[0]["description"]
        add_task(existing, "New")
        assert existing[0]["description"] == original_desc
        assert existing[0]["done"] is True

    def test_add_task_returns_same_list_object(self):
        """边界: 返回值应与输入列表为同一对象（原地修改）。"""
        original = []
        result = add_task(original, "Task")
        assert result is original

    def test_add_task_initial_done_is_false(self):
        """SPEC验收: 新任务初始状态为未完成。"""
        tasks = add_task([], "Task")
        assert tasks[0]["done"] is False


class TestDoneTask:
    """Tests for done_task - SPEC: 标记Todo项为完成"""

    def test_done_task_valid_id(self):
        """SPEC验收: 标记后对应项done变为True，其他不变。"""
        tasks = [
            {"id": 1, "description": "A", "done": False},
            {"id": 2, "description": "B", "done": False},
        ]
        updated = done_task(tasks, 1)
        assert updated[0]["done"] is True
        assert updated[1]["done"] is False

    def test_done_task_invalid_id(self, capsys):
        """边界: 标记不存在的任务ID，应提示错误且列表不变。"""
        tasks = [{"id": 1, "description": "A", "done": False}]
        original = [t.copy() for t in tasks]
        updated = done_task(tasks, 999)
        captured = capsys.readouterr()
        assert "Error: Task with id 999 not found." in captured.out
        assert updated == original

    def test_done_task_already_done(self):
        """边界: 标记一个已完成的任务，状态保持不变。"""
        tasks = [{"id": 1, "description": "A", "done": True}]
        updated = done_task(tasks, 1)
        assert updated[0]["done"] is True

    def test_done_task_empty_list(self, capsys):
        """边界: 在空列表上调用done_task应提示错误。"""
        updated = done_task([], 1)
        captured = capsys.readouterr()
        assert "Error: Task with id 1 not found." in captured.out
        assert updated == []

    def test_done_task_returns_same_list_object(self):
        """边界: 返回值应与输入列表为同一对象。"""
        tasks = [{"id": 1, "description": "A", "done": False}]
        result = done_task(tasks, 1)
        assert result is tasks


class TestListTasks:
    """Tests for list_tasks - SPEC: 标准输出应列出所有Todo项"""

    def test_list_tasks_empty(self, capsys):
        """边界: 空列表应显示特定提示。"""
        list_tasks([])
        captured = capsys.readouterr()
        assert "No tasks found." in captured.out

    def test_list_tasks_single_item(self, capsys):
        """SPEC验收: 列出单个任务，格式为 ID [状态] 描述。"""
        tasks = [{"id": 1, "description": "Buy milk", "done": False}]
        list_tasks(tasks)
        captured = capsys.readouterr()
        assert "1 [ ] Buy milk" in captured.out

    def test_list_tasks_format_done_status(self, capsys):
        """SPEC验收: 已完成任务显示[x]。"""
        tasks = [{"id": 1, "description": "Done task", "done": True}]
        list_tasks(tasks)
        captured = capsys.readouterr()
        assert "[x]" in captured.out
        assert "[ ]" not in captured.out

    def test_list_tasks_format_not_done_status(self, capsys):
        """SPEC验收: 未完成任务显示[ ]。"""
        tasks = [{"id": 1, "description": "Open task", "done": False}]
        list_tasks(tasks)
        captured = capsys.readouterr()
        assert "[ ]" in captured.out
        assert "[x]" not in captured.out

    def test_list_tasks_multiple_items(self, capsys):
        """SPEC验收: 多个任务按顺序逐行显示。"""
        tasks = [
            {"id": 1, "description": "Open task", "done": False},
            {"id": 2, "description": "Done task", "done": True},
        ]
        list_tasks(tasks)
        captured = capsys.readouterr()
        lines = captured.out.strip().split('\n')
        assert len(lines) == 2
        assert "1 [ ] Open task" in lines[0]
        assert "2 [x] Done task" in lines[1]


class TestFunctionSignatures:
    """验证所有函数签名与PLAN.md定义严格一致。"""

    def test_load_tasks_signature(self):
        sig = inspect.signature(load_tasks)
        assert list(sig.parameters.keys()) == ["filepath"]

    def test_save_tasks_signature(self):
        sig = inspect.signature(save_tasks)
        assert list(sig.parameters.keys()) == ["tasks", "filepath"]

    def test_add_task_signature(self):
        sig = inspect.signature(add_task)
        assert list(sig.parameters.keys()) == ["tasks", "description"]

    def test_done_task_signature(self):
        sig = inspect.signature(done_task)
        assert list(sig.parameters.keys()) == ["tasks", "task_id"]

    def test_list_tasks_signature(self):
        sig = inspect.signature(list_tasks)
        assert list(sig.parameters.keys()) == ["tasks"]

    def test_no_extra_default_params(self):
        """PLAN验收: 所有函数参数不得有默认值。"""
        for fn in [load_tasks, save_tasks, add_task, done_task, list_tasks]:
            sig = inspect.signature(fn)
            for name, param in sig.parameters.items():
                assert param.default is inspect.Parameter.empty, \
                    f"{fn.__name__}({name}) has unexpected default: {param.default}"