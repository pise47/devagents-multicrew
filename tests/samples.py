"""信封/文档内容样例库: 各角色合法输出 + 损坏输入 + 路径穿越注入。

信封协议（protocol.py 契约）:
    ```path=<工作区内相对路径>
    <内容全文>
    ```
响应可有多个块；块外文本忽略。内容不得包含 ```（v1 局限，prompts 已明示）。
"""

# ---- 合法文档 ----

SPEC_OK = """\
# 目标
一个命令行 Todo 应用。

## 功能
- add <标题>: 新增待办
- list: 列出全部
- done <id>: 标记完成
- JSON 文件持久化

## 验收标准
- 上述四条命令可用
- 数据重启不丢

## 文件布局
- todo.py 主程序
- 依赖: 无（标准库）
"""

PLAN_OK = """\
# 模块拆分
- todo.py: 单文件 CLI，命令分发 add/list/done
- 数据格式: JSON 数组

## 接口定义
- add(title: str) / list() / done(i: int)
- 文件操作封装 load()/save()

## 依赖
- 标准库 argparse/json/pathlib，无第三方

## 预期文件清单
- source: todo.py
- test: test_todo.py
"""

CODE_OK = """\
```path=todo.py
import json
import sys
from pathlib import Path

DB = Path("todos.json")

def load():
    return json.loads(DB.read_text(encoding="utf-8")) if DB.exists() else []

def save(todos):
    DB.write_text(json.dumps(todos, ensure_ascii=False), encoding="utf-8")

def main():
    args = sys.argv[1:]
    todos = load()
    if not args or args[0] == "list":
        for i, t in enumerate(todos, 1):
            print(i, t["title"], "✓" if t["done"] else "·")
    elif args[0] == "add":
        todos.append({"title": " ".join(args[1:]), "done": False})
        save(todos)
    elif args[0] == "done":
        todos[int(args[1]) - 1]["done"] = True
        save(todos)

if __name__ == "__main__":
    main()
```
"""

TEST_OK = """\
```path=test_todo.py
import json
from pathlib import Path

from todo import save, load, DB

def test_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr("todo.DB", tmp_path / "t.json")
    save([{"title": "x", "done": False}])
    assert load()[0]["title"] == "x"
```
"""

REVIEW_OK = """\
# 审查结果

## 阻断项
（无）

## 建议项
- 可读性: main() 可拆小函数
"""

REVIEW_BLOCKER = """\
# 审查结果

## 阻断项
- 正确性: done 命令越界不报错，list 直接崩溃

## 建议项
- 风格: 变量名可更语义化
"""

# ---- 信封块工具 ----

def env(path: str, content: str) -> str:
    """包一个信封块。尾部带换行，保证多块拼接时围栏各行独立。"""
    return f"```path={path}\n{content}\n```\n"


def spec_response() -> str:
    return env("SPEC.md", SPEC_OK)


def plan_response() -> str:
    return env("PLAN.md", PLAN_OK)


def code_response() -> str:
    return env("todo.py", CODE_OK.split("```path=todo.py\n", 1)[1].rsplit("\n```", 1)[0])


def code_full_response() -> str:
    """code-agent 完整产出: todo.py + requirements.txt。"""
    return code_response() + env("requirements.txt", "# 无第三方依赖\n")


def test_response() -> str:
    return env("test_todo.py", TEST_OK.split("```path=test_todo.py\n", 1)[1].rsplit("\n```", 1)[0])


def review_response(blocker: bool = False) -> str:
    return env("REVIEW.md", REVIEW_BLOCKER if blocker else REVIEW_OK)


TEST_MD_CONTENT = """\
# 测试设计
- 覆盖 SPEC 验收: add/list/done 各一条 + 边界（空列表/done 越界）
"""


def test_full_response() -> str:
    """test-agent 完整产出: 测试文件 + TEST.md 两个块。"""
    return env("test_todo.py", TEST_OK.split("```path=test_todo.py\n", 1)[1].rsplit("\n```", 1)[0]) + env(
        "TEST.md", TEST_MD_CONTENT
    )


# 失败路径样例（供 FakeLLM 弹脚本用）

PLAN_MISSING_SECTIONS = """\
# 模块拆分
- todo.py: 单文件
"""

CODE_ROGUE_EXTRA = env("todo.py", "x = 1") + env("rogue_extra.py", "y = 2")  # 越界新增

REVIEW_MISSING_SECTIONS = "# 审查\n无分级清单\n"


# ---- 损坏/攻击输入 ----

DAMAGED_UNCLOSED = "```path=a.py\ncontent never closed"

DAMAGED_NO_PATH = "```\nno path here\n```"

TRAVERSAL_CASES = [
    "../evil.py",
    "../../etc/passwd",
    "..\\up.py",
    "C:\\windows\\evil.py",
    "/absolute/path.py",
    "a/../../b.py",
]
