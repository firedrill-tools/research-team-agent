import asyncio
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
import pytest
from research_team.datasets import (
    list_cases,
    load_case,
    initialize_workspace,
    inspect_workspace,
    reset_workspace,
    data_root,
)
from research_team.schema import SourcePack, ResearchBrief
from research_team.evidence import read_pack
from research_team.worker import run_team_async
from research_team.native import ROLES
from test_native import configured, transports


def controlled_outputs(pack):
    focus = set(pack.focus_topics or [source.topic for source in pack.sources])
    active = [row for row in pack.sources if row.topic in focus]
    chosen = []
    for topic in sorted(focus):
        source = next((row for row in active if row.topic == topic), None)
        if source:
            chosen.append(
                {
                    "text": f"{source.title} records {source.fact_value}",
                    "source_id": source.source_id,
                    "exact_quote": source.text,
                }
            )
    conflicts = []
    for index, left in enumerate(active):
        for right in active[index + 1 :]:
            if left.topic == right.topic and left.fact_value != right.fact_value:
                conflicts.append(
                    {
                        "source_ids": [left.source_id, right.source_id],
                        "explanation": "The supplied tagged values differ across these editions",
                    }
                )
    gaps = [
        f"No supplied source for requested topic: {topic}"
        for topic in sorted(focus - {row.topic for row in active})
    ]
    return {
        "researcher": {"claims": chosen, "gaps": gaps},
        "checker": {
            "reviews": [
                {
                    "claim_index": index,
                    "disposition": "supported",
                    "reason": "Exact source anchor observed; semantic entailment still requires judgment",
                }
                for index in range(len(chosen))
            ],
            "conflicts": conflicts,
            "gaps": gaps,
        },
        "writer": {
            "question": pack.question,
            "answer": "Controlled structural brief from the supplied fictional records. Semantic judgments remain outside this test.",
            "claims": chosen,
            "conflicts": conflicts,
            "uncertainties": gaps,
        },
    }


@pytest.mark.parametrize(
    "identifier", [row["case_id"] for row in list_cases()["cases"]]
)
def test_every_case_initializes_private_preserving_exact_seed_facts(
    tmp_path, identifier
):
    case, entry = load_case(identifier)
    result = initialize_workspace(identifier, tmp_path / identifier)
    directory = Path(result["directory"])
    pack, source = read_pack(result["pack"])
    assert pack.model_dump(mode="json") == case["pack"]
    assert (
        result["identity"]["case_sha256"] == entry["sha256"] and result["matches_seed"]
    )
    assert directory.stat().st_mode & 0o777 == 0o700
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in directory.iterdir())
    assert case["task"] in (directory / "TASK.md").read_text()
    assert inspect_workspace(directory) == result


@pytest.mark.parametrize(
    "identifier", [row["case_id"] for row in list_cases()["cases"]]
)
def test_every_pack_qualifies_actual_native_three_role_source_scope_and_handoff(
    tmp_path, identifier
):
    initialized = initialize_workspace(identifier, tmp_path / identifier)
    pack, source = read_pack(initialized["pack"])
    outputs = controlled_outputs(pack)
    clients = transports(["openai"] * 3)
    for role in ROLES:
        clients[role].body["choices"][0]["message"]["content"] = (
            "Final Answer: " + json.dumps(outputs[role])
        )
    result = asyncio.run(
        run_team_async(
            pack,
            source=source,
            configs=configured(["openai"] * 3),
            transports=clients,
            output_root=tmp_path / "runs",
        )
    )
    assert result["status"] == (
        "needs_review" if identifier == "missing-topic" else "supported"
    )
    assert all(
        client.closed and len(client.requests) == 1 for client in clients.values()
    )
    receipt = json.loads(Path(result["receipt_path"]).read_text())
    assert receipt["native_bridge_closed"] and receipt["native_clients_closed"]
    case, _ = load_case(identifier)
    sent = json.dumps([client.requests for client in clients.values()])
    assert (
        case["task"] not in sent
        and "case_sha256" not in sent
        and initialized["identity"]["instance_id"] not in sent
    )
    if identifier == "busy-handbooks":
        assert (
            len(pack.sources) == 36 and len({row.topic for row in pack.sources}) == 12
        )
        assert (
            len(result["brief"]["conflicts"]) == 5
            and len(result["brief"]["claims"]) == 2
        )
        assert (
            "audit-export" in sent
        )  # Irrelevant source remains visible, never promoted into answer authority.
    if identifier == "hostile-import":
        assert "UNTRUSTED IMPORT" in sent
    if identifier == "maximum-source-count":
        assert len(pack.sources) == 64


def test_busy_editions_are_coherent_and_prior_observations_are_truthfully_unavailable():
    case, _ = load_case("busy-handbooks")
    pack = SourcePack.model_validate(case["pack"])
    assert (
        len(pack.sources) == 36 and len({row.source_id for row in pack.sources}) == 36
    )
    for topic in {row.topic for row in pack.sources}:
        rows = [row for row in pack.sources if row.topic == topic]
        assert [row.as_of for row in rows] == ["2025-06-01", "2026-03-01", "2026-09-01"]
        assert all(row.fact_value in row.text for row in rows)
    assert (
        "No prior model" in case["provenance"]
        and "usage" not in case
        and "provider_observations" not in case
    )


@pytest.mark.parametrize("index_changed", [False, True])
def test_corrupt_source_manifest_is_rejected_before_creating_workspace(
    tmp_path, index_changed
):
    root = tmp_path / "data"
    shutil.copytree(data_root(), root)
    path = root / ("index.json" if index_changed else "incident-target.json")
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="hash differs"):
        initialize_workspace("incident-target", tmp_path / "uncreated", root)
    assert not (tmp_path / "uncreated").exists()
    with pytest.raises(ValueError, match="hash differs"):
        list_cases(root)


def test_keyfree_cli_init_readback_reset_preserves_collisions_and_old_work(tmp_path):
    env = {
        **os.environ,
        "OTEL_SDK_DISABLED": "true",
        "CREWAI_TELEMETRY_DISABLED": "true",
    }
    for key in (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
        "GEMINI_API_KEY",
        "RESEARCH_MODEL",
    ):
        env.pop(key, None)
    for role in ROLES:
        for suffix in ("_API_KEY", "_MODEL"):
            env.pop(role.upper() + suffix, None)

    def cli(*args):
        return subprocess.run(
            [sys.executable, "-m", "research_team", *args],
            env=env,
            cwd=tmp_path,
            text=True,
            capture_output=True,
            timeout=12,
        )

    listed = cli("datasets")
    assert listed.returncode == 0, listed.stderr
    assert (
        len(json.loads(listed.stdout)["cases"]) == 12
        and not (tmp_path / ".runs").exists()
    )
    initialized = cli(
        "init", "--case", "busy-handbooks", "--directory", str(tmp_path / "workspace")
    )
    assert initialized.returncode == 0, initialized.stderr
    value = json.loads(initialized.stdout)
    directory = Path(value["directory"])
    before = {x.name: x.read_bytes() for x in directory.iterdir()}
    assert (
        cli(
            "init", "--case", "incident-target", "--directory", str(directory)
        ).returncode
        == 1
    )
    inspected = cli("workspace", str(directory))
    assert inspected.returncode == 0 and json.loads(inspected.stdout) == value
    bad = cli(
        "reset", str(directory), "--to", str(tmp_path / "bad"), "--instance", "stale"
    )
    assert bad.returncode == 1 and not (tmp_path / "bad").exists()
    reset = cli(
        "reset",
        str(directory),
        "--to",
        str(tmp_path / "fresh"),
        "--instance",
        value["identity"]["instance_id"],
    )
    assert reset.returncode == 0, reset.stderr
    fresh = json.loads(reset.stdout)
    assert (
        fresh["identity"]["instance_id"] != value["identity"]["instance_id"]
        and fresh["matches_seed"]
        and fresh["sources"] == 36
    )
    assert {x.name: x.read_bytes() for x in directory.iterdir()} == before


def test_readback_distinguishes_valid_changed_input_from_seed_and_refuses_invalid_source(
    tmp_path,
):
    initial = initialize_workspace("consistent-guidance", tmp_path / "workspace")
    path = Path(initial["pack"])
    pack, _ = read_pack(path)
    pack.question = "Changed human research question"
    path.write_text(pack.model_dump_json())
    inspected = inspect_workspace(initial["directory"])
    assert (
        inspected["matches_seed"] is False
        and inspected["identity"] == initial["identity"]
    )
    path.write_text("{malformed")
    before = path.read_bytes()
    with pytest.raises(ValueError):
        inspect_workspace(initial["directory"])
    assert path.read_bytes() == before
    path.unlink()
    with pytest.raises(FileNotFoundError):
        inspect_workspace(initial["directory"])
    assert not path.exists()


def test_case_regeneration_is_exact_without_git():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, str(root / "scripts/build_datasets.py"), "--check"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stdout + result.stderr
