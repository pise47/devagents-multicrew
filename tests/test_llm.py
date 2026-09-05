"""llm 客户端契约: 调用/错误四类分类/瞬时重试/usage 与计费。"""

from __future__ import annotations

import json

import pytest

from devagents.llm import (
    ChatResult,
    HTTPError,
    InvalidResponse,
    LLMError,
    NetworkError,
    OpenAIClient,
    ProtocolError as LlmProtocolError,
)


class FakeResp:
    """requests.post 的替身响应。"""

    def __init__(self, payload: dict | None = None, exc: Exception | None = None):
        self._payload = payload
        self._exc = exc

    def raise_for_status(self):
        if isinstance(self._exc, HTTPError):
            raise self._exc
        if isinstance(self._exc, Exception):
            raise self._exc

    def json(self):
        if self._exc:
            raise self._exc
        if self._payload is None:
            raise ValueError("bad json body")
        return self._payload


def ok_payload(content: str = "ok", usage=None) -> dict:
    return {
        "choices": [{"message": {"content": content}}],
        "usage": usage or {"prompt_tokens": 10, "completion_tokens": 5},
    }


@pytest.fixture
def client():
    prices = {"m1": {"input": 2.0, "output": 4.0}}  # 元/M tokens
    return OpenAIClient(base_url="http://fake", api_key="sk", prices=prices)


def _patch_post(monkeypatch, responses: list):
    """按序弹响应的 requests.post 替身; 耗尽则报错。"""
    calls = []

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append((url, json))
        if not responses:
            raise AssertionError("requests.post 调用数超出预期")
        return responses.pop(0)

    monkeypatch.setattr("devagents.llm.requests.post", fake_post)
    return calls


def _messages():
    return [{"role": "user", "content": "hi"}]


def test_chat_happy_path(client, monkeypatch):
    calls = _patch_post(monkeypatch, [FakeResp(payload=ok_payload("你好"))])
    res = client.chat(_messages(), model="m1")
    assert isinstance(res, ChatResult)
    assert res.content == "你好"
    assert res.prompt_tokens == 10 and res.completion_tokens == 5
    url = calls[0][0]
    assert url.endswith("/chat/completions")
    body = calls[0][1]
    assert body["model"] == "m1"
    assert body["messages"] == _messages()


def test_usage_accumulates_and_cost_calculates(client, monkeypatch):
    _patch_post(monkeypatch, [FakeResp(payload=ok_payload("a")), FakeResp(payload=ok_payload("b"))])
    client.chat(_messages(), model="m1")
    client.chat(_messages(), model="m1")
    u = client.usage
    assert (u.prompt_tokens, u.completion_tokens) == (20, 10)
    cost = client.total_cost()
    assert cost is not None
    assert cost == pytest.approx(20 / 1e6 * 2.0 + 10 / 1e6 * 4.0)


def test_missing_price_returns_none_cost(client, monkeypatch):
    """单价未配置的模型 → total_cost 为 None（账单只报 token，不瞎算钱）。"""
    _patch_post(monkeypatch, [FakeResp(payload=ok_payload("a"))])
    client.chat(_messages(), model="no-price-model")
    assert client.total_cost() is None


def test_network_error_classified_and_retried_once(client, monkeypatch):
    """瞬时类(Network) → transport 重试 1 次 → 仍失败则抛 NetworkError。"""
    _patch_post(
        monkeypatch,
        [
            FakeResp(exc=NetworkError("conn refused")),
            FakeResp(exc=NetworkError("conn refused")),
        ],
    )
    with pytest.raises(NetworkError):
        client.chat(_messages(), model="m1")
    assert client.retries["transport"] == 1


def test_http_5xx_retried_once_then_raised(client, monkeypatch):
    _patch_post(
        monkeypatch,
        [FakeResp(exc=HTTPError(500, "boom")), FakeResp(exc=HTTPError(500, "boom"))],
    )
    with pytest.raises(HTTPError):
        client.chat(_messages(), model="m1")
    assert client.retries["transport"] == 1


def test_http_400_not_retried(client, monkeypatch):
    """4xx 非瞬时（除 429）→ 不重试直接抛。"""
    _patch_post(monkeypatch, [FakeResp(exc=HTTPError(400, "bad request"))])
    with pytest.raises(HTTPError):
        client.chat(_messages(), model="m1")
    assert client.retries["transport"] == 0


def test_http_429_retried(client, monkeypatch):
    _patch_post(monkeypatch, [FakeResp(exc=HTTPError(429, "rate limit")), FakeResp(payload=ok_payload("ok"))])
    res = client.chat(_messages(), model="m1")
    assert res.content == "ok"
    assert client.retries["transport"] == 1


def test_transient_then_success(client, monkeypatch):
    """瞬时失败后成功 → 不抛错且计入重试。"""
    _patch_post(monkeypatch, [FakeResp(exc=NetworkError("drop")), FakeResp(payload=ok_payload("ok"))])
    res = client.chat(_messages(), model="m1")
    assert res.content == "ok"
    assert client.retries["transport"] == 1


def test_bad_json_body_classified_invalid_response(client, monkeypatch):
    _patch_post(monkeypatch, [FakeResp(payload=None)])  # json() 抛 ValueError
    with pytest.raises(InvalidResponse):
        client.chat(_messages(), model="m1")
    assert client.retries["transport"] == 0  # 非瞬时，不重试


def test_missing_choices_classified_protocol_error(client, monkeypatch):
    _patch_post(monkeypatch, [FakeResp(payload={"choices": []})])
    with pytest.raises(LlmProtocolError):
        client.chat(_messages(), model="m1")


def test_all_llm_errors_subclass_llm_error():
    assert issubclass(NetworkError, LLMError)
    assert issubclass(HTTPError, LLMError)
    assert issubclass(InvalidResponse, LLMError)
    assert issubclass(LlmProtocolError, LLMError)
