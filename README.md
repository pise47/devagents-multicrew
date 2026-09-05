# DevAgents — 多智能体代码开发系统

一条命令 + 一句需求 → 五个 LLM 角色 agent 接力协作，产出**可运行、可验证**的代码项目。

```bash
python -m devagents run "做一个 Python CLI Todo：add/list/done，JSON 存储" --out projects/todo-cli
```

## 它是什么

多智能体编排器的教学级实现（迷你 MetaGPT），也是个人提效工具。核心设计原则（SPEC.md §4.3）:

> **LLM 只产内容，一切 PASS/FAIL/终态由 pipeline 机械规则判定。** 角色 agent 永远不会"自说自话地宣布自己通过了"。

五角色串行流水线（镜像 agent-skills 流程 spec → plan → build → test → review）:

```
任务描述
  │
  ├─① spec-agent   需求 → SPEC.md（目标/功能/验收标准/文件布局）
  ├─② arch-agent   SPEC → PLAN.md（模块/接口/依赖/预期文件清单 source+test 双段）
  ├─③ code-agent   PLAN → 按清单写代码 + requirements.txt（不写测试）
  ├─④ test-agent   独立 QA: 从 SPEC 推导测试 → 写测试 → runner 真实执行
  │                   （结论由 pytest exit code 机械决定，与 LLM 文本无关）
  ├─⑤ review-agent 五轴审查 → REVIEW.md 分级清单（阻断项/建议项）
  │                   阻断项≥1 → pipeline 判 FAIL（机械规则）
  └─ 终报 → runs/<id>/: REPORT.md + report.json + token/费用账单
```

- **修复链**: code 修订 → 必先重跑 test（同一套测试）→ PASS 才放行 review 复审。双门皆过一轮才算完；上限 2 轮
- **终态三值**: `SUCCESS`(0) / `FAILED`(1) 业务未达成 / `STOPPED`(2) 基础设施中断（API 失败/超时/gate 耗尽），exit code 透传
- **产物 gate**: 每个阶段产出先过机械校验（SPEC 四章节、PLAN 四要素、文件清单逐文件核对、**越界新增源文件 FAIL**、REVIEW 分级可解析），失败本阶段重试 1 次
- **重试分层**: llm 瞬时错误（网络/5xx/429）transport 重试 1 次；内容问题（gate/解析）stage 重试 1 次；各自计数各自日志，互不叠加

## 支持的产出类型

| 类型 | 验证方式 |
|------|---------|
| Python 项目 | 工作区 `.venv` → `pip install -r requirements.txt pytest` → `python -m pytest -q`（真跑） |
| 单页前端（纯 HTML/CSS/JS） | test-agent 写 `smoke.json` 冒烟契约 → `http.server` + GET 200 + 关键文本断言（不依赖 node） |

## 快速开始

1. **API Key（必须按量 sk-key）**: `setx MIMO_API_KEY "sk-..."`（新开终端生效）
   - ⚠️ Token Plan key 仅限交互式使用，**自动化脚本禁止**（ToS 红线）
2. 首次运行自动从 `devagents.toml.example` 复制出 `devagents.toml`，按需编辑（模型/单价等；密钥不进文件）
3. 跑任务:

```bash
python -m devagents run "你的需求…" --out projects/xxx     # 全流程
python -m devagents report 20260905-162241                # 看某次运行（支持前缀）
```

## 配置（devagents.toml）

- `[llm]`: base_url（默认 MiMo 按量 `https://api.xiaomimimo.com/v1`）、key_env、timeout
- `[roles]`: 每角色模型——推理重角色 spec/arch/review 默认 `mimo-v2.5-pro`，量大角色 code/test 默认 `mimo-v2.5`（直连 API 用官方名，不带 `[1m]` 后缀）
- `[pipeline]`: 上下文预算（默认 60k tokens，主动低于模型窗口控成本）、修复环上限 2、gate/transport 重试各 1、runner 超时
- `[prices]`: 模型单价表（元/M tokens）——**空表 = 账单只报 token 不折算费用**，实测平台账单后填入

模型可换任意 OpenAI 兼容端点（换 base_url + key_env 即可）。

## 项目结构

```
devagents/
├─ cli.py        run/report 接线；exit code = 终态
├─ config.py     devagents.toml 加载（env DEVAGENTS_CONFIG 可覆盖）；缺 key 快速失败
├─ llm.py        OpenAI 兼容客户端：错误四类/瞬时重试/usage 与计费
├─ context.py    工作区快照 → 按预算裁剪（阶段间只传产物文件，不传对话历史）
├─ protocol.py   ```path= 信封解析 + 路径白名单（拒绝穿越/绝对路径/盘符）
├─ roles.py      角色定义 + prompts/ 模板加载 + 阶段↔模型映射
├─ pipeline.py   状态机：五阶段 + gate + 修复链 + 终态判定（核心）
├─ runner.py     执行器：venv+pytest / http.server 冒烟（白名单命令、工作区内、超时）
├─ report.py     REPORT.md + report.json + 账单
└─ prompts/      六个角色 prompt 模板（直接编辑即生效，调优不改代码）
```

## 测试

```bash
python -m pytest                 # 128 项：mock LLM 驱动的状态机矩阵 + 真子进程 runner（不触网用例为 mock 层）
python -m pytest -m smoke        # 真 API 冒烟（低频，需 MIMO_API_KEY）
```

单元层不触网：FakeLLM 按模型弹脚本、FakeRunner 脚本化判定，终态矩阵（SUCCESS/FAILED/STOPPED 全触发路径、修复轮内超时不耗计数）全部表驱动钉死。

## 边界（SPEC §8）

- **Always**: 只在 `--out` 内写文件；每阶段产物即时落盘；失败原文入报告，绝不静默；每次 run 打账单
- **Never**: key 硬编码/进日志/进 git；agent 输出驱动任意命令（执行器仅白名单）；路径逃逸；自动 git 操作；agent 联网（除 LLM API）
- git 仓库由本人手动管理（`git init` 后首次提交）

## 复盘笔记

### Demo A：Python CLI Todo（2026-09-05，真实 MiMo 按量 API）

`runs/20260905-163408` — **SUCCESS**，510s，9 次调用（输入 27k + 输出 18.5k token），零 prompts 调优。

- spec/arch/code 首轮全过 gate；test-agent 首次输出过 gate 失败（重试 1 次后过）→ 说明独立 QA 阶段的"写对文件"约束真在起作用
- runner 真跑 pytest PASS → review 抓到阻断项 → **修复链真实闭环**: code_fix → 同一套测试重跑 PASS → review 复审干净 → SUCCESS（修复轮 1/2）
- review 复审自身也经历一次结构 gate 重试（REVIEW.md 首版格式不合规 → 重发）——gate 防的是"格式漂移"，不只是内容
- 产物功能手测: `add/list/done` 全过（含递增 ID、JSON 持久化、损坏文件容错）
- 观察: 全流程 ~8.5 分钟，大头在 LLM 输出长文件（code_fix 单次输出 7.2k token）；按量端偶发慢

### Demo B：番茄钟单页（2026-09-05，MiMo Token Plan 套餐端）

`runs/20260905-164137` — **SUCCESS**，208s，6 次调用（输入 7.7k + 输出 7.8k token），修复轮 0/2，零调优。

- 首跑暴露适配器真 bug: Anthropic 协议 system 消息未提到顶层字段 → 模型丢角色提示自由发挥 → 两轮无信封 STOPPED。修复 + 单测钉死后重跑即过——**协议的坑要用真端点验证**（mock 测试只验证了消息形状，没验证协议语义）
- spec/arch/code/test/http.server 冒烟全部首轮过；仅 review 经历一次结构 gate 重试（REVIEW.md 格式 → 重发干净）
- 单页产出: index.html（arch 拆单文件方案，CSS/JS 内联）+ smoke.json（test-agent 从 SPEC 推导关键文案做断言）

#### 双轨实测对比

| 轨 | Demo A 按量(openai) | Demo B 套餐(anthropic) |
|----|----|----|
| 耗时 | 510s | 208s |
| 调用/token | 9 次 / 45.5k | 6 次 / 15.6k |
| 修复轮 | 1/2 | 0/2 |

结论: 套餐端（tp）当前更快更省 token；按量端作为可批量化/无套餐时的兜底轨保留。适配器实测要点见上表下方"双轨模型接入"。

## 双轨模型接入

| 协议 | 端点 | Key | 用途 |
|------|------|-----|------|
| `openai` | `api.xiaomimimo.com/v1` | 按量 `MIMO_API_KEY` | 默认/可批量化 |
| `anthropic` | `token-plan-cn.xiaomimimo.com/anthropic` | 套餐 `MIMO_TP_API_KEY` | 套餐 credits 消耗 |

实测（2026-09-05）: anthropic 端模型名**不带 [1m] 后缀**（带后缀 400 Unsupported model），响应原生含 thinking 块（适配器已跳过）。套餐 tp-key 官方 ToS 限交互式用途，自动化管线使用属用户自担风险的决定。
