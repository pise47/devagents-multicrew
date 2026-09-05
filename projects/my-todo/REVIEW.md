# 审查结果

## 阻断项
（无）

## 建议项
- 正确性: `main()` 中 `done` 子命令分支会无条件调用 `save_tasks`，即使 `done_task` 因无效 ID 未做任何修改。当 `todos.json` 不存在时，执行 `python todo.py done 999` 会创建一个空的 `todos.json` 文件，与用户意图不符。建议让 `done_task` 返回一个可区分的标识（如 `None`）或由 `main` 比较前后列表来决定是否保存。
- 可读性: `todo.py` 中模块级常量 `DATA_FILE = Path("todos.json")` 仅在 `main()` 中使用，但暴露在模块顶层，与纯函数 `load_tasks`/`save_tasks` 的设计风格不统一。建议将 `DATA_FILE` 移入 `main()` 函数体内作为局部变量，使核心函数保持无全局状态依赖。