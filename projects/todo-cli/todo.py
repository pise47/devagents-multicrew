import argparse
import json
import os
from typing import List, Dict, Any

TASKS_FILE = "todos.json"

def load_tasks() -> List[Dict[str, Any]]:
    """从 todos.json 读取任务列表，若文件不存在则返回空列表"""
    if not os.path.exists(TASKS_FILE):
        return []
    try:
        with open(TASKS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []

def save_tasks(tasks: List[Dict[str, Any]]) -> None:
    """将任务列表写入 todos.json"""
    with open(TASKS_FILE, "w", encoding="utf-8") as f:
        json.dump(tasks, f, ensure_ascii=False, indent=2)

def add_task(description: str) -> None:
    """添加新任务，自动生成递增ID，状态为 pending"""
    tasks = load_tasks()
    # 计算新ID：如果列表为空则为1，否则为最大ID+1
    next_id = max((task["id"] for task in tasks), default=0) + 1
    new_task = {
        "id": next_id,
        "description": description,
        "status": "pending"
    }
    tasks.append(new_task)
    save_tasks(tasks)

def list_tasks() -> None:
    """按格式 <id>: <description> [<status>] 打印所有任务"""
    tasks = load_tasks()
    for task in tasks:
        print(f"{task['id']}: {task['description']} [{task['status']}]")

def done_task(task_id: int) -> None:
    """根据 task_id 标记任务为 done，若 ID 不存在则打印错误"""
    tasks = load_tasks()
    for task in tasks:
        if task["id"] == task_id:
            task["status"] = "done"
            save_tasks(tasks)
            return None
    print(f"Error: Task with id {task_id} not found.")
    return None

def main() -> None:
    """程序入口，解析命令行参数并调用对应函数"""
    parser = argparse.ArgumentParser(description="命令行 Todo 应用")
    subparsers = parser.add_subparsers(dest="command", help="可用的命令")

    # add 子命令
    add_parser = subparsers.add_parser("add", help="添加新任务")
    add_parser.add_argument("description", help="任务描述")

    # list 子命令
    subparsers.add_parser("list", help="列出所有任务")

    # done 子命令
    done_parser = subparsers.add_parser("done", help="标记任务为已完成")
    done_parser.add_argument("task_id", type=int, help="任务ID")

    args = parser.parse_args()

    if args.command == "add":
        add_task(args.description)
    elif args.command == "list":
        list_tasks()
    elif args.command == "done":
        done_task(args.task_id)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()