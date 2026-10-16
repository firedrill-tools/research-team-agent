"""Run an owned CrewAI team over a local source snapshot with private failure proof."""

import argparse
import asyncio
import json
import logging
import os
import signal
import sys
import uuid
from pathlib import Path
from .evidence import read_pack
from .native import ROLES
from .worker import run_team_async
from .datasets import (
    list_cases,
    initialize_workspace,
    inspect_workspace,
    reset_workspace,
)


def save_report(path, value):
    staged = path.with_name("." + str(uuid.uuid4()) + ".tmp")
    try:
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
        os.link(
            staged, path
        )  # Exclusive atomic publication, including concurrent path collision.
        fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        staged.unlink(missing_ok=True)


async def execute(pack, source, args):
    loop = asyncio.get_running_loop()
    task = asyncio.current_task()
    seen = []
    previous = {}

    def stop(number, frame):
        if not seen:
            seen.append(number)
            task.cancel(f"Received {signal.Signals(number).name}")
            loop.call_soon_threadsafe(lambda: None)

    for name in ("SIGINT", "SIGTERM", "SIGHUP"):
        if hasattr(signal, name):
            number = getattr(signal, name)
            previous[number] = signal.getsignal(number)
            signal.signal(number, stop)
    try:
        result = await run_team_async(
            pack,
            source=source,
            output_root=args.output_root,
            timeout_seconds=args.timeout_seconds,
            role_models={role: getattr(args, role + "_model") for role in ROLES},
            role_base_urls={role: getattr(args, role + "_base_url") for role in ROLES},
        )
        return result, 0 if result["status"] == "supported" else 2
    except asyncio.CancelledError as error:
        number = seen[0] if seen else None
        return {
            "status": "interrupted",
            "signal": signal.Signals(number).name if number else None,
            "receipt_path": getattr(error, "receipt_path", None),
        }, 128 + number if number else 130
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


def main():
    # The CLI emits one JSON result; original native diagnostics remain in its private trace.
    logging.disable(logging.CRITICAL)
    arguments = sys.argv[1:]
    if arguments and arguments[0] in {"datasets", "init", "workspace", "reset"}:
        parser = argparse.ArgumentParser(
            description="Private model-free research workspaces"
        )
        commands = parser.add_subparsers(dest="command", required=True)
        commands.add_parser("datasets")
        initialize = commands.add_parser("init")
        initialize.add_argument("--case", required=True)
        initialize.add_argument("--directory", required=True, type=Path)
        inspect = commands.add_parser("workspace")
        inspect.add_argument("directory", type=Path)
        reset = commands.add_parser("reset")
        reset.add_argument("directory", type=Path)
        reset.add_argument("--to", required=True, type=Path)
        reset.add_argument("--instance", required=True)
        args = parser.parse_args(arguments)
        if args.command == "datasets":
            result = list_cases()
        elif args.command == "init":
            result = initialize_workspace(args.case, args.directory)
        elif args.command == "workspace":
            result = inspect_workspace(args.directory)
        else:
            result = reset_workspace(args.directory, args.to, args.instance)
        print(json.dumps(result, indent=2))
        return 0
    parser = argparse.ArgumentParser(
        description="Controlled-source CrewAI research team"
    )
    parser.add_argument("pack", type=Path)
    parser.add_argument("--output", type=Path, help="exclusive private report file")
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--timeout-seconds", type=float, default=120)
    for role in ROLES:
        parser.add_argument("--" + role + "-model", help="explicit provider/model")
        parser.add_argument(
            "--" + role + "-base-url", help="explicit HTTPS or loopback HTTP endpoint"
        )
    args = parser.parse_args()
    if args.output is not None and os.path.lexists(args.output):
        raise FileExistsError("report path already exists")
    pack, source = read_pack(args.pack)
    result, code = asyncio.run(execute(pack, source, args))
    if args.output is not None:
        try:
            save_report(args.output, result)
        except Exception as error:
            error.receipt_path = result.get("receipt_path")
            raise
    print(json.dumps(result, indent=2, allow_nan=False))
    return code


def cli():
    try:
        return main()
    except Exception as error:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error": {"name": type(error).__name__, "message": str(error)},
                    "receipt_path": getattr(error, "receipt_path", None),
                }
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(cli())
