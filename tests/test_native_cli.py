import json
import os
import signal
import subprocess
import sys
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import pytest
from test_native import response
from research_team.native import ROLES

ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def server(providers, stop=False, block=False):
    requests = []
    ready = threading.Event()
    release = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            index = len(requests)
            role = ROLES[index]
            provider = providers[index]
            requests.append(
                {
                    "role": role,
                    "provider": provider,
                    "body": body,
                    "headers": dict(self.headers),
                    "path": self.path,
                }
            )
            ready.set()
            if block:
                release.wait(15)
            raw = json.dumps(
                response(
                    provider, role, "length" if stop and provider == "openai" else None
                )
            ).encode()
            try:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
            except (BrokenPipeError, ConnectionResetError):
                pass

    service = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    service.daemon_threads = True
    thread = threading.Thread(target=service.serve_forever, daemon=True)
    thread.start()
    try:
        yield {
            "url": f"http://127.0.0.1:{service.server_port}",
            "requests": requests,
            "ready": ready,
            "release": release,
        }
    finally:
        release.set()
        service.shutdown()
        service.server_close()
        thread.join(2)


def environment():
    env = {
        **os.environ,
        "OTEL_SDK_DISABLED": "true",
        "CREWAI_TELEMETRY_DISABLED": "true",
        "HTTP_PROXY": "http://127.0.0.1:1",
        "HTTPS_PROXY": "http://127.0.0.1:1",
        "NO_PROXY": "",
    }
    for key in (
        "RESEARCH_MODEL",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "GOOGLE_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_GENAI_USE_VERTEXAI",
        "GOOGLE_GENAI_USE_ENTERPRISE",
    ):
        env.pop(key, None)
    for role in ROLES:
        for suffix in ("_MODEL", "_API_KEY", "_BASE_URL"):
            env.pop(role.upper() + suffix, None)
    return env


def command(tmp_path, service, providers):
    models = {
        "openai": "gpt-synthetic",
        "anthropic": "claude-synthetic",
        "gemini": "gemini-synthetic",
    }
    result = [
        sys.executable,
        "-m",
        "research_team",
        str(ROOT / "fixtures/policy-conflict.json"),
        "--output-root",
        str(tmp_path / "runs"),
    ]
    for role, provider in zip(ROLES, providers):
        result.extend(
            [
                "--" + role + "-model",
                provider + "/" + models[provider],
                "--" + role + "-base-url",
                service["url"] + ("/v1" if provider == "openai" else ""),
            ]
        )
    return result


@pytest.mark.parametrize(
    "providers,stop",
    [
        (["openai"] * 3, False),
        (["gemini", "openai", "anthropic"], False),
        (["openai"] * 3, True),
    ],
)
def test_normal_cli_native_http_per_role_and_original_terminal_authority(
    tmp_path, providers, stop
):
    env = environment()
    for role in ROLES:
        env[role.upper() + "_API_KEY"] = "synthetic-cli-" + role
    # Explicit keys and owned transports must not borrow ambient alternative auth or proxies.
    env["ANTHROPIC_AUTH_TOKEN"] = "ambient-should-not-be-used"
    env["OPENAI_ORG_ID"] = "ambient-org"
    env["OPENAI_PROJECT_ID"] = "ambient-project"
    with server(providers, stop=stop) as service:
        child = subprocess.run(
            command(tmp_path, service, providers),
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
        )
        assert child.returncode == (1 if stop else 0), child.stdout + child.stderr
        result = json.loads(child.stderr if stop else child.stdout)
        data = json.loads(Path(result["receipt_path"]).read_text())
        assert (
            data["status"] == ("failed" if stop else "completed")
            and data["native_clients_closed"]
            and data["native_bridge_closed"]
        )
        assert len(service["requests"]) == (1 if stop else 3)
        assert "synthetic-cli-" not in json.dumps(data)
        if not stop:
            assert result["status"] == "supported" and [
                row["role"] for row in data["role_outputs"]
            ] == list(ROLES)
            assert all(
                path.stat().st_mode & 0o777 == 0o600
                for path in Path(result["receipt_path"]).parent.iterdir()
                if path.is_file()
            )
            for item in service["requests"]:
                headers = {k.lower(): v for k, v in item["headers"].items()}
                assert (
                    "openai-organization" not in headers
                    and "openai-project" not in headers
                )
                if item["provider"] == "anthropic":
                    assert (
                        "authorization" not in headers
                        and headers["x-api-key"] == "synthetic-cli-writer"
                    )


@pytest.mark.parametrize("name", ["SIGINT", "SIGTERM", "SIGHUP"])
def test_normal_cli_signal_drains_worker_thread_bridge_and_native_http(tmp_path, name):
    env = environment()
    for role in ROLES:
        env[role.upper() + "_API_KEY"] = "synthetic-key"
    with server(["openai"] * 3, block=True) as service:
        child = subprocess.Popen(
            command(tmp_path, service, ["openai"] * 3),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            assert service["ready"].wait(10)
            child.send_signal(getattr(signal, name))
            stdout, stderr = child.communicate(timeout=8)
            assert child.returncode == 128 + int(getattr(signal, name)), stderr
            result = json.loads(stdout)
            data = json.loads(Path(result["receipt_path"]).read_text())
            assert result["status"] == "interrupted" and result["signal"] == name
            assert (
                data["status"] == "failed"
                and data["native_clients_closed"]
                and data["native_bridge_closed"]
                and data["result"] is None
            )
            assert (
                len(service["requests"]) == 1
                and data["native"][0]["status"] == "failed"
            )
        finally:
            if child.poll() is None:
                child.kill()
                child.communicate(timeout=2)


def test_missing_key_writes_failed_prepared_receipt_without_provider_calls(tmp_path):
    with server(["openai"] * 3) as service:
        child = subprocess.run(
            command(tmp_path, service, ["openai"] * 3),
            env=environment(),
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert child.returncode == 1
        result = json.loads(child.stderr)
        data = json.loads(Path(result["receipt_path"]).read_text())
        assert (
            data["status"] == "failed"
            and data["native"] == []
            and data["role_outputs"] == []
            and service["requests"] == []
        )


def test_existing_report_is_preserved_before_native_dispatch(tmp_path):
    output = tmp_path / "kept.report.json"
    output.write_text("existing human report")
    with server(["openai"] * 3) as service:
        child = subprocess.run(
            [*command(tmp_path, service, ["openai"] * 3), "--output", str(output)],
            env=environment(),
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert (
            child.returncode == 1
            and output.read_text() == "existing human report"
            and service["requests"] == []
        )
