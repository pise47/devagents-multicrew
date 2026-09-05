# PLAN — DevAgents 实现计划

> 依据: SPEC.md v2 终稿 · 2026-09-05 · 方法: 每任务内先测试后实现（TDD 切片），全自动流水线 + 2 个人工 checkpoint

## 1. 依赖图与切片策略

```
config ─┬→ llm ─────────┐
        ├→ runner ──────┤→ pipeline → report → cli
protocol ───────────────┤
context ────────────────┘
roles（仅依赖 prompts/ 模板，不依赖 context——由 pipeline 编排两者输出，防模块耦合）
```

- 叶子模块（config/llm/protocol/context/runner）彼此独立但 pipeline 依赖全部 → 先逐个做叶子（每个带完整单测），**垂直切片在第 5/6 任务才闭合**（mock 全链 → cli 命令）
- prompts 模板质量 = 全系统最大不确定项（真 API 效果全靠它）→ 安排真 API demo 调优轮次，不属于 mock 可验证范围
- runner 的真实子进程行为（venv/pytest/http.server）独立于 LLM 可先行真测（用夹具项目，秒级）

## 2. 任务清单（详见 tasks/todo.md）

| # | 任务 | 验收要点 | 依赖 |
|---|------|---------|------|
| 1 | 项目骨架 + config + toml.example + pyproject + .gitignore | `python -m devagents` 出 help；缺 MIMO_API_KEY → 快速失败指引（带测试）；env `DEVAGENTS_CONFIG` 可指测试配置 | — |
| 2 | tests/ 基建: mock LLM 信封夹具 + workspace 工厂 | 夹具能吐出各角色信封产物/损坏信封/路径穿越；workspace 工厂快速造 SPEC/PLAN 文件 | 1 |
| 3 | llm.py + protocol.py + context.py + 各自单测 | 账单累加数学对；错误分类（网络/HTTP/解析）可测；信封解析含穿越注入拒绝；上下文按角色白名单+预算截断 | 1,2 |
| 4 | prompts/ 五模板 + roles.py + report.py + 单测 | 模板含信封格式/判定权禁条/阻断分级说明；修复模式输入组装对；REPORT.md+report.json 终态渲染对 | 1,2 |
| 5 | runner.py + pipeline.py + 表驱动测试 | **核心**。runner 真跑夹具项目（pytest PASS/FAIL/超时、http.server 冒烟）；pipeline: 五阶段全链 SUCCESS、gate 重试耗尽 STOPPED、test FAIL→修复→PASS、review 阻断→修复→重测→复审、修复环耗尽 FAILED、修复轮内超时→STOPPED 不耗计数、PLAN 越界新增源文件 FAIL（豁免 `__pycache__`/`.pytest_cache`/`coverage.xml`/`htmlcov`/`.venv` 等环境与缓存产物） | 3,4 |
| 6 | cli.py 接线 + 命令级测试 + README 初稿 | `run`/`report` 子命令 exit code = 终态（0/1/2）；mock 全链经 cli 跑通；README 架构图 | 5 |
| ★ | **Checkpoint 1**（mock 全链绿后）: 呈现样例运行报告给用户过目 | 用户确认后再花真钱跑 API。⚠️ Checkpoint 是**开发流程**人工门，不属于 DevAgents runtime 状态机（runtime 全自动无人工门，两者不冲突） | 6 |
| 7 | Demo A 真 API: Todo CLI | SPEC §9 demo A 全过；调优轮定义 = Demo 未 SUCCESS → 改 prompts/ → **重新运行完整 demo**（非重跑失败阶段），≤3 轮超限停下报问题 | 6 |
| 8 | Demo B 真 API: 番茄钟单页 | SPEC §9 demo B 全过；两次 demo 费用账单入报告 | 7 |
| ★ | **Checkpoint 2**: 真 API 产物 + 账单复盘给用户过目；随后 git 建仓提示、memory 记录（⚠️ 属**开发者侧收尾动作**，非 DevAgents 功能验收项） | — | 8 |

### 重试分层（两机制互不混淆，各自计数各自日志）
| 机制 | 触发 | 次数 | 耗尽后 |
|------|------|------|--------|
| transport 重试（llm.py 内） | 瞬时类: `NetworkError` / HTTP 5xx / 429 | 1 | STOPPED——stage 不因 API 失败重试 |
| stage 重试（pipeline gate） | 内容问题: 产物 gate 失败 / 信封解析失败 | 1 | STOPPED |

- 错误类型四类: `NetworkError`/`HTTPError`/`InvalidResponse`/`ProtocolError`，瞬时判定机械化
- 日志分别标记 `transport_retry`/`stage_retry`；最坏线上调用 2 次/阶段，不叠加成 4

## 3. 风险与对策

| 风险 | 对策 |
|------|------|
| prompts 质量不足 → demo 跑不通 | Demo 任务内置调优轮次（≤3）；调优只改 prompts/ 不动代码 |
| MiMo 直连稳定性（超时/长响应截断） | llm.py 错误分类 + 重试 1 次（仅限瞬时类错误）；prompt 限制输出规模；账单可见 |
| Windows 子进程/venv 路径坑 | runner 用 `sys.executable -m venv`、路径全用绝对化 + 引号；runner 单测在任务 5 先真跑夹具 |
| 信封格式偶发解析失败 | 重试 1 次机制 + 解析错误原文入报告（STOPPED 可回溯） |

## 4. 完成定义（本计划整体）

tasks/todo.md 全勾 + SPEC §9 验收 1-6 全过 + 两次人工 checkpoint 已确认。
