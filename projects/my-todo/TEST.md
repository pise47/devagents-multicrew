# 测试设计与边界用例

## 测试文件说明
- tests/test_core.py: 核心业务函数单元测试（直接 import 被测函数）
- tests/test_cli.py: CLI 集成测试（通过 subprocess 调用真实命令行）

## SPEC 验收标准覆盖情况

### AC1: add 命令创建 todos.json 条目（自增 ID、给定描述、初始未完成状态）
- test_core: TestAddTask 全部 6 个用例（ID 自增、初始 done=False、空列表起始 ID=1、从 max+1 递增）
- test_cli: TestCLIAdd.test_add_creates_json_file（验证文件存在及内容结构）、test_add_then_list_shows_task、test_add_multiple_tasks_increments_id

### AC2: list 命令输出 ID、描述和状态（[未完成]/[已完成]）
- test_core: TestListTasks 全部 5 个用例（格式 [x]/[ ]、空列表提示、多任务逐行输出）
- test_cli: TestCLIList.test_list_displays_status_correctly（验证 [x] Task A / [ ] Task B）

### AC3: done 命令更新 todos.json 中对应 ID 的状态为完成
- test_core: TestDoneTask.test_done_task_valid_id
- test_cli: TestCLIDone.test_done_updates_json_file（验证 JSON 文件内容）、test_done_shows_in_list

### AC4: todos.json 不存在时自动创建并初始化为空列表
- test_core: TestLoadTasks.test_load_tasks_file_not_found
- test_cli: TestCLIPersistence.test_auto_create_json_on_first_run

### AC5: 不导入任何第三方模块
- test_cli: TestCLINoThirdPartyDeps.test_no_third_party_imports

## PLAN 接口定义验证
- TestFunctionSignatures: 验证全部 5 个函数的参数名与 PLAN.md 定义一致
- TestSaveTasks.test_save_tasks_signature_no_default: 验证 save_tasks 无默认参数（曾出现阻断缺陷）
- TestFunctionSignatures.test_no_extra_default_params: 批量验证所有函数参数无默认值

## 边界与风险用例
1. 文件不存在: TestLoadTasks.test_load_tasks_file_not_found
2. 无效 JSON 语法: TestLoadTasks.test_load_tasks_invalid_json_syntax
3. JSON 非列表类型: TestLoadTasks.test_load_tasks_not_a_list
4. 空列表操作: TestAddTask.test_add_task_to_empty_list、TestDoneTask.test_done_task_empty_list、TestListTasks.test_list_tasks_empty、TestSaveTasks.test_save_tasks_empty_list
5. 无效任务 ID: TestDoneTask.test_done_task_invalid_id、TestCLIDone.test_done_invalid_id
6. ID 跳跃后自增: TestAddTask.test_add_task_id_from_max（已有 ID=5 时新增应为 6）
7. 已完成任务重复标记: TestDoneTask.test_done_task_already_done
8. 函数返回同一列表对象: TestAddTask.test_add_task_returns_same_list_object、TestDoneTask.test_done_task_returns_same_list
9. 现有任务不被篡改: TestAddTask.test_add_task_preserves_existing

## 已知限制
- 未测试并发写入场景（单进程串行执行）
- 未进行大文件或性能压力测试
- CLI 测试通过 subprocess 真实执行，不 mock 被测对象主逻辑（符合测试策略要求）
- 未直接测试 main() 无参数时 sys.exit(1) 行为（属于 CLI 错误处理扩展点）

## 执行结果（机械写入，非 LLM 结论）

- verdict: PASS
- exit_code: 0
- 耗时: 2.2s
- 轮次: 当前为最新一次执行
```
...........................................                              [100%]
43 passed in 1.87s

```
