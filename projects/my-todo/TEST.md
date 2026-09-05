# 测试设计与边界用例

## 测试覆盖的验收标准
1. **添加后列表可见**: `TestCLIAdd.test_add_then_list_shows_task` 验证添加任务后通过list命令能看到该任务。
2. **正确显示ID、描述、状态**: `TestCLIList.test_list_displays_status_correctly` 和 `TestCore.TestListTasks.test_list_tasks_format` 验证输出格式符合规范（[x]/[ ]、ID、描述）。
3. **标记完成状态更新**: `TestCLIDone.test_done_updates_status_and_file` 和 `TestCore.TestDoneTask.test_done_task_valid_id` 验证done操作后done字段变为True。
4. **生成/更新JSON文件**: `TestCLIAdd.test_add_creates_json_file` 和 `TestCore.TestSaveTasks` 系列测试验证文件创建与内容正确性。
5. **重启后数据加载**: `TestCLIPersistence.test_persistence_across_invocations` 模拟两次运行验证持久化。
6. **无第三方依赖**: `TestCLINoThirdPartyDeps.test_no_imports_in_source` 检查源代码导入语句。

## 边界与风险点测试
- **文件不存在**: `TestCore.TestLoadTasks.test_load_tasks_file_not_found` 验证load_tasks返回空列表。
- **无效JSON/非列表文件**: `TestCore.TestLoadTasks.test_invalid_json` 和 `test_not_a_list` 覆盖损坏或格式错误的数据文件。
- **空列表操作**: `TestCore.TestAddTask.test_add_task_empty_list` 和 `TestCore.TestListTasks.test_list_tasks_empty` 验证无任务时的行为。
- **无效任务ID**: `TestCore.TestDoneTask.test_done_task_invalid_id` 和 `TestCLIDone.test_done_invalid_id` 验证错误提示且数据不变。
- **ID自增逻辑**: `TestCore.TestAddTask.test_add_task_increments_id` 验证多次添加后ID递增正确。
- **命令行错误处理**: 通过subprocess测试真实命令行调用，包括无命令参数时的行为（未直接测试，但main函数中有`sys.exit(1)`逻辑，可作为未来扩展点）。
- **并发/文件锁定**: 当前测试为单进程串行，未覆盖并发写入场景，属于已知限制。
- **大文件/性能**: 未进行压力测试，对于小规模待办事项列表（典型用例）风险较低。

## 执行结果（机械写入，非 LLM 结论）

- verdict: PASS
- exit_code: 0
- 耗时: 12.4s
```
.....................                                                    [100%]
21 passed in 2.10s

```


## 执行结果（机械写入，非 LLM 结论）

- verdict: FAIL
- exit_code: 1
- 耗时: 1.7s
```
............FF.......                                                    [100%]
================================== FAILURES ===================================
_________________ TestSaveTasks.test_save_tasks_creates_file __________________

self = <test_core.TestSaveTasks object at 0x000001F062453B10>
temp_file = WindowsPath('C:/Users/pise/AppData/Local/Temp/pytest-of-pise/pytest-44/test_save_tasks_creates_file0/test_tasks.json')

    def test_save_tasks_creates_file(self, temp_file):
        """SPEC: 应生成或更新一个JSON文件。"""
        tasks = [{"id": 1, "description": "Task", "done": False}]
>       save_tasks(tasks, temp_file)
E       TypeError: save_tasks() takes 1 positional argument but 2 were given

tests\test_core.py:38: TypeError
_________________ TestSaveTasks.test_save_task
```


## 执行结果（机械写入，非 LLM 结论）

- verdict: PASS
- exit_code: 0
- 耗时: 1.6s
```
.....................                                                    [100%]
21 passed in 1.30s

```
