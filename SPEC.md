# SPEC — DevAgents 多智能体代码开发系统

> 状态: v2 终稿 · 2026-09-05 · 目录: E:\devagents
> v2 终稿修订: 版本标记统一（文档内不再出现 v1/v2 分版）、requirements.txt 钉死为唯一安装依据（pyproject 仅可选）、PLAN 清单完全一致性、修复轮内 STOPPED 优先级
> v2 修订（评审第二轮）: 修复链线性化(test 先于 review 双门)、修复模式输入定义、PLAN 强制文件清单、结论判定权归 pipeline、review 阻断/建议分级、终态 SUCCESS/FAILED/STOPPED
> v1 修订（评审第一轮）: test-agent 定档独立 QA、前端冒烟去问号、prompts 入包、阶段间只传产物文件、config 命名统一、产物 gate、修复轮显式定义
> **核心哲学: LLM 只产内容（文档/代码/清单），一切 PASS/FAIL/终态由 pipeline 机械规则判定，LLM 不得自行宣布通过**

## 1. 目标与用户

**一句话**: 一条命令 + 一句需求 → 多个 LLM 角色 agent 接力协作，产出可运行、可验证的代码项目。

**用途（双重）**:
- **自用提效**: "写一个 XX 小项目"变成单命令，AI 流水线自动产出（规格→架构→编码→测试→审查），失败点清晰可回溯
- **学习研究**: 亲手实现 agent 编排、角色分工、判定权与内容权分离、token 成本可观测——考研复试可讲的项目

**参照**: MetaGPT 的简化单机版；本版只做五角色串行流水线。

**非目标（本版明确不做）**: 角色并行、网页 UI、联网检索、tool-calling 循环、node/前端测试框架、非 Python/单页的语言、大型仓库级项目

## 2. 核心流程与修复链

```
run "<自然语言任务>" --out <工作区>
  │  每阶段产物先过【gate 机械校验】，失败→本阶段重试1次→仍失败→STOPPED
  ├─ ① spec-agent   需求 → SPEC.md（目标/功能/验收标准/文件布局）
  ├─ ② arch-agent   SPEC → PLAN.md（模块拆分/接口/依赖/【预期文件清单】/测试要点）
  ├─ ③ code-agent   SPEC+PLAN → 按清单写全部代码文件 + requirements.txt（强制，唯一安装依据）
  │       ⚠️ 不写测试代码（职责归 test-agent，防自测盲区）；不得新增 PLAN 未声明源文件
  ├─ ④ test-agent   独立 QA: SPEC+PLAN+代码树 → 设计并写测试 → runner 执行
  │       → TEST.md（结论由 runner exit code 机械写入，LLM 文本仅作缺陷定位）
  │       └─ FAIL → 修复链（见下）
  ├─ ⑤ review-agent 五轴审查 → REVIEW.md（阻断项/建议项分级清单，无自宣结论）
  │       └─ 阻断项≥1（pipeline 判定）→ 修复链（见下）
  └─ ⑥ 终报 → runs/<run-id>/: REPORT.md + report.json（终态见 §4.4）+ 账单
```

**修复链（线性，test 永远先于 review）**:
```
缺陷反馈（TEST.md FAIL 或 REVIEW.md 阻断项）
  → code-agent 修复模式: 输入 = SPEC + PLAN + 当前代码树 + 最新缺陷报告
  → 重跑 test（必过）  → PASS 才放行 review 复审（必过）
  → 双门皆过 = 本轮完成；任一门 FAIL = 计数+1 进下一轮（上限 2）
```
- review 触发修复后**同样重跑 test**——修复统一走"修订 → test → review"链路，无需 review→test 特殊通道
- 修复环耗尽仍 FAIL → 终止，FAILED 终报
- **修复轮内基础设施中断（runner 超时/API 失败）优先级高于 FAIL 判定** → 一律 STOPPED，不消耗修复轮计数、不进 FAILED

**停止规则（全自动，无人工门）**: API 失败 → STOPPED（错误原文入日志，不静默）；gate 重试 1 次仍失败 → STOPPED；修复环耗尽仍 FAIL → FAILED。

## 3. 角色与上下文设计

| 角色 | 输入（只读工作区文件） | 产出 |
|------|------------------------|------|
| spec-agent | 用户任务原文 | `SPEC.md` |
| arch-agent | SPEC.md | `PLAN.md` |
| code-agent | SPEC.md + PLAN.md | PLAN 清单内代码文件 + 依赖清单 |
| test-agent | SPEC.md + PLAN.md + 代码树 | 测试代码 + `TEST.md`（结论 pipeline 覆写） |
| review-agent | SPEC.md + PLAN.md + 代码树 + TEST.md | `REVIEW.md`（分级清单，无结论） |

**PLAN.md 契约（四要素，gate 强制）**: 模块拆分 + 接口定义 + 依赖清单 + **预期文件清单**（路径+职责，gate 逐文件核对基准）。测试要点并入模块拆分说明。

**文件清单一致性规则**: 清单分两段——`source`（code-agent 负责写全）+ `test`（test-agent 负责写全）；code gate 对 source 段**缺文件 FAIL、擅自新增未声明源文件也 FAIL**；豁免（不计入核对）: venv/`__pycache__`/pytest 缓存/测试运行生成物等环境与缓存产物。

**上下文交接原则（context.py）**:
- 阶段间**只传上游产物文件**，**不传任何对话历史**——token 不随阶段膨胀
- 按角色白名单加载；超大文件截断（每文件 token 上限 + 目录清单，超限提示）
- 总上下文预算默认 60k tokens（低于模型窗口，主动控成本），config 可调

**LLM 接入（llm.py，OpenAI 兼容）**:
- OpenAI Chat Completions 非流式，requests 直连
- **默认模型**（MiMo 按量）: 推理重角色（spec/arch/review）→ `mimo-v2.5-pro`；量大型（code/test）→ `mimo-v2.5`；⚠️ 官方名**不带 [1m] 后缀**
- **Key**: 仅环境变量 `MIMO_API_KEY`（按量 sk-key）。红线: Token Plan key 禁用于自动化脚本（ToS）→ 缺 key 快速失败给指引
- **计费**: 每次调用记 usage 逐角色累计，单价配置维护，终报打印消耗 token + 估算费用

**输出协议（protocol.py）**: 信封格式 ```` ```path=<工作区内相对路径> ```` + 全文 `````；解析失败 → 本阶段重试 1 次 → STOPPED；路径白名单（拒绝绝对路径/`..`/盘符/越界，计入失败）。

## 4. 状态机（pipeline.py）

### 4.1 产物校验 gate（机械校验，每阶段后）
| 阶段 | gate 检查 |
|------|-----------|
| spec | SPEC.md 含 目标/功能/验收标准/文件布局 四章节 |
| arch | PLAN.md 含 模块拆分/接口/依赖/预期文件清单 四要素 |
| code | PLAN source 段**逐文件核对**全落盘于 --out + 依赖清单存在 + 无清单外新增源文件（§3 豁免除外） |
| test | TEST.md 存在且结论可读（结论由 runner 写入，§4.3） |
| review | REVIEW.md 含 阻断项/建议项 清单且格式可解析 |

### 4.2 修复环
- 定义、触发、链路见 §2「修复链」；计数器跨 test/review 共用，上限 2
- 每轮修复后 test gate 必须先 PASS 才允许 review 复审；code-agent 修复模式输入固定为 SPEC+PLAN+代码树+最新缺陷报告

### 4.3 判定权分离（本系统关键规则）
| 判定 | 归属 | 依据 |
|------|------|------|
| test 的 PASS/FAIL | **pipeline + runner** | pytest exit code / 冒烟 GET 结果，机械写入 TEST.md 结论段；LLM 输出与此冲突时以 runner 为准 |
| review 的 PASS/FAIL | **pipeline** | REVIEW.md 阻断项列表**非空 → FAIL**（机械规则），LLM 不自宣 |
| 阶段是否通过 | **pipeline** | gate 清单校验 |
| 修复是否需要 | **pipeline** | 上述判定结果 |
| spec/plan 质量 | LLM（无自动判据，靠下游 gate 兜底） | — |

review 分级约定（写入 roles.py prompt）: **阻断项** = 正确性错误/验收标准不满足/安全硬伤/架构不可行；**建议项** = 风格/可读性/性能优化——建议项永不 FAIL。

### 4.4 终态（统一三值，全量落 report）
| 终态 | exit code | 含义 | 触发 |
|------|-----------|------|------|
| `SUCCESS` | 0 | 全部 gate 过 + test PASS + 无阻断项，修复环内完成 | 正常走完 |
| `FAILED` | 1 | 业务未达成 | test FAIL 或阻断项存在，且修复环耗尽 |
| `STOPPED` | 2 | 基础设施中断 | API 失败 / gate 重试耗尽 / runner 超时 / 缺 key / 解析失败 |

产物: `runs/<run-id>/REPORT.md`（人读：各阶段产物+结论+阻塞项+账单）+ `report.json`（机读：终态/阶段明细/耗时/token/费用，脚本可消费）。CLI 以 exit code 透传终态。

## 5. 项目结构

```
E:\devagents\
├─ SPEC.md / README.md       元规格 / 用法+架构图+复盘笔记（复试可讲）
├─ pyproject.toml            包定义（Python ≥3.10，唯一运行时依赖 requests）
├─ devagents.toml            运行时配置（包根旁固定位置；缺 → 首跑自动从 example 复制并提示补配）
├─ devagents.toml.example    示例配置（占位符，无真 key）
├─ devagents\
│  ├─ __init__.py / cli.py   (argparse: run/report；exit code=终态)
│  ├─ config.py              读 devagents.toml + 环境变量；缺 key 快速失败
│  ├─ llm.py                 OpenAI 兼容客户端 + usage 累计 + 计费
│  ├─ context.py             文件树 → 角色白名单裁剪 + 截断 + 总预算（§3）
│  ├─ protocol.py            信封解析 + 路径白名单
│  ├─ roles.py               角色定义 + system prompt 模板（引用包内 prompts/）
│  ├─ pipeline.py            阶段状态机 + gate + 修复链 + 终态判定（§4）
│  ├─ runner.py              执行器: venv+pip install+pytest(--cov) / http.server 冒烟
│  │                         子进程超时，白名单命令，仅工作区内
│  ├─ report.py              REPORT.md + report.json + 账单
│  └─ prompts\               包内 prompt 模板（__file__ 相对路径读取，改文件即生效）
├─ tests\                    单测（mock LLM，无网络）+ smoke 标记 e2e
└─ projects\                 demo 工作区（todo-cli、番茄钟单页…）
```

**开发运行约定**: 项目根 `python -m devagents` / `python -m pytest tests/`（`-m` 自动 cwd 入 sys.path）；`pip install -e .` 可选（README 写明）。

## 6. 代码风格

- Python ≥3.10；标准库优先，运行时依赖仅 `requests`；测试 `pytest` + `pytest-cov`
- 类型标注、模块单职责、函数短、注释中文简洁
- 不流式；日志 = 控制台实时进度 + `runs/<run-id>/` 全量落盘（各阶段 prompt/response 摘要，复盘用）
- key 只走环境变量；禁硬编码/进日志/进 git

## 7. 测试策略（本系统自身）

| 层 | 手段 |
|----|------|
| 单元 | mock LLM 夹具: 五阶段产物落盘、gate 触发与重试、**修复链全路径表驱动**（含"review 触发修复→test 重跑"路径）、**终态判定表驱动**（SUCCESS/FAILED/STOPPED 全触发矩阵）、解析器（损坏信封/路径穿越）、账单累加、runner 超时、缺 key |
| 冒烟(e2e) | `pytest -m smoke`: 真 MiMo API 跑 demo（§9），低频标 slow |

**产出项目验证（runner.py，确定性，无 node）**:
- Python: 工作区 venv → `pip install -r requirements.txt` → `python -m pytest --cov`（覆盖率报告，本版不设门槛）
- 单页前端: `python -m http.server` → requests 检查 GET 200 + SPEC 关键元素 → 关闭；JS 语法由浏览器解析兜底（局限本版接受，node 检查留后续版本）

## 8. 边界

**Always**: 只在 `--out` 内写文件；每阶段产物即时落盘；失败原文可见入报告不静默；每次 run 打 token + 费用账单。

**Ask first**: 运行时全自动无人门；report/重跑子命令天然可介入；git 由本人手动建仓提交，系统只提示不自动执行。

**Never**
- key 硬编码/泄露
- agent 输出驱动任意命令——执行器仅白名单: venv pip install / pytest / http.server，工作区内 + 超时
- 路径逃逸（`..`/绝对路径/盘符）——协议层拒绝计失败
- 自动 git；agent 联网（除 LLM API）
- code-agent 写测试代码；LLM 自行宣布 PASS/FAIL/终态

## 9. 验收标准

1. `tests/` 全绿（mock 驱动无网络）
2. **demo A**: `run "Python CLI Todo：add/list/done、JSON 持久化"` → code 按 PLAN 清单落盘；test-agent 独立写测试；venv 装依赖 pytest 真跑通过
3. **demo B**: `run "番茄钟单页：25min 倒计时、开始/暂停/重置、纯 HTML/CSS/JS"` → http.server 冒烟通过
4. 每次 run 有 REPORT.md + report.json + 费用账单
5. gate、修复链、终态矩阵、路径逃逸、缺 key——测试钉死
6. README 可读: 架构图 + 一次运行复盘笔记

## 10. 已决策记录

- Python 依赖装工作区 venv，不碰系统 Python；前端验证不依赖 node
- test-agent = 独立 QA（自写测试从 SPEC/PLAN 推导预期），code-agent 不产测试
- 判定权归 pipeline（§4.3）；修复链 test 先于 review 双门（§2）；修复环上限 2；gate 重试 1 次
- 终态 SUCCESS/FAILED/STOPPED（§4.4）随 exit code 透传
- git 本人手动建仓；config 文件仅有占位符
- 产出项目安装依据唯一 = requirements.txt（pyproject 仅确有打包需求时附带，runner 一律不读）
- PLAN 文件清单 = source + test 两段，越界新增源文件 FAIL，环境/缓存产物豁免
- 修复轮内 runner 超时等基础设施中断 = STOPPED，不消耗修复计数（§2）
