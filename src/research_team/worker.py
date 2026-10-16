"""Native async CrewAI role collaboration with independent handoff/source authority."""

import asyncio
import math
from contextlib import AsyncExitStack
from .schema import SourcePack, ResearchNotes, CheckReport, ResearchBrief
from .native import ROLES, from_environment, create_role
from .evidence import Receipt
from .team import build_crew, _raw_json, grade_brief, grade_handoff
from .bridge import NativeBridge, NativeAbort


async def run_team_async(
    pack,
    *,
    configs=None,
    output_root=None,
    timeout_seconds=120,
    source=None,
    writer=None,
    transports=None,
    role_models=None,
    role_base_urls=None,
):
    if (
        type(timeout_seconds) not in (int, float)
        or not 0 < timeout_seconds <= 300
        or not math.isfinite(timeout_seconds)
    ):
        raise ValueError("research timeout must be finite and in (0,300]")
    pack = SourcePack.model_validate(pack).model_copy(deep=True)
    receipt = Receipt(
        pack, [], output_root, timeout_seconds, source=source, writer=writer
    )
    bridge = NativeBridge(receipt)
    stack = AsyncExitStack()
    close_attempted = False
    result = None
    failure = None
    outputs = {}
    boundaries = {}

    def callback(role):
        def record(output):
            receipt.guard()
            receipt.source_guard()
            original = str(output.raw)
            item = {
                "role": role,
                "raw": original,
                "raw_sha256": receipt.sha(original.encode()),
                "parsed": None,
            }
            receipt.data["role_outputs"].append(item)
            receipt.save()
            receipt.guard()
            boundary = boundaries[role]
            if (
                boundary.observation is None
                or boundary.observation["status"] != "accepted"
            ):
                raise ValueError("role lacks an accepted original native completion")
            model = {
                "researcher": ResearchNotes,
                "checker": CheckReport,
                "writer": ResearchBrief,
            }[role]
            parsed = model.model_validate(_raw_json(original))
            outputs[role] = parsed
            item["parsed"] = parsed.model_dump(mode="json")
            if role == "checker":
                notes = outputs["researcher"]
                indices = [row.claim_index for row in parsed.reviews]
                if len(set(indices)) != len(indices) or set(indices) != set(
                    range(len(notes.claims))
                ):
                    raise ValueError(
                        "checker must classify every candidate exactly once"
                    )
                claims = [
                    notes.claims[row.claim_index]
                    for row in parsed.reviews
                    if row.disposition == "supported"
                ]
                gate = grade_brief(
                    pack,
                    ResearchBrief(
                        question=pack.question,
                        answer="Checker source gate",
                        claims=claims,
                        conflicts=parsed.conflicts,
                        uncertainties=parsed.gaps,
                    ),
                )
                issues = [
                    x for x in gate["issues"] if x != "brief contains no cited claims"
                ]
                if notes.gaps and not parsed.gaps:
                    issues.append("checker dropped research uncertainty")
                if issues:
                    raise ValueError("invalid checker handoff: " + "; ".join(issues))
            receipt.save()
            receipt.guard()

        return record

    try:
        receipt.save()
        receipt.guard()
        receipt.source_guard()
        if configs is None:
            configs = from_environment(role_models, role_base_urls)
        if len(configs) != 3 or [x.role for x in configs] != list(ROLES):
            raise ValueError(
                "researcher/checker/writer configurations are required in role order"
            )
        for config in configs:
            config.validate()
        receipt.data["roles"] = [config.public() for config in configs]
        receipt.save()
        receipt.guard()
        llms = {}
        for config in configs:
            llms[config.role], boundaries[config.role] = await create_role(
                config,
                receipt,
                stack,
                (transports or {}).get(config.role),
                bridge=bridge,
            )
        crew = build_crew(
            pack,
            llms=llms,
            callbacks={role: callback(role) for role in ROLES},
            strict_handoffs=True,
            task_store_path=receipt.path.parent / "crew-tasks.db",
        )
        async with asyncio.timeout_at(receipt.deadline):
            completed = await crew.akickoff()
        receipt.guard()
        receipt.source_guard()
        if set(outputs) != set(ROLES) or len(completed.tasks_output) != 3:
            raise ValueError("all three native role task outputs are required")
        receipt.data["crew_usage"] = (
            completed.token_usage.model_dump(mode="json")
            if completed.token_usage is not None
            else None
        )
        await bridge.close()
        receipt.data["native_bridge_closed"] = True
        close_attempted = True
        await stack.aclose()
        receipt.data["native_clients_closed"] = True
        receipt.save()
        receipt.guard()
        receipt.source_guard()
        result = grade_handoff(
            pack, outputs["researcher"], outputs["checker"], outputs["writer"]
        )
        result.update(
            execution_kind="native_crewai_three_role",
            receipt_path=str(receipt.path),
            run_id=receipt.data["run_id"],
        )
        receipt.data["status"] = "release_prepared"
        receipt.save()
        receipt.guard()
        receipt.source_guard()
    except BaseException as error:
        failure = error.original if isinstance(error, NativeAbort) else error
        receipt.stopping = True
    finally:
        try:
            await bridge.close()
            receipt.data["native_bridge_closed"] = True
        except BaseException as error:
            failure = failure or error
            receipt.data["native_bridge_closed"] = False
            receipt.data["bridge_error"] = {
                "name": type(error).__name__,
                "message": str(error),
            }
        if not close_attempted:
            try:
                close_attempted = True
                await stack.aclose()
                receipt.data["native_clients_closed"] = True
            except BaseException as error:
                failure = failure or error
                receipt.data["close_error"] = {
                    "name": type(error).__name__,
                    "message": str(error),
                }
        try:
            receipt.finish(result, failure)
        except BaseException as error:
            failure = failure or error
            receipt.data.update(
                status="failed",
                result=None,
                durable_status="failed",
                recording_error={"name": type(error).__name__, "message": str(error)},
            )
            try:
                receipt.save(final=True)
            except BaseException:
                receipt.data["durable_status"] = "unknown"
    if failure is not None:
        failure.receipt_path = str(receipt.path)
        failure.evidence = receipt.data
        raise failure
    return result
