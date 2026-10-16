import asyncio
import json
from pathlib import Path
import httpx
import httpx2
import pytest
from research_team.native import RoleConfig, ROLES
from research_team.worker import run_team_async
from test_research import PACK, supported_brief


def outputs():
    brief = supported_brief().model_dump(mode="json")
    return {
        "researcher": {"claims": brief["claims"], "gaps": []},
        "checker": {
            "reviews": [
                {
                    "claim_index": 0,
                    "disposition": "supported",
                    "reason": "Exact quote observed",
                }
            ],
            "conflicts": brief["conflicts"],
            "gaps": [],
        },
        "writer": brief,
    }


def response(provider, role, stop=None):
    text = "Final Answer: " + json.dumps(outputs()[role])
    if provider == "openai":
        return {
            "id": "chatcmpl_controlled_" + role,
            "object": "chat.completion",
            "created": 1792144800,
            "model": "gpt-observed",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": text},
                    "finish_reason": stop or "stop",
                }
            ],
            "usage": {"prompt_tokens": 11, "completion_tokens": 5, "total_tokens": 16},
        }
    if provider == "anthropic":
        return {
            "id": "msg_controlled_" + role,
            "type": "message",
            "role": "assistant",
            "model": "claude-observed",
            "content": [{"type": "text", "text": text}],
            "stop_reason": stop or "end_turn",
            "stop_sequence": None,
            "usage": {"input_tokens": 11, "output_tokens": 5},
        }
    return {
        "responseId": "gemini_controlled_" + role,
        "modelVersion": "gemini-observed",
        "candidates": [
            {
                "index": 0,
                "content": {"role": "model", "parts": [{"text": text}]},
                "finishReason": stop or "STOP",
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 11,
            "candidatesTokenCount": 5,
            "totalTokenCount": 16,
        },
    }


class Transport(httpx.AsyncBaseTransport):
    def __init__(self, provider, role, body=None, delay=None, status=200):
        self.status = status
        self.provider = provider
        self.role = role
        self.body = body or response(provider, role)
        self.requests = []
        self.closed = False
        self.delay = delay

    async def handle_async_request(self, request):
        self.requests.append(json.loads(await request.aread()))
        if self.delay:
            await self.delay()
        return httpx.Response(
            self.status, json=self.body, headers={"x-request-id": "req-controlled"}
        )

    async def aclose(self):
        self.closed = True


class AnthropicTransport(httpx2.AsyncBaseTransport):
    def __init__(self, role, body=None):
        self.role = role
        self.body = body or response("anthropic", role)
        self.requests = []
        self.closed = False

    async def handle_async_request(self, request):
        self.requests.append(json.loads(await request.aread()))
        return httpx2.Response(
            200, json=self.body, headers={"request-id": "req-controlled"}
        )

    async def aclose(self):
        self.closed = True


def configured(providers):
    models = {
        "openai": "gpt-synthetic",
        "anthropic": "claude-synthetic",
        "gemini": "gemini-synthetic",
    }
    return [
        RoleConfig(
            role,
            provider,
            models[provider],
            "synthetic-key",
            "http://127.0.0.1:19/v1" if provider == "openai" else "http://127.0.0.1:19",
        )
        for role, provider in zip(ROLES, providers)
    ]


def transports(providers):
    return {
        role: AnthropicTransport(role)
        if provider == "anthropic"
        else Transport(provider, role)
        for role, provider in zip(ROLES, providers)
    }


@pytest.mark.parametrize(
    "providers",
    [
        ["openai"] * 3,
        ["anthropic"] * 3,
        ["gemini"] * 3,
        ["gemini", "openai", "anthropic"],
    ],
)
def test_actual_three_role_native_sdk_completion_and_handoff(tmp_path, providers):
    clients = transports(providers)
    result = asyncio.run(
        run_team_async(
            PACK,
            configs=configured(providers),
            transports=clients,
            output_root=tmp_path / "runs",
        )
    )
    assert (
        result["status"] == "supported"
        and result["execution_kind"] == "native_crewai_three_role"
    )
    assert all(
        client.closed and len(client.requests) == 1 for client in clients.values()
    )
    receipt = json.loads(Path(result["receipt_path"]).read_text())
    assert receipt["status"] == "completed" and receipt["native_clients_closed"]
    assert [row["role"] for row in receipt["native"]] == list(ROLES)
    assert [row["role"] for row in receipt["role_outputs"]] == list(ROLES)
    assert all(row["status"] == "accepted" for row in receipt["native"])
    assert receipt["cost_usd"] is None and "synthetic-key" not in json.dumps(receipt)
    for config, row in zip(configured(providers), receipt["native"]):
        assert config.model != row["response_model"]


@pytest.mark.parametrize(
    "provider,stop",
    [("openai", "length"), ("anthropic", "max_tokens"), ("gemini", "MAX_TOKENS")],
)
@pytest.mark.parametrize("role", ROLES)
def test_unfinished_role_cannot_release_brief_or_run_later_roles(
    tmp_path, provider, stop, role
):
    providers = [provider] * 3
    clients = transports(providers)
    clients[role].body = response(provider, role, stop)
    with pytest.raises(Exception) as error:
        asyncio.run(
            run_team_async(
                PACK,
                configs=configured(providers),
                transports=clients,
                output_root=tmp_path / "runs",
            )
        )
    data = json.loads(Path(error.value.receipt_path).read_text())
    index = ROLES.index(role)
    assert (
        data["status"] == "failed"
        and data["result"] is None
        and data["native_clients_closed"]
        and data["native_bridge_closed"]
    )
    assert [len(clients[x].requests) for x in ROLES] == [
        1 if i <= index else 0 for i in range(3)
    ]
    assert all(client.closed for client in clients.values())
    assert (
        data["native"][-1]["status"] == "rejected"
        and data["native"][-1]["reported_usage"] is not None
    )
    assert len(data["role_outputs"]) == index


@pytest.mark.parametrize("cancel", [False, True])
def test_parent_cancellation_or_deadline_drains_actual_bridge_and_sdk(tmp_path, cancel):
    async def scenario():
        clients = transports(["openai"] * 3)
        ready = asyncio.Event()
        drained = asyncio.Event()

        async def delay():
            ready.set()
            try:
                await asyncio.sleep(30)
            finally:
                drained.set()

        clients["researcher"].delay = delay
        task = asyncio.create_task(
            run_team_async(
                PACK,
                configs=configured(["openai"] * 3),
                transports=clients,
                output_root=tmp_path / "runs",
                timeout_seconds=10 if cancel else 0.5,
            )
        )
        await asyncio.wait_for(ready.wait(), 4)
        if cancel:
            task.cancel()
        with pytest.raises(asyncio.CancelledError if cancel else TimeoutError) as error:
            await task
        data = json.loads(Path(error.value.receipt_path).read_text())
        assert (
            data["status"] == "failed"
            and data["native_clients_closed"]
            and data["native_bridge_closed"]
        )
        assert drained.is_set() and all(client.closed for client in clients.values())
        assert clients["checker"].requests == [] and clients["writer"].requests == []
        before = Path(error.value.receipt_path).read_bytes()
        await asyncio.sleep(0.05)
        assert Path(error.value.receipt_path).read_bytes() == before

    asyncio.run(scenario())


def test_original_usage_unknown_zero_invalid_and_sdk_counters_are_separate(tmp_path):
    clients = transports(["openai"] * 3)
    clients["researcher"].body["usage"] = {
        "prompt_tokens": 0,
        "completion_tokens": False,
        "total_tokens": None,
        "custom_counter": 71,
    }
    with pytest.raises(TypeError) as error:
        asyncio.run(
            run_team_async(
                PACK,
                configs=configured(["openai"] * 3),
                transports=clients,
                output_root=tmp_path / "runs",
            )
        )
    data = json.loads(Path(error.value.receipt_path).read_text())
    usage = data["native"][0]["reported_usage"]
    assert usage["fields"]["prompt_tokens"] == {"state": "observed", "value": 0}
    assert usage["fields"]["completion_tokens"] == {"state": "invalid", "value": None}
    assert usage["fields"]["total_tokens"] == {"state": "unknown", "value": None}
    assert (
        usage["raw"]["custom_counter"] == 71
        and data["native_clients_closed"]
        and data["result"] is None
    )
    assert clients["checker"].requests == []


def test_checker_cannot_support_missing_quote_then_invoke_writer(tmp_path):
    clients = transports(["openai"] * 3)
    notes = outputs()["researcher"]
    notes["claims"][0]["exact_quote"] = "invented quote not present in any source"
    clients["researcher"].body["choices"][0]["message"]["content"] = (
        "Final Answer: " + json.dumps(notes)
    )
    with pytest.raises(ValueError, match="invalid checker handoff") as error:
        asyncio.run(
            run_team_async(
                PACK,
                configs=configured(["openai"] * 3),
                transports=clients,
                output_root=tmp_path / "runs",
            )
        )
    data = json.loads(Path(error.value.receipt_path).read_text())
    assert (
        clients["writer"].requests == []
        and len(data["role_outputs"]) == 2
        and data["result"] is None
    )


def test_writer_cannot_expand_supported_candidate_authority(tmp_path):
    clients = transports(["openai"] * 3)
    brief = outputs()["writer"]
    brief["claims"][0]["text"] = "The current target is 900 minutes"
    clients["writer"].body["choices"][0]["message"]["content"] = (
        "Final Answer: " + json.dumps(brief)
    )
    result = asyncio.run(
        run_team_async(
            PACK,
            configs=configured(["openai"] * 3),
            transports=clients,
            output_root=tmp_path / "runs",
        )
    )
    assert result["status"] == "needs_review" and any(
        "not supported by the checker" in issue for issue in result["issues"]
    )


@pytest.mark.parametrize("missing", [False, True])
def test_zero_or_absent_original_usage_stays_distinct_from_crew_defaults(
    tmp_path, missing
):
    clients = transports(["openai"] * 3)
    if missing:
        clients["researcher"].body.pop("usage")
    else:
        clients["researcher"].body["usage"] = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
    result = asyncio.run(
        run_team_async(
            PACK,
            configs=configured(["openai"] * 3),
            transports=clients,
            output_root=tmp_path / "runs",
        )
    )
    data = json.loads(Path(result["receipt_path"]).read_text())
    fields = data["native"][0]["reported_usage"]["fields"]
    assert all(
        row["state"] == ("unknown" if missing else "observed")
        and row["value"] == (None if missing else 0)
        for row in fields.values()
    )
    assert data["crew_usage"] is not None and data["cost_usd"] is None


def test_failed_close_cannot_be_reclassified_as_closed_by_empty_stack_retry(tmp_path):
    class FailedClose(Transport):
        async def aclose(self):
            raise RuntimeError("controlled transport close failure")

    clients = transports(["openai"] * 3)
    clients["writer"] = FailedClose("openai", "writer")
    with pytest.raises(RuntimeError, match="close failure") as error:
        asyncio.run(
            run_team_async(
                PACK,
                configs=configured(["openai"] * 3),
                transports=clients,
                output_root=tmp_path / "runs",
            )
        )
    data = json.loads(Path(error.value.receipt_path).read_text())
    assert (
        data["status"] == "failed"
        and data["result"] is None
        and not data["native_clients_closed"]
    )


@pytest.mark.parametrize(
    "stage",
    ["prepared", "request", "response", "role", "release_prepared", "completed"],
)
def test_recording_fault_stops_later_native_work_or_supported_release(tmp_path, stage):
    clients = transports(["openai"] * 3)
    failed = False

    def writer(path, data):
        nonlocal failed
        trigger = (
            data["status"] == stage
            if stage in {"prepared", "release_prepared", "completed"}
            else bool(data["native"]) and data["native"][-1]["status"] == "prepared"
            if stage == "request"
            else bool(data["native"]) and data["native"][-1].get("response") is not None
            if stage == "response"
            else bool(data["role_outputs"])
        )
        if trigger and not failed:
            failed = True
            raise OSError("controlled recording failure")
        path.write_text(json.dumps(data))

    with pytest.raises(Exception) as error:
        asyncio.run(
            run_team_async(
                PACK,
                configs=configured(["openai"] * 3),
                transports=clients,
                output_root=tmp_path / "runs",
                writer=writer,
            )
        )
    data = json.loads(Path(error.value.receipt_path).read_text())
    assert data["status"] == "failed" and data["result"] is None
    expected = (
        0
        if stage in {"prepared", "request"}
        else 1
        if stage in {"response", "role"}
        else 3
    )
    assert sum(len(client.requests) for client in clients.values()) == expected
    if stage != "prepared":
        assert all(client.closed for client in clients.values())


def test_permanent_final_recording_fault_exposes_in_memory_failure_not_supported_result(
    tmp_path,
):
    clients = transports(["openai"] * 3)

    def writer(path, data):
        if data["status"] in {"release_prepared", "completed", "failed"}:
            raise OSError("controlled permanent recording failure")
        path.write_text(json.dumps(data))

    with pytest.raises(OSError) as error:
        asyncio.run(
            run_team_async(
                PACK,
                configs=configured(["openai"] * 3),
                transports=clients,
                output_root=tmp_path / "runs",
                writer=writer,
            )
        )
    assert (
        error.value.evidence["durable_status"] == "unknown"
        and error.value.evidence["status"] == "failed"
        and error.value.evidence["result"] is None
    )
    assert all(client.closed for client in clients.values())


def test_changed_original_source_snapshot_blocks_checker_and_retains_original_bytes(
    tmp_path,
):
    from research_team.evidence import read_pack

    source_path = tmp_path / "source.json"
    original = PACK.model_dump_json().encode()
    source_path.write_bytes(original)
    pack, source = read_pack(source_path)
    clients = transports(["openai"] * 3)

    async def change():
        source_path.write_bytes(original + b" ")

    clients["researcher"].delay = change
    with pytest.raises(ValueError, match="source pack changed") as error:
        asyncio.run(
            run_team_async(
                pack,
                source=source,
                configs=configured(["openai"] * 3),
                transports=clients,
                output_root=tmp_path / "runs",
            )
        )
    data = json.loads(Path(error.value.receipt_path).read_text())
    assert clients["checker"].requests == [] and data["result"] is None
    import base64

    assert (
        base64.b64decode(data["source_snapshot"]["original_bytes_base64"]) == original
    )
    assert source_path.read_bytes() == original + b" "


def test_ambient_missing_credentials_fail_in_prepared_receipt_without_clients(
    tmp_path, monkeypatch
):
    for role in ROLES:
        monkeypatch.delenv(role.upper() + "_API_KEY", raising=False)
        monkeypatch.delenv(role.upper() + "_MODEL", raising=False)
    monkeypatch.setenv("RESEARCH_MODEL", "openai/gpt-synthetic")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="API key") as error:
        asyncio.run(run_team_async(PACK, output_root=tmp_path / "runs"))
    data = json.loads(Path(error.value.receipt_path).read_text())
    assert (
        data["native"] == []
        and data["status"] == "failed"
        and data["native_clients_closed"]
        and data["native_bridge_closed"]
    )


def test_crewai_rate_limit_wrappers_cannot_retry_or_sleep_after_native_failure(
    tmp_path, monkeypatch
):
    def forbidden(*args, **kwargs):
        raise AssertionError("unexpected hidden CrewAI rate-limit retry")

    monkeypatch.setattr("crewai.llms.retry.get_retry_delay_seconds", forbidden)
    clients = transports(["openai"] * 3)
    clients["researcher"].status = 429
    clients["researcher"].body = {
        "error": {"type": "rate_limit_error", "message": "controlled throttling"},
        "usage": {"prompt_tokens": 7, "completion_tokens": 0, "total_tokens": 7},
    }
    with pytest.raises(Exception) as error:
        asyncio.run(
            run_team_async(
                PACK,
                configs=configured(["openai"] * 3),
                transports=clients,
                output_root=tmp_path / "runs",
            )
        )
    assert "unexpected hidden" not in str(error.value)
    data = json.loads(Path(error.value.receipt_path).read_text())
    assert (
        len(clients["researcher"].requests) == 1
        and clients["checker"].requests == []
        and clients["writer"].requests == []
    )
    assert (
        data["native"][0]["http_status"] == 429
        and data["native"][0]["reported_usage"]["fields"]["prompt_tokens"]["value"] == 7
    )
    assert (
        data["status"] == "failed"
        and data["native_clients_closed"]
        and data["native_bridge_closed"]
    )


def test_invalid_credential_value_is_not_copied_into_error_or_evidence(tmp_path):
    configs = configured(["openai"] * 3)
    configs[0] = RoleConfig(
        "researcher",
        "openai",
        "gpt-synthetic",
        "synthetic-secret\n",
        "http://127.0.0.1:19",
    )
    with pytest.raises(ValueError) as error:
        asyncio.run(
            run_team_async(PACK, configs=configs, output_root=tmp_path / "runs")
        )
    assert "synthetic-secret" not in str(error.value) + json.dumps(error.value.evidence)
