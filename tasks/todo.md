# TODO — DevAgents（依据 tasks/plan.md）

> 勾选 = 完成且验收通过。★ = 人工 checkpoint。

## 任务 1: 骨架 + config ✅
- [x] `devagents/` 包 + `pyproject.toml` + `.gitignore`（venv/缓存/runs 产物）+ `__init__.py`
- [x] `config.py`: 读包根 `devagents.toml`（env `DEVAGENTS_CONFIG` 可覆盖）；缺文件自动从 `.example` 复制提示补配；[llm]/[roles]/[pipeline]/[prices]/[storage] 段默认值
- [x] 缺 key → `ConfigError` 含指引 + Token Plan 红线（测试钉死）
- [x] `devagents.toml.example`（占位符无真 key）+ `--version`/`--help` 可用（UTF-8 控制台修复）
- [x] config 单测 6 绿（默认值/覆盖/env 缺失/自动复制/坏 toml/未知段容忍/key_env 自定义）

## 任务 2: tests/ 基建 ✅
- [x] `conftest.py`: FakeLLM（按 model 弹脚本/抛异常，接口对齐 OpenAIClient）+ make_config（五阶段分派不同模型名）+ workspace 工厂
- [x] `samples.py` 信封产物库: 各角色合法输出 + 损坏信封 + 穿越样例
- [x] 基建随任务 3 套件首次跑绿（40 passed）自检通过

## 任务 3: llm + protocol + context ✅
- [x] `llm.py`: Chat Completions 直连 + usage/单价折算；错误四类 + transport 重试仅瞬时类；total_cost 单价缺失返回 None
- [x] `protocol.py`: 信封解析（块外忽略/反斜杠归一/未闭合报错）+ 路径白名单（.. 显式拒绝）
- [x] `context.py`: 快照忽略集（.venv/缓存/git）+ 单文件截断 + 总预算 + truncated 报告
- [x] 三模块单测绿（llm 12 / protocol 15 / context 7）

## 任务 4: prompts + roles + report ✅
- [x] `devagents/prompts/`: spec/arch/code/code_fix/test/review 六模板（含前端 smoke.json 契约、清单双段格式）
- [x] 模板含: 信封输出格式、不自行宣布结论禁条、review 阻断/建议分级、requirements.txt 强制、修复模式只重发改动文件
- [x] `roles.py`: 模板加载（缓存）+ 消息组装 + 模型映射（修复复用 code 模型）；不依赖 context/protocol
- [x] `report.py`: REPORT.md + report.json + 账单（单价缺失 → 只报 token + 提示）
- [x] 单测 21 绿

## 任务 5: runner + pipeline（核心）✅
- [x] `runner.py`: venv+pip install+pytest 执行器 / http.server 冒烟执行器；基础设施超时（300s）与测试执行超时分离；TIMEOUT/ERROR 判定
- [x] runner 真跑夹具 7 绿（通过/失败/超时/冒烟 200/缺文案/404/缺 smoke.json）
- [x] `pipeline.py`: 五阶段 + gate 全套（spec 四章节/arch 四要素+清单解析/code 缺文件与越界双查含豁免/review 分级解析）
- [x] 修复链统一循环: test 先于 review 双门、review 触发修复后重跑 test、越界 gate FAIL + 尝试前清理、修复轮内超时/API 失败 STOPPED 不耗计数
- [x] 终态矩阵表驱动（mock 全链 SUCCESS / FAILED 耗尽 / STOPPED 全触发路径）
- [x] 全套件 85 绿（mock 78 + 真子进程 7，41.5s）

## 任务 6: cli + README ✅
- [x] `cli.py`: run/report 接线，exit code=终态；build_llm/build_runner/run_task 可注入测试
- [x] 命令级测试 6 绿: mock 全链经真实 main() 跑通，SUCCESS/FAILED/STOPPED exit code 0/1/2 断言；缺 key 快速失败含红线
- [x] README.md 初稿: 架构图+用法+配置+边界+测试说明（复盘笔记留 demo 后补）
## ★ Checkpoint 1 ✅
- [x] mock 全链样例报告呈现用户（runs/20260905-162505），确认后进真 API

## 任务 7: Demo A（真 API）✅
- [x] `run "Python CLI Todo"` 全流程 **SUCCESS**（runs/20260905-163408, 510s, 9 调用 45k token, 按量 key）
- [x] 真实修复链闭环: review 抓阻断 → code_fix → test 重跑 PASS → 复审干净；gate 重试真实发生 2 次（test 1 次 + review 1 次）——零调优一次过，prompts 未改
- [x] 产物功能验证: add/list/done 手测全过；账单 + REPORT.md 完整于 projects/todo-cli

## 任务 8: Demo B（真 API）✅
- [x] `run "番茄钟单页"` 全流程 **SUCCESS**（runs/20260905-164137, 208s, 6 调用 15.6k token, **Token Plan 套餐端**）
- [x] 产物入 projects/pomodoro；冒烟 PASS（http.server + smoke.json 断言）
- [x] README 复盘笔记补 Demo B + 双轨对比 + anthropic 适配器实测结论（system 顶层字段 bug 教训）
- [x] 双轨对照: tp 端 208s/15.6k vs 按量 510s/45.5k——修复链未触发轮次更少

## ★ Checkpoint 2 ✅
- [x] 真 API 产物 + 账单复盘呈现用户；git 建仓（86067b8）+ 首次提交
- [x] 记忆更新：project-devagents.md + MEMORY.md 索引 + tool-configs 双轨实测 + decisions-log ToS 破例 + LanceDB 双写 + last-session 摘要
- [x] /review 五轴审查（code-reviewer 34 次工具调用实测复现）：1 Critical + 8 Important 全修复 + 24 条回归测试 → 128 全绿，提交 d4e9267
