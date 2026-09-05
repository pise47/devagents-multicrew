import os
import json
import pytest
from todo import load_tasks, save_tasks, add_task, list_tasks, done_task, TASKS_FILE

@pytest.fixture(autouse=True)
def clean_up_tasks_file():
    """每个测试前清理 todos.json，测试后也清理"""
    if os.path.exists(TASKS_FILE):
        os.remove(TASKS_FILE)
    yield
    if os.path.exists(TASKS_FILE):
        os.remove(TASKS_FILE)

class TestLoadTasks:
    def test_file_not_exists_returns_empty_list(self):
        """验收标准：若文件不存在则返回空列表"""
        assert load_tasks() == []
    
    def test_loads_existing_tasks(self):
        """验收标准：能从文件正确加载任务"""
        initial_tasks = [{"id": 1, "description": "Test", "status": "pending"}]
        save_tasks(initial_tasks)
        assert load_tasks() == initial_tasks
    
    def test_corrupted_file_returns_empty_list(self):
        """边界：文件内容损坏时返回空列表"""
        with open(TASKS_FILE, 'w', encoding='utf-8') as f:
            f.write("not valid json")
        assert load_tasks() == []

class TestSaveTasks:
    def test_creates_file(self):
        """验收标准：能创建并写入文件"""
        tasks = [{"id": 1, "description": "Save test", "status": "pending"}]
        save_tasks(tasks)
        assert os.path.exists(TASKS_FILE)
        with open(TASKS_FILE, 'r', encoding='utf-8') as f:
            assert json.load(f) == tasks

class TestAddTask:
    def test_add_first_task(self):
        """验收标准：添加新任务，ID为1，描述为指定值，状态为pending"""
        add_task("Buy groceries")
        tasks = load_tasks()
        assert len(tasks) == 1
        assert tasks[0]["id"] == 1
        assert tasks[0]["description"] == "Buy groceries"
        assert tasks[0]["status"] == "pending"
    
    def test_add_multiple_tasks_increments_id(self):
        """验收标准：自动生成唯一递增ID"""
        add_task("Task 1")
        add_task("Task 2")
        tasks = load_tasks()
        assert len(tasks) == 2
        assert tasks[0]["id"] == 1
        assert tasks[1]["id"] == 2
    
    def test_add_task_with_spaces_in_description(self):
        """验收标准：描述参数支持空格"""
        add_task("Buy milk and bread")
        tasks = load_tasks()
        assert tasks[0]["description"] == "Buy milk and bread"

class TestListTasks:
    def test_list_empty(self):
        """验收标准：无任务时list输出为空（通过捕获stdout验证）"""
        from io import StringIO
        import sys
        captured_output = StringIO()
        sys.stdout = captured_output
        list_tasks()
        sys.stdout = sys.__stdout__
        assert captured_output.getvalue() == ""
    
    def test_list_single_task(self):
        """验收标准：输出格式为 <id>: <description> [<status>]"""
        add_task("Test list format")
        from io import StringIO
        import sys
        captured_output = StringIO()
        sys.stdout = captured_output
        list_tasks()
        sys.stdout = sys.__stdout__
        output = captured_output.getvalue().strip()
        assert output == "1: Test list format [pending]"
    
    def test_list_multiple_tasks(self):
        """验收标准：列出所有任务"""
        add_task("Task 1")
        add_task("Task 2")
        done_task(1)  # 先完成第一个任务
        from io import StringIO
        import sys
        captured_output = StringIO()
        sys.stdout = captured_output
        list_tasks()
        sys.stdout = sys.__stdout__
        output = captured_output.getvalue().strip()
        lines = output.split('\n')
        assert len(lines) == 2
        assert lines[0] == "1: Task 1 [done]"
        assert lines[1] == "2: Task 2 [pending]"

class TestDoneTask:
    def test_done_existing_task(self):
        """验收标准：根据task_id将任务状态更新为done"""
        add_task("Complete this")
        done_task(1)
        tasks = load_tasks()
        assert tasks[0]["status"] == "done"
    
    def test_done_nonexistent_task(self):
        """验收标准：ID不存在时输出错误消息"""
        from io import StringIO
        import sys
        captured_output = StringIO()
        sys.stdout = captured_output
        done_task(999)
        sys.stdout = sys.__stdout__
        error_msg = captured_output.getvalue().strip()
        assert "Error: Task with id 999 not found." in error_msg
    
    def test_done_does_not_affect_other_tasks(self):
        """边界：完成一个任务不应影响其他任务"""
        add_task("Task A")
        add_task("Task B")
        done_task(1)
        tasks = load_tasks()
        assert tasks[0]["status"] == "done"
        assert tasks[1]["status"] == "pending"

class TestDataPersistence:
    def test_data_persists_across_operations(self):
        """验收标准：应用在多次运行间保持数据持久化"""
        add_task("Persistent task 1")
        add_task("Persistent task 2")
        done_task(1)
        # 模拟重新加载（实际上就是直接读取文件）
        tasks = load_tasks()
        assert len(tasks) == 2
        assert tasks[0]["description"] == "Persistent task 1"
        assert tasks[0]["status"] == "done"
        assert tasks[1]["description"] == "Persistent task 2"
        assert tasks[1]["status"] == "pending"

class TestErrorHandling:
    def test_add_missing_description(self):
        """验收标准：add命令缺少描述时，输出用法错误信息"""
        # 通过main函数测试CLI错误处理
        from io import StringIO
        import sys
        import argparse
        captured_output = StringIO()
        sys.stderr = captured_output
        # 尝试以错误方式调用add
        try:
            from todo import main
            # 模拟命令行参数：只有add，没有description
            sys.argv = ['todo.py', 'add']
            main()
        except SystemExit:
            pass
        finally:
            sys.stderr = sys.__stderr__
        error_output = captured_output.getvalue()
        # argparse会输出用法信息
        assert "usage:" in error_output.lower() or "error:" in error_output.lower()