import asyncio
import json
from contextlib import suppress
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.service.workspace import get_workspace_session
from app.schema.conversation import AgentRunEventResponse, AgentRunResponse
from app.repository.agent_run import list_agent_run_events
from app.service.agent_run import (
    AgentRunNotFoundError,
    get_run,
    request_cancel,
    stream_resume_run,
)


router = APIRouter(prefix="/agent-runs", tags=["agent-runs"])
SessionDependency = Annotated[AsyncSession, Depends(get_workspace_session)]


def _sse(event: dict) -> str:
    event_type = str(event.get("type") or "message")
    data = {key: value for key, value in event.items() if key != "type"}
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.get("/{run_id}", response_model=AgentRunResponse)
async def read_agent_run(run_id: UUID, session: SessionDependency) -> AgentRunResponse:
    try:
        run = await get_run(session, run_id)
    except AgentRunNotFoundError as error:
        raise HTTPException(status_code=404, detail="Agent run not found") from error
    return AgentRunResponse.model_validate(run)


@router.post("/{run_id}/cancel", response_model=AgentRunResponse)
async def cancel_agent_run(run_id: UUID, session: SessionDependency) -> AgentRunResponse:
    try:
        run = await request_cancel(session, run_id)
    except AgentRunNotFoundError as error:
        raise HTTPException(status_code=404, detail="Agent run not found") from error
    return AgentRunResponse.model_validate(run)


@router.get("/{run_id}/events", response_model=list[AgentRunEventResponse])
async def read_agent_run_events(
    run_id: UUID, session: SessionDependency
) -> list[AgentRunEventResponse]:
    try:
        await get_run(session, run_id)
    except AgentRunNotFoundError as error:
        raise HTTPException(status_code=404, detail="Agent run not found") from error
    events = await list_agent_run_events(session, run_id)
    return [AgentRunEventResponse.model_validate(event) for event in events]


@router.post("/{run_id}/resume/stream")
async def resume_agent_run(
    run_id: UUID,
    request: Request,
    session: SessionDependency,
    api_key: Annotated[str, Header(alias="X-DeepSeek-API-Key", min_length=1)],
    tavily_api_key: Annotated[
        str | None, Header(alias="X-Tavily-API-Key", min_length=1)
    ] = None,
) -> StreamingResponse:
    async def generate():
        stream = stream_resume_run(
            session=session,
            run_id=run_id,
            api_key=api_key,
            tavily_api_key=tavily_api_key,
            checkpointer=request.app.state.agent_checkpointer,
        )
        pending: asyncio.Task | None = None
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
                yield _sse(event)
        except AgentRunNotFoundError:
            yield _sse({"type": "message.failed", "message": "Agent run not found"})
        except asyncio.CancelledError:
            if pending:
                pending.cancel()
                with suppress(asyncio.CancelledError):
                    await pending
            raise
        except Exception as error:
            yield _sse({"type": "message.failed", "message": str(error)})
        finally:
            with suppress(RuntimeError):
                await stream.aclose()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )
