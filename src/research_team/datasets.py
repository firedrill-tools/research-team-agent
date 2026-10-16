"""Hash-bound controlled packs and exclusive private model-free workspaces."""

import json
import os
import re
import stat
import uuid
from importlib.resources import files
from pathlib import Path
from ._dataset_manifest import INDEX_SHA256
from .schema import SourcePack
from .native import strict_json
from .evidence import read_pack, sha, now

DATASET = "controlled-research-cases"
VERSION = "1.0.0"


def encoded(value):
    return (
        json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    ).encode()


def data_root():
    packaged = files("research_team").joinpath("sample_data")
    return (
        packaged if packaged.is_dir() else Path(__file__).resolve().parents[2] / "data"
    )


def read_data(root, name, maximum):
    if not re.fullmatch("[a-z0-9-]+[.]json", name):
        raise ValueError("invalid dataset filename")
    raw = root.joinpath(name).read_bytes()
    if len(raw) > maximum:
        raise ValueError("dataset exceeds supported retained bytes")
    return raw


def index(root=None):
    raw = read_data(root or data_root(), "index.json", 65536)
    if sha(raw) != INDEX_SHA256:
        raise ValueError("dataset index hash differs from source authority")
    value = strict_json(raw)
    if (
        value.get("schema_version") != 1
        or value.get("dataset") != DATASET
        or value.get("version") != VERSION
        or not isinstance(value.get("cases"), list)
        or not 1 <= len(value["cases"]) <= 100
    ):
        raise ValueError("unsupported dataset index")
    return value


def load_case(identifier, root=None):
    root = root or data_root()
    manifest = index(root)
    entry = next(
        (row for row in manifest["cases"] if row["case_id"] == identifier), None
    )
    if entry is None:
        raise ValueError("unknown research dataset case")
    raw = read_data(root, entry["file"], 2 * 1048576)
    if sha(raw) != entry["sha256"]:
        raise ValueError("dataset case hash differs from index")
    case = strict_json(raw)
    if (
        case.get("schema_version") != 1
        or case.get("dataset") != DATASET
        or case.get("version") != VERSION
        or case.get("case_id") != identifier
        or case.get("profile") != entry["profile"]
    ):
        raise ValueError("unsupported dataset case")
    SourcePack.model_validate(case["pack"])
    return case, entry


def list_cases(root=None):
    manifest = index(root)
    for row in manifest["cases"]:
        load_case(row["case_id"], root)
    return manifest


def write_private(path, raw):
    with path.open("xb") as file:
        os.chmod(path, 0o600)
        file.write(raw)
        file.flush()
        os.fsync(file.fileno())


def initialize_workspace(identifier, directory, root=None):
    case, entry = load_case(identifier, root)
    directory = Path(os.path.abspath(directory))
    directory.mkdir(mode=0o700)
    raw = encoded(case["pack"])
    identity = {
        "schema_version": 1,
        "dataset": DATASET,
        "version": VERSION,
        "case_id": identifier,
        "case_sha256": entry["sha256"],
        "index_sha256": INDEX_SHA256,
        "seed_pack_sha256": sha(raw),
        "instance_id": str(uuid.uuid4()),
        "initialized_at": now(),
    }
    write_private(directory / "pack.json", raw)
    write_private(
        directory / "TASK.md",
        (case["task"] + "\n\n" + case["provenance"] + "\n").encode(),
    )
    write_private(directory / "workspace.json", encoded(identity))
    return inspect_workspace(directory, root)


def inspect_workspace(directory, root=None):
    directory = Path(os.path.abspath(directory))
    path = directory / "workspace.json"
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 65536:
        raise ValueError("workspace identity requires a bounded regular file")
    identity = strict_json(path.read_bytes())
    if (
        set(identity)
        != {
            "schema_version",
            "dataset",
            "version",
            "case_id",
            "case_sha256",
            "index_sha256",
            "seed_pack_sha256",
            "instance_id",
            "initialized_at",
        }
        or identity["schema_version"] != 1
        or identity["dataset"] != DATASET
        or identity["version"] != VERSION
        or identity["index_sha256"] != INDEX_SHA256
    ):
        raise ValueError("unsupported workspace identity")
    if (
        str(uuid.UUID(identity["instance_id"])) != identity["instance_id"]
        or uuid.UUID(identity["instance_id"]).version != 4
    ):
        raise ValueError("invalid workspace instance")
    case, entry = load_case(identity["case_id"], root)
    if identity["case_sha256"] != entry["sha256"] or identity[
        "seed_pack_sha256"
    ] != sha(encoded(case["pack"])):
        raise ValueError("workspace dataset identity changed")
    pack, current = read_pack(directory / "pack.json")
    return {
        "directory": str(directory),
        "pack": str(directory / "pack.json"),
        "identity": identity,
        "current_pack_sha256": current["sha256"],
        "matches_seed": current["sha256"] == identity["seed_pack_sha256"],
        "sources": len(pack.sources),
        "topics": sorted({row.topic for row in pack.sources}),
        "focus_topics": pack.focus_topics,
    }


def reset_workspace(directory, destination, instance, root=None):
    original = inspect_workspace(directory, root)
    if original["identity"]["instance_id"] != instance:
        raise ValueError("reset source instance is no longer current")
    return initialize_workspace(original["identity"]["case_id"], destination, root)
