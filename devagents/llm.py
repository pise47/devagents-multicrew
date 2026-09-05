"""LLM 客户端: OpenAI 兼容（按量）与 Anthropic 协议（MiMo Token Plan）双适配器。

错误四类（SPEC §4 重试分层）:
- NetworkError      连接/超时等瞬时网络问题 → transport 重试
- HTTPError         非 2xx（429/5xx 瞬时重试；其余 4xx 不重试直接抛）
- InvalidResponse   HTTP 成功但响应体不是合法 JSON / 结构不对
- ProtocolError     响应结构合法但缺 text/content

计费: 每次调用记 usage；单价表（元/M tokens）折算；缺单价 → total_cost None（只报 token）。

实测结论（2026-09-05）: MiMo Token Plan Anthropic 端点接受无 [1m] 后缀模型名、
拒绝 [1m]（400 Unsupported model）；响应原生含 thinking 内容块（适配器跳过）。
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import requests

ANTHROPIC_VERSION = "2023-06-01"


class LLMError(RuntimeError):
    """LLM 层错误基类。"""


class NetworkError(LLMError):
    """瞬时网络错误（连接失败/超时）。"""


class HTTPError(LLMError):
    """非 2xx 响应。status 429 或 >=500 视为瞬时。"""

    def __init__(self, status: int, body: str = ""):
        self.status = status
        super().__init__(f"HTTP {status}: {body[:200]}")


class InvalidResponse(LLMError):
    """响应体不是合法 JSON 或不可解析。"""


class ProtocolError(LLMError):
    """响应结构合法但内容缺失（无 text/content）。"""


@dataclass(frozen=True)
class ChatResult:
    content: str
    prompt_tokens: int
    completion_tokens: int
    model: str


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    calls: int = 0


def _is_transient(err: LLMError) -> bool:
    if isinstance(err, NetworkError):
        return True
    if isinstance(err, HTTPError):
        return err.status == 429 or err.status >= 500
    return False


class _LLMClient:
    """共享外壳: 重试循环 + usage 累计 + 计费。子类实现 _request_once/_parse。"""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        prices: dict | None = None,
        timeout_s: int = 180,
        transport_retry: int = 1,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.prices = prices or {}
        self.timeout_s = timeout_s
        self.transport_retry = max(0, transport_retry)
        self.usage = Usage()
        self.retries: dict[str, int] = {"transport": 0}
        self._calls: list[tuple[str, int, int]] = []  # (model, pt, ct)

    def chat(self, messages: list[dict], model: str, **kwargs) -> ChatResult:
        """一次角色调用。瞬时错误按 transport_retry 重试，耗尽原样抛出。"""
        attempt = 0
        while True:
            try:
                result = self._parse(self._request_once(messages, model), model)
            except LLMError as e:
                if _is_transient(e) and attempt < self.transport_retry:
                    self.retries["transport"] += 1
                    attempt += 1
                    time.sleep(0.5 * attempt)  # 简单退避
                    continue
                raise
            self.usage.prompt_tokens += result.prompt_tokens
            self.usage.completion_tokens += result.completion_tokens
            self.usage.calls += 1
            self._calls.append((model, result.prompt_tokens, result.completion_tokens))
            return result

    def total_cost(self) -> float | None:
        """累计费用（元）。任一模型单价未配置 → None（只报 token）。"""
        total = 0.0
        for model, pt, ct in self._calls:
            price = self.prices.get(model)
            if not price:
                return None
            total += pt / 1e6 * float(price.get("input", 0.0))
            total += ct / 1e6 * float(price.get("output", 0.0))
        return round(total, 6)

    def _request_once(self, messages: list[dict], model: str) -> dict:
        raise NotImplementedError

    def _parse(self, payload: dict, model: str) -> ChatResult:
        raise NotImplementedError


def _http_error_from(resp) -> None:
    """requests.HTTPError → 本层 HTTPError（含响应体摘要）。"""
    try:
        detail = resp.text[:200]
    except Exception:
        detail = ""
    raise HTTPError(resp.status_code, detail)


class OpenAIClient(_LLMClient):
    """OpenAI 兼容 /chat/completions（按量 sk-key）。"""

    def _request_once(self, messages: list[dict], model: str) -> dict:
        url = f"{self.base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        body = {"model": model, "messages": messages}
        try:
            resp = requests.post(url, headers=headers, json=body, timeout=self.timeout_s)
        except requests.ConnectionError as e:
            raise NetworkError(f"连接失败 {self.base_url}: {e}") from e
        except requests.Timeout as e:
            raise NetworkError(f"请求超时({self.timeout_s}s): {e}") from e
        except requests.RequestException as e:
            # 其余 requests 异常（ChunkedEncoding/ContentDecoding 等）必须收进 LLMError 体系
            raise NetworkError(f"请求异常: {e}") from e
        try:
            resp.raise_for_status()
        except requests.HTTPError:
            _http_error_from(resp)
        return _json_of(resp)

    @staticmethod
    def _parse(payload: dict, model: str) -> ChatResult:
        _check_dict(payload)
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ProtocolError(f"响应无 choices: {str(payload)[:200]}")
        msg = choices[0].get("message") or {}
        content = msg.get("content")
        if content is None:
            raise ProtocolError("choices[0].message.content 缺失")
        usage = payload.get("usage") or {}
        pt = int(usage.get("prompt_tokens", 0) or 0)
        ct = int(usage.get("completion_tokens", 0) or 0)
        return ChatResult(content=str(content), prompt_tokens=pt, completion_tokens=ct, model=model)


class AnthropicClient(_LLMClient):
    """Anthropic /v1/messages（MiMo Token Plan 套餐 tp-key，无 [1m] 后缀）。

    max_tokens 必填（config llm.max_output_tokens）；响应 content 含 thinking
    块 → 只取 type=text 拼装；usage = input_tokens/output_tokens。
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        prices: dict | None = None,
        timeout_s: int = 180,
        transport_retry: int = 1,
        max_output_tokens: int = 16384,
    ):
        super().__init__(base_url, api_key, prices, timeout_s, transport_retry)
        self.max_output_tokens = max_output_tokens

    def _request_once(self, messages: list[dict], model: str) -> dict:
        url = f"{self.base_url}/v1/messages"
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "Content-Type": "application/json",
        }
        # Anthropic 协议: system 必须放顶层字段（messages 里只允许 user/assistant）
        system_parts = [m["content"] for m in messages if m.get("role") == "system"]
        rest = [
            {"role": m["role"], "content": m["content"]}
            for m in messages
            if m.get("role") != "system"
        ]
        body: dict = {"model": model, "messages": rest, "max_tokens": self.max_output_tokens}
        if system_parts:
            body["system"] = "\n\n".join(system_parts)
        try:
            resp = requests.post(url, headers=headers, json=body, timeout=self.timeout_s)
        except requests.ConnectionError as e:
            raise NetworkError(f"连接失败 {self.base_url}: {e}") from e
        except requests.Timeout as e:
            raise NetworkError(f"请求超时({self.timeout_s}s): {e}") from e
        try:
            resp.raise_for_status()
        except requests.HTTPError:
            _http_error_from(resp)
        return _json_of(resp)

    @staticmethod
    def _parse(payload: dict, model: str) -> ChatResult:
        _check_dict(payload)
        content = payload.get("content")
        if not isinstance(content, list):
            raise ProtocolError(f"响应无 content 列表: {str(payload)[:200]}")
        texts = [item.get("text", "") for item in content if isinstance(item, dict) and item.get("type") == "text"]
        if not texts:
            raise ProtocolError("响应无 text 内容块（可能只有 thinking）")
        usage = payload.get("usage") or {}
        pt = int(usage.get("input_tokens", 0) or 0)
        ct = int(usage.get("output_tokens", 0) or 0)
        return ChatResult(content="\n".join(texts), prompt_tokens=pt, completion_tokens=ct, model=model)


def _check_dict(payload: dict) -> None:
    if not isinstance(payload, dict):
        raise InvalidResponse(f"响应不是 JSON 对象: {type(payload)}")


def _json_of(resp) -> dict:
    try:
        return resp.json()
    except ValueError as e:
        raise InvalidResponse(f"响应体不是合法 JSON: {e}") from e
