import json
import argparse
import sys
from pathlib import Path

DATA_FILE = Path("todos.json")


def load_tasks(filepath: Path = DATA_FILE) -> list[dict]:
    """从指定JSON文件加载任务列表，文件不存在则返回空列表。"""
    if not filepath.exists():
        return []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            return []
        return data
    except (json.JSONDecodeError, IOError):
        return []


def save_tasks(tasks: list[dict], filepath: Path = DATA_FILE) -> None:
    """将任务列表保存到指定JSON文件。"""
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(tasks, f, ensure_ascii=False, indent=2)


def add_task(tasks: list[dict], description: str) -> list[dict]:
    """向列表追加新任务（ID自增），返回更新后的列表。"""
    if tasks:
        next_id = max(t["id"] for t in tasks) + 1
    else:
        next_id = 1
    tasks.append({
        "id": next_id,
        "description": description,
        "done": False,
    })
    return tasks


def list_tasks(tasks: list[dict]) -> None:
    """将任务列表格式化并打印到标准输出。"""
    if not tasks:
        print("No tasks found.")
        return
    for task in tasks:
        status = "[x]" if task["done"] else "[ ]"
        print(f'{task["id"]} {status} {task["description"]}')


def done_task(tasks: list[dict], task_id: int) -> list[dict]:
    """根据ID查找任务并标记其done为True，返回更新后的列表。若ID无效则提示错误。"""
    for task in tasks:
        if task["id"] == task_id:
            task["done"] = True
            return tasks
    print(f"Error: Task with id {task_id} not found.")
    return tasks


def main() -> None:
    """应用入口，创建argparse.ArgumentParser，定义子命令，解析参数并调度对应功能函数。"""
    parser = argparse.ArgumentParser(description="Todo list manager")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    add_parser = subparsers.add_parser("add", help="Add a new task")
    add_parser.add_argument("description", type=str, help="Task description")

    subparsers.add_parser("list", help="List all tasks")

    done_parser = subparsers.add_parser("done", help="Mark a task as done")
    done_parser.add_argument("id", type=int, help="Task ID to mark as done")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    tasks = load_tasks()

    if args.command == "add":
        tasks = add_task(tasks, args.description)
        save_tasks(tasks)
    elif args.command == "list":
        list_tasks(tasks)
    elif args.command == "done":
        tasks = done_task(tasks, args.id)
        save_tasks(tasks)


if __name__ == "__main__":
    main()