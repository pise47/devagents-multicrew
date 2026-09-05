# 审查结果

## 阻断项
- 正确性: `save_tasks` 函数定义签名与 PLAN.md 接口定义不一致。PLAN.md 明确定义函数签名为 `save_tasks(tasks: list[dict], filepath: Path) -> None`，但 `todo.py` 中实现为 `save_tasks(tasks: list[dict], filepath: Path = DATA_FILE) -> None`，增加了默认参数。这导致当测试（如 `test_core.py`）按 PLAN 定义的签名调用 `save_tasks(tasks, temp_file)` 时，Python 解释器因参数计数不匹配而报错 `TypeError: save_tasks() takes 1 positional argument but 2 were given`，该错误在 TEST.md 第二次执行结果中明确出现。虽然第三次执行结果通过，但这表明存在不稳定的正确性问题。缺陷位于 `todo.py` 的 `save_tasks` 函数定义处。修复方案：移除 `filepath` 参数的默认值 `= DATA_FILE`，使其与 PLAN.md 接口定义完全一致。

## 建议项
- 可读性: `todo.py` 中函数 `load_tasks` 和 `save_tasks` 的 `filepath` 参数使用模块级常量 `DATA_FILE` 作为默认值，使函数签名隐式依赖全局状态，降低了可重用性。建议移除默认值，强制调用者（如 `main` 函数）显式传递 `DATA_FILE`。
- 正确性: `done_task` 函数在找不到指定 ID 的任务时，会打印错误信息但依然返回原列表。随后 `main` 函数会无条件调用 `save_tasks` 保存这个未修改的列表，导致不必要的文件重写（更新文件修改时间）。建议让 `done_task` 在无效 ID 时返回一个标识（如 `None`），让 `main` 函数根据返回值决定是否保存，或至少在 `done_task` 无效时跳过保存操作。