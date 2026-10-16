"""Owned pinned native CrewAI providers and original completion authority."""

import base64
import json
import os
from dataclasses import dataclass, field
from urllib.parse import urlsplit
import httpx
import httpx2
from openai import AsyncOpenAI, omit as openai_omit
from anthropic import AsyncAnthropic, omit
from google import genai
from google.genai import types
from pydantic import PrivateAttr, model_validator
from crewai.llms.providers.openai.completion import OpenAICompletion
from crewai.llms.providers.anthropic.completion import AnthropicCompletion
from crewai.llms.providers.gemini.completion import GeminiCompletion

ROLES = ("researcher", "checker", "writer")
DEFAULT_URLS = {
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com",
    "gemini": "https://generativelanguage.googleapis.com",
}
KEYS = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GOOGLE_API_KEY",
}
MAX_BODY = 1048576


@dataclass(frozen=True)
class RoleConfig:
    role: str
    provider: str
    model: str
    api_key: str = field(repr=False)
    base_url: str = ""

    def validate(self):
        if (
            self.role not in ROLES
            or self.provider not in DEFAULT_URLS
            or not isinstance(self.model, str)
            or not self.model
            or len(self.model) > 200
            or any(c.isspace() for c in self.model)
        ):
            raise ValueError("explicit role/provider/model is required")
        if (
            not isinstance(self.api_key, str)
            or not self.api_key
            or len(self.api_key) > 4096
            or any(not 33 <= ord(c) <= 126 for c in self.api_key)
        ):
            raise ValueError(f"explicit {self.role} provider API key is required")
        try:
            url = urlsplit(self.base_url)
            if (
                not url.hostname
                or url.username
                or url.password
                or url.query
                or url.fragment
                or not (
                    url.scheme == "https"
                    or url.scheme == "http"
                    and url.hostname in {"127.0.0.1", "localhost", "::1"}
                )
            ):
                raise ValueError()
            url.port
        except (ValueError, TypeError):
            raise ValueError(
                "provider endpoint requires HTTPS or loopback HTTP without URL credentials/query/fragment"
            ) from None
        if self.provider == "gemini" and (
            os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "false").lower()
            not in {"false", "0", ""}
            or os.getenv("GOOGLE_GENAI_USE_ENTERPRISE", "").lower() in {"true", "1"}
        ):
            raise ValueError("only explicit Gemini Developer API mode is qualified")
        return self

    def public(self):
        return {
            "role": self.role,
            "provider": self.provider,
            "model": self.model,
            "base_url": self.base_url,
        }


def from_environment(models=None, base_urls=None):
    result = []
    for role in ROLES:
        selected = (
            (models or {}).get(role)
            or os.getenv(role.upper() + "_MODEL")
            or os.getenv("RESEARCH_MODEL")
        )
        if not selected or "/" not in selected:
            raise ValueError(
                f"{role.upper()}_MODEL or RESEARCH_MODEL requires provider/model"
            )
        provider, model = selected.split("/", 1)
        if provider not in DEFAULT_URLS:
            raise ValueError("qualified providers are openai, anthropic and gemini")
        key = (
            os.getenv(role.upper() + "_API_KEY")
            or os.getenv(KEYS[provider])
            or (os.getenv("GEMINI_API_KEY") if provider == "gemini" else None)
        )
        result.append(
            RoleConfig(
                role,
                provider,
                model,
                key,
                (base_urls or {}).get(role)
                or os.getenv(role.upper() + "_BASE_URL")
                or DEFAULT_URLS[provider],
            ).validate()
        )
    return result


class OwnedOpenAI(OpenAICompletion):
    _owned = PrivateAttr()
    _bridge = PrivateAttr()

    def call(self, *args, **kwargs):
        return self._bridge.invoke(self.acall, *args, **kwargs)

    @model_validator(mode="after")
    def _init_clients(self):
        return self

    def _get_async_client(self):
        return self._owned

    def _get_sync_client(self):
        raise RuntimeError("this role owns native async work only")


class OwnedAnthropic(AnthropicCompletion):
    _owned = PrivateAttr()
    _bridge = PrivateAttr()

    def call(self, *args, **kwargs):
        return self._bridge.invoke(self.acall, *args, **kwargs)

    @model_validator(mode="after")
    def _init_clients(self):
        return self

    def _get_async_client(self):
        return self._owned

    def _get_sync_client(self):
        raise RuntimeError("this role owns native async work only")


class OwnedGemini(GeminiCompletion):
    _owned = PrivateAttr()
    _bridge = PrivateAttr()

    def call(self, *args, **kwargs):
        return self._bridge.invoke(self.acall, *args, **kwargs)

    @model_validator(mode="after")
    def _init_client(self):
        return self

    def _get_async_client(self):
        return self._owned

    def _get_sync_client(self):
        raise RuntimeError("this role owns native async work only")


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate provider JSON key")
            result[key] = value
        return result

    def invalid(value):
        raise ValueError("nonfinite provider JSON")

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def completion(provider, body):
    if not isinstance(body, dict):
        raise ValueError("provider response must be an object")
    if provider == "openai":
        choices = body.get("choices")
        if (
            body.get("object") != "chat.completion"
            or not isinstance(body.get("id"), str)
            or not body["id"].strip()
            or not isinstance(choices, list)
            or len(choices) != 1
            or not isinstance(choices[0], dict)
        ):
            raise ValueError("expected one original chat completion")
        choice = choices[0]
        message = choice.get("message")
        if (
            type(choice.get("index")) is not int
            or choice.get("index") != 0
            or choice.get("finish_reason") != "stop"
            or not isinstance(message, dict)
            or message.get("role") != "assistant"
            or message.get("refusal")
            or message.get("tool_calls")
            or message.get("function_call")
            or not isinstance(message.get("content"), str)
            or not message["content"].strip()
        ):
            raise ValueError(
                "role requires completed stop text without pending/refused/tool output"
            )
        return {
            "response_id": body["id"],
            "response_model": body.get("model"),
            "finish_reason": choice["finish_reason"],
        }
    if provider == "anthropic":
        content = body.get("content")
        if (
            body.get("type") != "message"
            or body.get("role") != "assistant"
            or not isinstance(body.get("id"), str)
            or not body["id"].strip()
            or body.get("stop_reason") != "end_turn"
            or body.get("stop_sequence") is not None
            or not isinstance(content, list)
            or not content
            or any(
                not isinstance(x, dict)
                or x.get("type") not in {"text", "thinking", "redacted_thinking"}
                for x in content
            )
            or not any(
                x.get("type") == "text"
                and isinstance(x.get("text"), str)
                and x["text"].strip()
                for x in content
            )
        ):
            raise ValueError("role requires one completed end_turn text message")
        return {
            "response_id": body["id"],
            "response_model": body.get("model"),
            "finish_reason": body["stop_reason"],
        }
    candidates = body.get("candidates")
    feedback = body.get("promptFeedback")
    if isinstance(feedback, dict) and feedback.get("blockReason") not in {
        None,
        "BLOCK_REASON_UNSPECIFIED",
    }:
        raise ValueError("Gemini prompt was blocked")
    if (
        not isinstance(candidates, list)
        or len(candidates) != 1
        or not isinstance(candidates[0], dict)
    ):
        raise ValueError("expected one Gemini candidate")
    candidate = candidates[0]
    content = candidate.get("content")
    parts = content.get("parts") if isinstance(content, dict) else None
    if (
        candidate.get("finishReason") != "STOP"
        or not isinstance(content, dict)
        or content.get("role") not in {None, "model"}
        or not isinstance(parts, list)
        or not parts
        or any(
            not isinstance(x, dict)
            or any(
                x.get(key) is not None
                for key in (
                    "functionCall",
                    "executableCode",
                    "codeExecutionResult",
                    "inlineData",
                    "fileData",
                )
            )
            for x in parts
        )
        or not any(
            not x.get("thought")
            and isinstance(x.get("text"), str)
            and x["text"].strip()
            for x in parts
        )
        or any(
            isinstance(x, dict) and x.get("blocked") is True
            for x in candidate.get("safetyRatings") or []
        )
    ):
        raise ValueError("role requires one completed unblocked STOP text candidate")
    return {
        "response_id": body.get("responseId"),
        "response_model": body.get("modelVersion"),
        "finish_reason": candidate["finishReason"],
    }


def measurements(provider, body):
    raw = (
        body.get("usageMetadata" if provider == "gemini" else "usage")
        if isinstance(body, dict)
        else None
    )
    names = {
        "openai": ("prompt_tokens", "completion_tokens", "total_tokens"),
        "anthropic": (
            "input_tokens",
            "output_tokens",
            "cache_creation_input_tokens",
            "cache_read_input_tokens",
        ),
        "gemini": ("promptTokenCount", "candidatesTokenCount", "totalTokenCount"),
    }
    fields = {}
    for name in names[provider]:
        value = raw.get(name) if isinstance(raw, dict) else None
        valid = type(value) is int and 0 <= value <= 2**53 - 1
        fields[name] = {
            "state": "observed" if valid else "unknown" if value is None else "invalid",
            "value": value if valid else None,
        }
    return {
        "source": "original decoded HTTP JSON before SDK normalization",
        "raw": raw,
        "fields": fields,
        "cost_usd": None,
    }


class Boundary:
    def __init__(self, config, receipt):
        self.config = config
        self.receipt = receipt
        self.observation = None

    async def request(self, request):
        self.receipt.guard()
        if self.observation is not None:
            raise RuntimeError(
                "one native HTTP request per role is supported; retry/repair is disabled"
            )
        raw = await request.aread()
        if len(raw) > MAX_BODY:
            raise ValueError("role request exceeds retained1MiB bound")
        body = strict_json(raw)
        if body.get("stream") is True:
            raise ValueError("only nonstreaming role JSON is qualified")
        self.observation = {
            "role": self.config.role,
            "provider": self.config.provider,
            "status": "prepared",
            "request_sha256": self.receipt.sha(raw),
            "request_body": body,
            "response": None,
            "error": None,
        }
        self.receipt.data["native"].append(self.observation)
        self.receipt.save()
        self.receipt.guard()

    async def response(self, response):
        item = self.observation
        item["status"] = "received"
        item["http_status"] = response.status_code
        item["request_id"] = response.headers.get(
            "x-request-id"
        ) or response.headers.get("request-id")
        try:
            raw = await response.aread()
            item.update(
                decoded_body_base64=base64.b64encode(raw[:MAX_BODY]).decode(),
                body_sha256=self.receipt.sha(raw),
                truncated=len(raw) > MAX_BODY,
            )
            if len(raw) > MAX_BODY:
                self.receipt.save()
                raise ValueError("provider response exceeds retained1MiB bound")
            body = strict_json(raw)
            item.update(
                response=body, reported_usage=measurements(self.config.provider, body)
            )
            self.receipt.save()
            self.receipt.guard()
            if 200 <= response.status_code < 300:
                item.update(completion(self.config.provider, body))
                item["status"] = "accepted"
            else:
                item["status"] = "http_error"
            self.receipt.save()
            self.receipt.guard()
        except BaseException as error:
            self.receipt.failure = self.receipt.failure or error
            item.update(
                status="rejected",
                error={"name": type(error).__name__, "message": str(error)},
            )
            self.receipt.save()
            raise
        finally:
            await response.aclose()


async def create_role(config, receipt, stack, transport=None, bridge=None):
    config.validate()
    boundary = Boundary(config, receipt)
    hooks = {"request": [boundary.request], "response": [boundary.response]}
    options = {
        "transport": transport,
        "timeout": httpx.Timeout(30, connect=5),
        "trust_env": False,
        "follow_redirects": False,
        "event_hooks": hooks,
    }
    if config.provider == "anthropic":
        options["timeout"] = httpx2.Timeout(30, connect=5)
    http_type = (
        httpx2.AsyncClient if config.provider == "anthropic" else httpx.AsyncClient
    )
    client = await stack.enter_async_context(http_type(**options))
    if config.provider == "openai":
        sdk = await stack.enter_async_context(
            AsyncOpenAI(
                api_key=config.api_key,
                base_url=config.base_url,
                http_client=client,
                max_retries=0,
                organization=None,
                project=None,
                default_headers={
                    "OpenAI-Organization": openai_omit,
                    "OpenAI-Project": openai_omit,
                },
            )
        )
        llm = OwnedOpenAI(
            model=config.model,
            provider="openai",
            api_key=config.api_key,
            base_url=config.base_url,
            max_retries=0,
            max_completion_tokens=2048,
            stream=False,
            temperature=0,
            timeout=30,
        )
    elif config.provider == "anthropic":
        sdk = await stack.enter_async_context(
            AsyncAnthropic(
                api_key=config.api_key,
                auth_token=None,
                base_url=config.base_url,
                http_client=client,
                max_retries=0,
                default_headers={"Authorization": omit, "X-Api-Key": config.api_key},
            )
        )
        llm = OwnedAnthropic(
            model=config.model,
            provider="anthropic",
            api_key=config.api_key,
            base_url=config.base_url,
            max_retries=0,
            max_tokens=2048,
            stream=False,
            temperature=None,
            timeout=30,
        )
    else:

        class NoSync(httpx.BaseTransport):
            def handle_request(self, request):
                raise RuntimeError("this role owns async generateContent only")

        sync = stack.enter_context(httpx.Client(transport=NoSync(), trust_env=False))
        sdk = genai.Client(
            api_key=config.api_key,
            vertexai=False,
            http_options={
                "base_url": config.base_url,
                "api_version": "v1beta",
                "timeout": 30000,
                "retry_options": types.HttpRetryOptions(attempts=1),
                "httpx_client": sync,
                "httpx_async_client": client,
            },
        )
        stack.callback(sdk.close)
        stack.push_async_callback(sdk.aio.aclose)
        llm = OwnedGemini(
            model=config.model,
            provider="gemini",
            api_key=config.api_key,
            use_vertexai=False,
            max_output_tokens=2048,
            stream=False,
            temperature=0,
        )
    llm._owned = sdk
    llm._bridge = bridge
    return llm, boundary
