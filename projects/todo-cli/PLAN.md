# 模块拆分
- **命令行解析模块 (todo.py)**：负责使用 `argparse` 定义 `add`、`list`、`done` 三个子命令，并处理相应参数。
- **任务管理模块 (todo.py)**：负责核心逻辑，包括任务数据的读取（从 `todos.json`）、写入（到 `todos.json`）、添加新任务、列出任务、标记任务完成。

## 接口定义
- **数据结构**：任务以字典表示，格式为 `{"id": int, "description": str, "status": str}`，其中 `status` 取值为 `"pending"` 或 `"done"`。任务列表为包含此类字典的列表。
- **函数签名**:
  - `load_tasks() -> list[dict]`：从 `todos.json` 读取并返回任务列表；若文件不存在则返回空列表。
  - `save_tasks(tasks: list[dict]) -> None`：将任务列表写入 `todos.json` 文件。
  - `add_task(description: str) -> None`：向任务列表中添加一个新任务，自动生成唯一递增 ID，状态为 `"pending"`，并保存。
  - `list_tasks() -> None`：读取任务列表，并按要求格式（`<id>: <description> [<status>]`）逐行打印。
  - `done_task(task_id: int) -> None`：根据 `task_id` 查找任务并将其状态更新为 `"done"`，若 ID 不存在则打印错误消息。
  - `main() -> None`：程序入口，解析命令行参数并调用对应函数。

## 依赖
- 无第三方依赖（仅使用标准库 `argparse` 和 `json` 模块）。

## 预期文件清单
- source: todo.py  # 应用主文件，包含命令行接口和核心任务管理逻辑
- test: tests/test_todo.py  # 测试文件，验证添加、列出、完成任务功能及错误处理