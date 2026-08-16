import asyncio
import json
import logging
from contextlib import suppress
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.schema.conversation import (
    ConversationMessagesResponse,
    ConversationResponse,
    ConversationSummaryResponse,
    MessageResponse,
    SendMessageRequest,
    SendMessageResponse,
)
from app.service.conversation import (
    ConversationNotFoundError,
    create_new_conversation,
    delete_existing_conversation,
    get_conversation_messages,
    get_conversations,
)
from app.service.agent_run import stream_new_run
from app.repository.agent_run import get_run_ids_by_assistant_message_ids


router = APIRouter(prefix="/conversations", tags=["conversations"])
SessionDependency = Annotated[AsyncSession, Depends(get_db_session)]
logger = logging.getLogger(__name__)


def _sse(event: dict) -> str:
    event_type = str(event.get("type") or "message")
    payload = {key: value for key, value in event.items() if key != "type"}
    return f"event: {event_type}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post(
    "",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation(session: SessionDependency) -> ConversationResponse:
    conversation = await create_new_conversation(session)
    return ConversationResponse.model_validate(conversation)


@router.get("", response_model=list[ConversationSummaryResponse])
async def read_conversations(
    session: SessionDependency,
) -> list[ConversationSummaryResponse]:
    conversations = await get_conversations(session)
    return [
        ConversationSummaryResponse(
            id=conversation.id,
            created_at=conversation.created_at,
            title=title,
        )
        for conversation, title in conversations
    ]


@router.post(
    "/{conversation_id}/messages",
    response_model=SendMessageResponse,
)
async def create_message(
    conversation_id: UUID,
    request: SendMessageRequest,
    http_request: Request,
    session: SessionDependency,
    api_key: Annotated[
        str,
        Header(alias="X-DeepSeek-API-Key", min_length=1),
    ],
    tavily_api_key: Annotated[
        str | None,
        Header(alias="X-Tavily-API-Key", min_length=1),
    ] = None,
    embedding_api_key: Annotated[
        str | None,
        Header(alias="X-Embedding-API-Key", min_length=1),
    ] = None,
    embedding_base_url: Annotated[
        str | None,
        Header(alias="X-Embedding-Base-URL", min_length=1, max_length=500),
    ] = None,
) -> SendMessageResponse:
    try:
        assistant_payload: dict | None = None
        stream = stream_new_run(
            session=session,
            conversation_id=conversation_id,
            content=request.message,
            api_key=api_key,
            tavily_api_key=tavily_api_key,
            embedding_api_key=embedding_api_key,
            embedding_base_url=embedding_base_url,
            use_rag=request.use_rag,
            requested_mode=request.mode,
            checkpointer=http_request.app.state.agent_checkpointer,
        )
        async for event in stream:
            if event.get("type") == "message.completed":
                assistant_payload = event["message"]
    except ConversationNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        ) from error
    if assistant_payload is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Agent did not complete the response",
        )

    return SendMessageResponse(
        conversation_id=conversation_id,
        assistant_message=MessageResponse.model_validate(assistant_payload),
    )


@router.post("/{conversation_id}/messages/stream")
async def create_message_stream(
    conversation_id: UUID,
    request: SendMessageRequest,
    http_request: Request,
    session: SessionDependency,
    api_key: Annotated[
        str,
        Header(alias="X-DeepSeek-API-Key", min_length=1),
    ],
    tavily_api_key: Annotated[
        str | None,
        Header(alias="X-Tavily-API-Key", min_length=1),
    ] = None,
    embedding_api_key: Annotated[
        str | None,
        Header(alias="X-Embedding-API-Key", min_length=1),
    ] = None,
    embedding_base_url: Annotated[
        str | None,
        Header(alias="X-Embedding-Base-URL", min_length=1, max_length=500),
    ] = None,
) -> StreamingResponse:
    async def generate():
        stream = stream_new_run(
            session=session,
            conversation_id=conversation_id,
            content=request.message,
            api_key=api_key,
            tavily_api_key=tavily_api_key,
            embedding_api_key=embedding_api_key,
            embedding_base_url=embedding_base_url,
            use_rag=request.use_rag,
            requested_mode=request.mode,
            checkpointer=http_request.app.state.agent_checkpointer,
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
        except ConversationNotFoundError:
            yield _sse({"type": "message.failed", "message": "Conversation not found"})
        except asyncio.CancelledError:
            if pending is not None:
                pending.cancel()
                with suppress(asyncio.CancelledError):
                    await pending
            raise
        except Exception:
            logger.exception("Streaming message failed")
            yield _sse({"type": "message.failed", "message": "生成回答时发生内部错误"})
        finally:
            with suppress(RuntimeError):
                await stream.aclose()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


@router.delete(
    "/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_conversation(
    conversation_id: UUID,
    session: SessionDependency,
) -> Response:
    try:
        await delete_existing_conversation(session, conversation_id)
    except ConversationNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        ) from error

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{conversation_id}/messages",
    response_model=ConversationMessagesResponse,
)
async def read_messages(
    conversation_id: UUID,
    session: SessionDependency,
) -> ConversationMessagesResponse:
    try:
        messages = await get_conversation_messages(session, conversation_id)
    except ConversationNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        ) from error

    run_ids = await get_run_ids_by_assistant_message_ids(
        session, [message.id for message in messages if message.role == "assistant"]
    )
    responses = []
    for message in messages:
        response = MessageResponse.model_validate(message)
        if message.id in run_ids:
            response = response.model_copy(update={"run_id": run_ids[message.id]})
        responses.append(response)
    return ConversationMessagesResponse(
        conversation_id=conversation_id,
        messages=responses,
    )
