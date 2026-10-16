"""Fresh locked installed teams and complete archived test suite outside checkout."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
from pathlib import Path
from zipfile import ZipFile
from package_source import build

ROOT = Path(__file__).resolve().parents[1]
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
UV = os.environ.get("UV") or shutil.which("uv")
if not UV:
    raise RuntimeError("uv is required")
ENV = {**os.environ, "OTEL_SDK_DISABLED": "true", "CREWAI_TELEMETRY_DISABLED": "true"}
for key in (
    "OPENAI_API_KEY",
    "OPENAI_ORG_ID",
    "OPENAI_PROJECT_ID",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_GENAI_USE_VERTEXAI",
    "GOOGLE_GENAI_USE_ENTERPRISE",
    "RESEARCH_MODEL",
    "VIRTUAL_ENV",
    "PYTHONPATH",
    "PYTHONHOME",
):
    ENV.pop(key, None)
for role in ("RESEARCHER", "CHECKER", "WRITER"):
    for suffix in ("_MODEL", "_API_KEY", "_BASE_URL"):
        ENV.pop(role + suffix, None)


def run(command, cwd, check=True):
    result = subprocess.run(
        [str(x) for x in command],
        cwd=cwd,
        env=ENV,
        capture_output=True,
        text=True,
        timeout=240,
    )
    if check and result.returncode:
        raise RuntimeError(
            f"command failed: {command[0]}\n{result.stdout[-12000:]}\n{result.stderr[-12000:]}"
        )
    return result


PROGRAM = r"""
import json,os,subprocess,sys,threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import research_team
from research_team.datasets import list_cases,initialize_workspace,inspect_workspace,reset_workspace
from research_team.evidence import read_pack
base=Path(sys.argv[1]);assert Path(research_team.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
manifest=list_cases();assert len(manifest['cases'])==12
for case in manifest['cases']:
 result=initialize_workspace(case['case_id'],base/case['case_id']);assert result['identity']['case_sha256']==case['sha256'] and Path(result['pack']).stat().st_mode&0o777==0o600
busy=inspect_workspace(base/'busy-handbooks');assert busy['sources']==36 and len(busy['topics'])==12 and len(busy['focus_topics'])==2
fresh=reset_workspace(base/'busy-handbooks',base/'fresh',busy['identity']['instance_id']);assert fresh['identity']['instance_id']!=busy['identity']['instance_id']
pack,_=read_pack(base/'consistent-guidance/pack.json');source=pack.sources[0]
claim={'text':source.title+' records '+source.fact_value,'source_id':source.source_id,'exact_quote':source.text}
outputs=[{'claims':[claim],'gaps':[]},{'reviews':[{'claim_index':0,'disposition':'supported','reason':'Original quote observed'}],'conflicts':[],'gaps':[]},{'question':pack.question,'answer':'Controlled installed team brief','claims':[claim],'conflicts':[],'uncertainties':[]}]
requests=[]
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_POST(self):
  body=json.loads(self.rfile.read(int(self.headers['Content-Length'])));index=len(requests);requests.append(body)
  raw=json.dumps({'id':f'chatcmpl_dist_{index}','object':'chat.completion','created':1792144800,'model':'gpt-observed-dist','choices':[{'index':0,'message':{'role':'assistant','content':'Final Answer: '+json.dumps(outputs[index])},'finish_reason':'stop'}],'usage':{'prompt_tokens':11,'completion_tokens':5,'total_tokens':16}}).encode()
  self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.daemon_threads=True;thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
cli=[sys.executable,'-I','-m','research_team',str(base/'consistent-guidance/pack.json'),'--output-root',str(base/'runs'),'--output',str(base/'qualified.report.json')]
env={**os.environ,'RESEARCH_MODEL':'openai/gpt-synthetic-dist','OPENAI_API_KEY':'synthetic-dist-key'}
for role in ('researcher','checker','writer'):cli.extend(['--'+role+'-base-url',f'http://127.0.0.1:{server.server_port}/v1'])
try:
 result=subprocess.run(cli,env=env,capture_output=True,text=True,timeout=30)
 assert result.returncode==0,result.stderr
 report=json.loads(result.stdout);assert report['status']=='supported' and len(requests)==3
 receipt=json.loads(Path(report['receipt_path']).read_text());assert receipt['native_clients_closed'] and receipt['native_bridge_closed'] and len(receipt['role_outputs'])==3
 assert Path(base/'qualified.report.json').stat().st_mode&0o777==0o600
 assert all(row['response_model']=='gpt-observed-dist' for row in receipt['native'])
finally:server.shutdown();server.server_close();thread.join(2)
print('installed twelve cases/private reset and real three-role native CLI HTTP passed')
"""


def exercise(python, base):
    base.mkdir()
    run([python.parent / "research-team", "--help"], base)
    manifest = json.loads(
        run([python, "-I", "-m", "research_team", "datasets"], base).stdout
    )
    assert len(manifest["cases"]) == 12
    run([python, "-I", "-c", PROGRAM, base], base)
    cli = [
        python,
        "-I",
        "-m",
        "research_team",
        base / "consistent-guidance/pack.json",
        "--output-root",
        base / "missing-key-runs",
    ]
    for role in ("researcher", "checker", "writer"):
        cli.extend(["--" + role + "-model", "openai/gpt-synthetic-dist"])
    preflight = run(cli, base, False)
    assert preflight.returncode == 1
    failure = json.loads(preflight.stderr)
    receipt = json.loads(Path(failure["receipt_path"]).read_text())
    assert (
        receipt["status"] == "failed"
        and receipt["native"] == []
        and receipt["role_outputs"] == []
    )


def extract(path, destination):
    destination.mkdir()
    with tarfile.open(path) as archive:
        assert all(member.isfile() or member.isdir() for member in archive.getmembers())
        archive.extractall(destination, filter="data")
    (source,) = destination.iterdir()
    return source


def verify_source(source):
    manifest = json.loads((source / "source-manifest.json").read_text())
    assert {
        str(path.relative_to(source)) for path in source.rglob("*") if path.is_file()
    } == {row["path"] for row in manifest["files"]} | {"source-manifest.json"}
    for row in manifest["files"]:
        path = source / row["path"]
        assert (
            hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"]
            and path.stat().st_size == row["bytes"]
            and path.stat().st_mode & 0o777 == row["mode"]
        )
    return manifest


def main():
    wheel = ROOT / "dist" / f"research_team_agent-{VERSION}-py3-none-any.whl"
    sdist = ROOT / "dist" / f"research_team_agent-{VERSION}.tar.gz"
    bundle = build()
    with tempfile.TemporaryDirectory(prefix="research-team-distribution-") as directory:
        temp = Path(directory)
        assert not temp.is_relative_to(ROOT)
        assert build(temp / "repeat.tar.gz")["sha256"] == bundle["sha256"]
        with ZipFile(wheel) as archive:
            assert (
                len(
                    [
                        name
                        for name in archive.namelist()
                        if name.startswith("research_team/sample_data/")
                        and name.endswith(".json")
                    ]
                )
                == 13
            )
        requirements = temp / "requirements.txt"
        requirements.write_text(
            run(
                [
                    UV,
                    "export",
                    "--locked",
                    "--extra",
                    "test",
                    "--no-dev",
                    "--no-emit-project",
                    "--format",
                    "requirements-txt",
                ],
                ROOT,
            ).stdout
        )
        environment = temp / "wheel-env"
        run([UV, "venv", "--python", sys.executable, environment], temp)
        python = environment / "bin/python"
        run([UV, "pip", "sync", "--python", python, requirements], temp)
        run([UV, "pip", "install", "--python", python, "--no-deps", wheel], temp)
        exercise(python, temp / "wheel-case")
        source = extract(sdist, temp / "sdist")
        assert all(
            (source / name).exists()
            for name in (
                "uv.lock",
                "data/index.json",
                "tests/test_native_cli.py",
                "scripts/build_datasets.py",
                ".github/workflows/check.yml",
                "COMPATIBILITY.md",
            )
        )
        run(
            [
                UV,
                "sync",
                "--locked",
                "--extra",
                "test",
                "--no-editable",
                "--project",
                source,
            ],
            temp,
        )
        exercise(source / ".venv/bin/python", temp / "sdist-case")
        run(
            [source / ".venv/bin/python", "scripts/build_datasets.py", "--check"],
            source,
        )
        complete = extract(bundle["path"], temp / "complete")
        manifest = verify_source(complete)
        run(
            [
                UV,
                "sync",
                "--locked",
                "--extra",
                "test",
                "--no-editable",
                "--project",
                complete,
            ],
            temp,
        )
        exercise(complete / ".venv/bin/python", temp / "complete-case")
        run(
            [complete / ".venv/bin/python", "scripts/build_datasets.py", "--check"],
            complete,
        )
        suite = run([complete / ".venv/bin/python", "-m", "pytest", "-q"], complete)
        assert "89 passed" in suite.stdout, suite.stdout
        for row in manifest["files"]:
            assert (
                hashlib.sha256((complete / row["path"]).read_bytes()).hexdigest()
                == row["sha256"]
            )
    report = {
        **bundle,
        "checks": "fresh locked wheel/sdist/complete source, twelve private cases/reset, actual installed native three-role HTTP, missing-key receipts, complete89 suite",
    }
    (ROOT / "dist/qualification.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
