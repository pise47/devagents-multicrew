# 目标
开发一个命令行 Todo 应用，支持添加、列出和标记完成任务，并通过 JSON 文件持久化存储，使用纯 Python 标准库实现。

## 功能
- 使用 `add` 子命令添加新的 Todo 项，需要提供任务描述。
- 使用 `list` 子命令列出所有 Todo 项，显示 ID、描述和完成状态。
- 使用 `done` 子命令通过指定 ID 标记 Todo 项为完成。
- Todo 数据持久化到 JSON 文件，默认文件名为 `todos.json`。
- 应用纯使用 Python 标准库，无任何第三方依赖。

## 验收标准
- 运行 `python todo.py add "描述"` 后，`todos.json` 文件中应新增一个条目，包含自增 ID、给定描述和初始未完成状态。
- 运行 `python todo.py list` 后，标准输出应列出所有 Todo 项，格式为每行显示 ID、描述和状态（如 `[未完成]` 或 `[已完成]`）。
- 运行 `python todo.py done <ID>` 后，`todos.json` 文件中对应 ID 的项状态应变为完成。
- 如果 `todos.json` 文件不存在，应用首次运行时应自动创建并初始化为空列表。
- 应用代码中不导入任何第三方模块，仅使用 `argparse`、`json` 等标准库模块。

## 文件布局
- 项目类型：Python 项目。
- 主要文件：`todo.py`，单文件 CLI 应用。
- 运行时生成：`todos.json`，用于存储 Todo 数据。
- 使用标准库 `argparse` 解析命令行参数，`json` 模块处理 JSON 文件读写。