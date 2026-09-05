# 目标
开发一个 Python 命令行 Todo 应用，支持通过 `add`、`list`、`done` 子命令管理任务，使用 JSON 文件进行数据持久化，完全基于 Python 标准库实现，无第三方依赖。

## 功能
- `add` 子命令：添加新任务，任务描述为必需参数，自动生成唯一递增 ID，默认状态为待完成。
- `list` 子命令：列出所有任务，显示任务 ID、描述和状态（待完成或已完成）。
- `done` 子命令：根据任务 ID 将指定任务标记为已完成。
- 数据持久化：任务数据存储在 JSON 文件中，文件路径默认为当前目录下的 `todos.json`。
- 纯标准库实现：仅使用 Python 标准库模块（如 `argparse` 和 `json`），无外部依赖。

## 验收标准
- 执行 `python todo.py add "Buy groceries"` 后，`todos.json` 文件包含新任务，ID 为 1，描述为 "Buy groceries"，状态为 "pending"。
- 执行 `python todo.py list` 时，输出格式为每行一个任务，如 `1: Buy groceries [pending]`，列出所有任务。
- 执行 `python todo.py done 1` 后，`todos.json` 中 ID 为 1 的任务状态更新为 "done"。
- 错误处理：`add` 命令缺少描述时，输出用法错误信息；`done` 命令指定不存在的 ID 时，输出错误消息。
- 应用不导入任何非标准库模块，可通过检查导入语句验证。
- 应用在多次运行间保持数据持久化，任务不会丢失。

## 文件布局
- 项目类型：Python 项目
- 主要文件：`todo.py`，包含命令行接口和核心逻辑。
- 数据文件：`todos.json`，由应用自动创建和管理，存储任务数据。
- 无其他文件，纯标准库实现，无需构建步骤。