# 模块拆分
- `todo.py`: 单文件应用，包含三个主要模块职责：
  1. **数据存储**: 负责从 `todos.json` 文件加载待办事项列表，以及将列表保存回文件。
  2. **任务管理**: 包含待办事项的添加 (`add`)、列出 (`list`) 和标记完成 (`done`) 的核心业务逻辑。
  3. **命令行界面**: 使用 `argparse` 解析 `add`、`list`、`done` 子命令及其参数，并调用任务管理功能。
  - 测试要点：1) 文件读写正确性；2) 任务操作逻辑（ID自增、状态翻转）；3) 命令行参数解析及对应函数调用。

## 接口定义
- **数据结构**:
  `tasks`: `list[dict]`，每个字典包含键 `id` (int), `description` (str), `done` (bool)。
- **函数签名**（必须严格遵循，不得添加默认参数）:
  `load_tasks(filepath: Path) -> list[dict]`: 从指定JSON文件加载任务列表，文件不存在则返回空列表。
  `save_tasks(tasks: list[dict], filepath: Path) -> None`: 将任务列表保存到指定JSON文件。
  `add_task(tasks: list[dict], description: str) -> list[dict]`: 向列表追加新任务（ID自增），返回更新后的列表。
  `list_tasks(tasks: list[dict]) -> None`: 将任务列表格式化并打印到标准输出。
  `done_task(tasks: list[dict], task_id: int) -> list[dict]`: 根据ID查找任务并标记其 `done` 为 `True`，返回更新后的列表。若ID无效则提示错误。
  `main() -> None`: 应用入口，创建 `argparse.ArgumentParser`，定义子命令，解析参数并调度对应功能函数。
- **CLI 接口**:
  `python todo.py add <description>`
  `python todo.py list`
  `python todo.py done <id>`

## 依赖
- 无第三方依赖 (仅使用标准库: `json`, `argparse`, `pathlib`, `sys`)

## 预期文件清单
- source: todo.py  # 命令行应用主体，包含所有业务逻辑和CLI定义
- test: tests/test_core.py  # 测试数据存储与任务管理核心函数(load_tasks, save_tasks, add_task, done_task)
- test: tests/test_cli.py  # 测试命令行接口(add, list, done子命令的解析与调用)