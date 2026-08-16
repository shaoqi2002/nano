import asyncio
import json
from contextlib import suppress
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.eval.dataset import load_golden_dataset
from app.repository.agent_eval import get_eval_run, list_eval_results, list_eval_runs
from app.schema.evaluation import (
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


@router.get("/dataset", response_model=EvalDatasetResponse)
async def read_eval_dataset() -> EvalDatasetResponse:
    dataset = load_golden_dataset()
    return EvalDatasetResponse(
        version=dataset.version,
        description=dataset.description,
        cases=[EvalCaseResponse.model_validate(case.model_dump()) for case in dataset.cases],
    )


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
    by_id = {case.id: case for case in dataset.cases}
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
