import json
import pytest
from pathlib import Path
from todo import load_tasks, save_tasks, add_task, done_task, list_tasks

@pytest.fixture
def temp_file(tmp_path):
    """Provide a temporary file path for tests."""
    return tmp_path / "test_tasks.json"

class TestLoadTasks:
    def test_load_tasks_file_not_found(self, temp_file):
        """SPEC: 文件不存在则返回空列表。"""
        assert load_tasks(temp_file) == []

    def test_load_tasks_valid_json(self, temp_file):
        """SPEC: 加载有效的JSON列表。"""
        data = [{"id": 1, "description": "Test", "done": False}]
        temp_file.write_text(json.dumps(data), encoding="utf-8")
        loaded = load_tasks(temp_file)
        assert loaded == data

    def test_load_tasks_invalid_json(self, temp_file):
        """边界: 文件内容不是有效JSON。"""
        temp_file.write_text("not json", encoding="utf-8")
        assert load_tasks(temp_file) == []

    def test_load_tasks_not_a_list(self, temp_file):
        """边界: JSON文件内容不是列表（如字典）。"""
        data = {"id": 1, "description": "Test"}
        temp_file.write_text(json.dumps(data), encoding="utf-8")
        assert load_tasks(temp_file) == []

class TestSaveTasks:
    def test_save_tasks_creates_file(self, temp_file):
        """SPEC: 应生成或更新一个JSON文件。"""
        tasks = [{"id": 1, "description": "Task", "done": False}]
        save_tasks(tasks, temp_file)
        assert temp_file.exists()
        with open(temp_file, "r", encoding="utf-8") as f:
            saved = json.load(f)
        assert saved == tasks

    def test_save_tasks_updates_file(self, temp_file):
        """SPEC: 应更新一个JSON文件。"""
        initial = [{"id": 1, "description": "A", "done": False}]
        save_tasks(initial, temp_file)
        updated = [{"id": 1, "description": "A", "done": True}]
        save_tasks(updated, temp_file)
        with open(temp_file, "r", encoding="utf-8") as f:
            saved = json.load(f)
        assert saved == updated

class TestAddTask:
    def test_add_task_empty_list(self):
        """边界: 向空列表添加任务，ID应从1开始。"""
        tasks = add_task([], "First task")
        assert len(tasks) == 1
        assert tasks[0]["id"] == 1
        assert tasks[0]["description"] == "First task"
        assert tasks[0]["done"] is False

    def test_add_task_increments_id(self):
        """SPEC: ID自增。"""
        tasks = add_task([], "Task 1")
        tasks = add_task(tasks, "Task 2")
        assert tasks[0]["id"] == 1
        assert tasks[1]["id"] == 2

    def test_add_task_preserves_existing(self):
        """边界: 添加任务不应修改现有任务。"""
        existing = [{"id": 5, "description": "Old", "done": True}]
        tasks = add_task(existing, "New")
        assert len(tasks) == 2
        assert tasks[0]["id"] == 5
        assert tasks[1]["id"] == 6

class TestDoneTask:
    def test_done_task_valid_id(self):
        """SPEC: 标记一个待办事项为完成后，其状态在列表中应更新为已完成。"""
        tasks = [{"id": 1, "description": "A", "done": False},
                 {"id": 2, "description": "B", "done": False}]
        updated = done_task(tasks, 1)
        assert updated[0]["done"] is True
        assert updated[1]["done"] is False

    def test_done_task_invalid_id(self, capsys):
        """边界: 标记不存在的任务ID，应提示错误，列表不变。"""
        tasks = [{"id": 1, "description": "A", "done": False}]
        original_tasks = tasks.copy()
        updated = done_task(tasks, 999)
        captured = capsys.readouterr()
        assert "Error: Task with id 999 not found." in captured.out
        assert updated == original_tasks

class TestListTasks:
    def test_list_tasks_empty(self, capsys):
        """边界: 空列表应显示特定消息。"""
        list_tasks([])
        captured = capsys.readouterr()
        assert "No tasks found." in captured.out

    def test_list_tasks_format(self, capsys):
        """SPEC: 应正确显示每个事项的ID、描述和完成状态。"""
        tasks = [
            {"id": 1, "description": "Open task", "done": False},
            {"id": 2, "description": "Done task", "done": True}
        ]
        list_tasks(tasks)
        captured = capsys.readouterr()
        lines = captured.out.strip().split('\n')
        assert len(lines) == 2
        assert "1 [ ] Open task" in lines[0]
        assert "2 [x] Done task" in lines[1]