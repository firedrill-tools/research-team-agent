"""Private prepared/final role evidence and bounded source snapshot continuity."""

import asyncio
import base64
import hashlib
import json
import os
import stat
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from .schema import SourcePack
from .native import strict_json


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(value):
    return hashlib.sha256(
        value
        if isinstance(value, bytes)
        else json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def read_pack(path):
    path = Path(os.path.abspath(path))
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_size > 1048576:
        raise ValueError("source pack requires a bounded regular local file")
    raw = path.read_bytes()
    after = path.lstat()
    if len(raw) > 1048576 or (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    ) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        raise ValueError("source changed during snapshot read")
    pack = SourcePack.model_validate(strict_json(raw))
    return pack, {
        "path": str(path),
        "sha256": sha(raw),
        "bytes": len(raw),
        "device": after.st_dev,
        "inode": after.st_ino,
        "original_bytes_base64": base64.b64encode(raw).decode(),
    }


class Receipt:
    sha = staticmethod(sha)

    def __init__(self, pack, configs, output_root, timeout, source=None, writer=None):
        self.deadline = time.monotonic() + timeout
        self.writer = writer
        self.recording_error = None
        self.failure = None
        self.stopping = False
        root = Path(output_root or ".runs")
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        directory = root / str(uuid.uuid4())
        directory.mkdir(mode=0o700)
        self.path = directory / "trace.json"
        self.data = {
            "schema_version": 1,
            "run_id": directory.name,
            "status": "prepared",
            "started_at": now(),
            "source_snapshot": source,
            "pack": pack.model_dump(mode="json"),
            "pack_sha256": sha(pack.model_dump(mode="json")),
            "roles": [config.public() for config in configs],
            "native": [],
            "role_outputs": [],
            "crew_usage": None,
            "native_clients_closed": False,
            "result": None,
            "error": None,
            "cost_usd": None,
        }

    def guard(self):
        if self.stopping:
            raise asyncio.CancelledError("research is stopping")
        try:
            task = asyncio.current_task()
        except RuntimeError:
            task = None
        if task is not None and task.cancelling():
            raise asyncio.CancelledError("research cancellation requested")
        if self.recording_error:
            raise self.recording_error
        if self.failure:
            raise RuntimeError(
                "a prior native boundary failed; role work cannot continue"
            ) from self.failure
        if time.monotonic() >= self.deadline:
            raise TimeoutError("research operation deadline exceeded")

    def source_guard(self):
        source = self.data["source_snapshot"]
        if source is not None:
            live, current = read_pack(source["path"])
            if sha(live.model_dump(mode="json")) != self.data["pack_sha256"]:
                raise ValueError("model pack differs from original source snapshot")
            if any(
                current[key] != source[key] for key in ("sha256", "device", "inode")
            ):
                raise ValueError("original source pack changed during research")

    def save(self, final=False):
        if self.recording_error and not final:
            raise self.recording_error
        staged = self.path.with_name("." + str(uuid.uuid4()) + ".tmp")
        try:
            value = json.loads(json.dumps(self.data, allow_nan=False))
            if self.writer is not None:
                self.writer(self.path, value)
                return
            with staged.open("xb") as file:
                os.chmod(staged, 0o600)
                file.write(
                    (
                        json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)
                        + "\n"
                    ).encode()
                )
                file.flush()
                os.fsync(file.fileno())
            os.replace(staged, self.path)
            fd = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        except BaseException as error:
            self.recording_error = error
            raise
        finally:
            staged.unlink(missing_ok=True)

    def finish(self, result, failure):
        self.data.update(
            status="failed" if failure else "completed",
            finished_at=now(),
            result=None if failure else result,
        )
        if failure:
            for item in self.data["native"]:
                if item["status"] in {"prepared", "received"}:
                    item.update(
                        status="failed",
                        error={"name": type(failure).__name__, "message": str(failure)},
                    )
            chain = []
            current = failure
            while current is not None and len(chain) < 5:
                chain.append(
                    {
                        "name": type(current).__name__,
                        "message": str(current),
                        "status_code": getattr(current, "status_code", None),
                    }
                )
                current = current.__cause__
            self.data["error"] = {
                "name": type(failure).__name__,
                "message": str(failure),
                "causes": chain,
            }
        self.save(final=True)
