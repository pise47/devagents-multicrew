"""Anthropic 协议客户端契约（MiMo Token Plan 端点，无 [1m] 后缀）。

实测结论（2026-09-05 probe）: token-plan-cn.xiaomimimo.com/anthropic
接受 mimo-v2.5-pro / mimo-v2.5（无后缀），拒绝 [1m]；响应原生含 thinking 块。
"""

from __future__ import annotations

import pytest

from devagents.llm import (
    AnthropicClient,
    ChatResult,
    HTTPError,
    InvalidResponse,
    NetworkError,
    ProtocolError,
)
from tests.test_llm import FakeResp, _messages, _patch_post


def ok_payload(text: str = "你好", with_thinking: bool = True) -> dict:
    content = []
    if with_thinking:
        content.append({"type": "thinking", "thinking": "deep thinking", "signature": "sig"})
    content.append({"type": "text", "text": text})
    return {
        "id": "x",
        "type": "message",
        "content": content,
        "usage": {"input_tokens": 12, "output_tokens": 7},
    }


@pytest.fixture
def client():
    return AnthropicClient(
        base_url="https://token-plan-cn.xiaomimimo.com/anthropic",
        api_key="tp-test",
        prices={"mimo-v2.5-pro": {"input": 1.0, "output": 2.0}},
    )


def test_chat_sends_anthropic_protocol(client, monkeypatch):
    calls = _patch_post(monkeypatch, [FakeResp(payload=ok_payload("结果"))])
    res = client.chat(_messages(), model="mimo-v2.5-pro")
    assert isinstance(res, ChatResult)
    assert res.content == "结果"  # thinking 块被跳过
    assert res.prompt_tokens == 12 and res.completion_tokens == 7
    url, body = calls[0]
    assert url == "https://token-plan-cn.xiaomimimo.com/anthropic/v1/messages"
    assert body["model"] == "mimo-v2.5-pro"
    assert body["messages"] == _messages()
    assert body["max_tokens"] > 0


def test_system_message_hoisted_to_top_level(client, monkeypatch):
    """system 角色必须提到顶层 system 字段，messages 里只留 user/assistant。"""
    body_capture = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        body_capture.update(json or {})
        return FakeResp(payload=ok_payload("ok"))

    monkeypatch.setattr("devagents.llm.requests.post", fake_post)
    msgs = [{"role": "system", "content": "你是 spec-agent"}, {"role": "user", "content": "任务"}]
    client.chat(msgs, model="m")
    assert body_capture["system"] == "你是 spec-agent"
    assert body_capture["messages"] == [{"role": "user", "content": "任务"}]
    assert all(m["role"] != "system" for m in body_capture["messages"])


def test_chat_headers(client, monkeypatch):
    headers_capture = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        headers_capture.update(headers or {})
        return FakeResp(payload=ok_payload("ok"))

    monkeypatch.setattr("devagents.llm.requests.post", fake_post)
    client.chat(_messages(), model="m")
    assert headers_capture.get("x-api-key") == "tp-test"
    assert headers_capture.get("anthropic-version", "").startswith("2023-")
    assert "Bearer" not in headers_capture.get("Authorization", "")


def test_thinking_only_response_is_protocol_error(client, monkeypatch):
    payload = ok_payload("")
    payload["content"] = [{"type": "thinking", "thinking": "x", "signature": "s"}]
    _patch_post(monkeypatch, [FakeResp(payload=payload)])
    with pytest.raises(ProtocolError):
        client.chat(_messages(), model="m")


def test_http_529_retried_then_success(client, monkeypatch):
    """Anthropic overloaded(529) 视为瞬时，transport 重试 1 次。"""
    _patch_post(
        monkeypatch,
        [FakeResp(exc=HTTPError(529, "overloaded")), FakeResp(payload=ok_payload("ok"))],
    )
    res = client.chat(_messages(), model="m")
    assert res.content == "ok"
    assert client.retries["transport"] == 1


def test_http_401_not_retried(client, monkeypatch):
    _patch_post(monkeypatch, [FakeResp(exc=HTTPError(401, "invalid x-api-key"))])
    with pytest.raises(HTTPError) as ei:
        client.chat(_messages(), model="m")
    assert ei.value.status == 401
    assert client.retries["transport"] == 0


def test_network_error_retried(client, monkeypatch):
    _patch_post(monkeypatch, [FakeResp(exc=NetworkError("conn")), FakeResp(payload=ok_payload("ok"))])
    assert client.chat(_messages(), model="m").content == "ok"
    assert client.retries["transport"] == 1


def test_bad_json_is_invalid_response(client, monkeypatch):
    _patch_post(monkeypatch, [FakeResp(payload=None)])
    with pytest.raises(InvalidResponse):
        client.chat(_messages(), model="m")


def test_usage_and_cost_accumulate(client, monkeypatch):
    _patch_post(monkeypatch, [FakeResp(payload=ok_payload("a")), FakeResp(payload=ok_payload("b"))])
    client.chat(_messages(), model="mimo-v2.5-pro")
    client.chat(_messages(), model="mimo-v2.5-pro")
    assert (client.usage.prompt_tokens, client.usage.completion_tokens) == (24, 14)
    assert client.total_cost() == pytest.approx(24 / 1e6 + 14 / 1e6 * 2)
