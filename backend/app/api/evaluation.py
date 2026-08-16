import asyncio
import json
from contextlib import suppress
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.eval.dataset import EVAL_FORM_OPTIONS, EvalCase, load_golden_dataset
from app.repository.agent_eval import (
    create_eval_case,
    delete_eval_case,
    exclude_builtin_case,
    get_eval_case,
    get_eval_run,
    list_eval_cases,
    list_excluded_builtin_case_ids,
    list_eval_results,
    list_eval_runs,
    restore_builtin_cases,
)
from app.schema.evaluation import (
    EvalCaseDefinition,
    EvalCaseResponse,
    EvalDatasetResponse,
    EvalResultResponse,
    EvalRunDetailResponse,
    EvalRunRequest,
    EvalRunResponse,
)
from app.service.evaluation import stream_eval_run


router = APIRouter(prefix="/evals", tags=["evals"])
SessionDependency = Annotated[AsyncSession, Depends(get_db_session)]


def _sse(event: dict) -> str:
    event_type = str(event.get("type") or "message")
    data = {key: value for key, value in event.items() if key != "type"}
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _custom_case_id(case_id: UUID) -> str:
    return f"custom:{case_id}"


def _case_response(
    case: EvalCase, *, source: str = "builtin"
) -> EvalCaseResponse:
    return EvalCaseResponse(
        **case.model_dump(), source=source, editable=source == "custom"
    )


def _stored_case(case) -> EvalCase:
    return EvalCase(id=_custom_case_id(case.id), **case.definition)


@router.get("/dataset", response_model=EvalDatasetResponse)
async def read_eval_dataset(session: SessionDependency) -> EvalDatasetResponse:
    dataset = load_golden_dataset()
    excluded_ids = await list_excluded_builtin_case_ids(session)
    custom_cases = [_stored_case(case) for case in await list_eval_cases(session)]
    return EvalDatasetResponse(
        version=dataset.version,
        description=dataset.description,
        cases=[_case_response(case) for case in dataset.cases if case.id not in excluded_ids]
        + [_case_response(case, source="custom") for case in custom_cases],
        form_options=EVAL_FORM_OPTIONS,
        hidden_builtin_count=len(excluded_ids),
    )


@router.post(
    "/cases", response_model=EvalCaseResponse, status_code=status.HTTP_201_CREATED
)
async def create_custom_eval_case(
    body: EvalCaseDefinition, session: SessionDependency
) -> EvalCaseResponse:
    async with session.begin():
        case = await create_eval_case(session, body.model_dump())
    return _case_response(_stored_case(case), source="custom")


@router.put("/cases/{case_id}", response_model=EvalCaseResponse)
async def update_custom_eval_case(
    case_id: UUID, body: EvalCaseDefinition, session: SessionDependency
) -> EvalCaseResponse:
    async with session.begin():
        case = await get_eval_case(session, case_id)
        if case is None:
            raise HTTPException(status_code=404, detail="Eval case not found")
        case.definition = body.model_dump()
    return _case_response(_stored_case(case), source="custom")


@router.post("/cases/presets/restore", status_code=status.HTTP_204_NO_CONTENT)
async def restore_preset_eval_cases(session: SessionDependency) -> Response:
    async with session.begin():
        await restore_builtin_cases(session)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/cases/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_eval_case(
    case_id: str, session: SessionDependency
) -> Response:
    dataset = load_golden_dataset()
    if case_id in {case.id for case in dataset.cases}:
        async with session.begin():
            await exclude_builtin_case(session, case_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    try:
        custom_id = UUID(case_id.removeprefix("custom:"))
    except ValueError as error:
        raise HTTPException(status_code=404, detail="Eval case not found") from error
    async with session.begin():
        case = await get_eval_case(session, custom_id)
        if case is None:
            raise HTTPException(status_code=404, detail="Eval case not found")
        await delete_eval_case(session, case)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/runs", response_model=list[EvalRunResponse])
async def read_eval_runs(
    session: SessionDependency, limit: Annotated[int, Query(ge=1, le=100)] = 20
) -> list[EvalRunResponse]:
    return [
        EvalRunResponse.model_validate(run)
        for run in await list_eval_runs(session, limit)
    ]


@router.get("/runs/{run_id}", response_model=EvalRunDetailResponse)
async def read_eval_run(
    run_id: UUID, session: SessionDependency
) -> EvalRunDetailResponse:
    run = await get_eval_run(session, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Eval run not found")
    results = await list_eval_results(session, run_id)
    return EvalRunDetailResponse(
        **EvalRunResponse.model_validate(run).model_dump(),
        results=[EvalResultResponse.model_validate(result) for result in results],
    )


@router.post("/runs/stream")
async def create_eval_run_stream(
    body: EvalRunRequest,
    request: Request,
    session: SessionDependency,
    api_key: Annotated[str, Header(alias="X-DeepSeek-API-Key", min_length=1)],
    tavily_api_key: Annotated[
        str | None, Header(alias="X-Tavily-API-Key", min_length=1)
    ] = None,
) -> StreamingResponse:
    dataset = load_golden_dataset()
    excluded_ids = await list_excluded_builtin_case_ids(session)
    by_id = {case.id: case for case in dataset.cases if case.id not in excluded_ids}
    for stored in await list_eval_cases(session):
        custom = _stored_case(stored)
        by_id[custom.id] = custom
    selected_ids = body.case_ids or list(by_id)
    unknown = [case_id for case_id in selected_ids if case_id not in by_id]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown eval cases: {unknown}")
    cases = [by_id[case_id] for case_id in selected_ids]

    async def generate():
        stream = stream_eval_run(
            session=session,
            dataset_version=dataset.version,
            cases=cases,
            api_key=api_key,
            tavily_api_key=tavily_api_key,
            checkpointer=request.app.state.agent_checkpointer,
            judge_enabled=body.judge_enabled,
            judge_weight=body.judge_weight,
        )
        pending: asyncio.Task | None = None
        active_run_id: UUID | None = None
        try:
            while True:
                if pending is None:
                    pending = asyncio.create_task(anext(stream))
                done, _ = await asyncio.wait({pending}, timeout=15)
                if not done:
                    yield ": keep-alive\n\n"
                    continue
                try:
                    event = pending.result()
                except StopAsyncIteration:
                    break
                pending = None
                if event.get("type") == "eval.started":
                    active_run_id = UUID(str(event["run_id"]))
                yield _sse(event)
        except asyncio.CancelledError:
            if pending:
                pending.cancel()
                with suppress(asyncio.CancelledError):
                    await pending
            if active_run_id:
                async with session.begin():
                    run = await get_eval_run(session, active_run_id)
                    if run and run.status == "running":
                        run.status = "cancelled"
                        run.completed_at = datetime.now(timezone.utc)
            raise
        except Exception as error:
            if active_run_id:
                async with session.begin():
                    run = await get_eval_run(session, active_run_id)
                    if run and run.status == "running":
                        run.status = "failed"
                        run.error = str(error)[:2000]
                        run.completed_at = datetime.now(timezone.utc)
            yield _sse({"type": "eval.failed", "message": str(error)})
        finally:
            with suppress(RuntimeError):
                await stream.aclose()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )
