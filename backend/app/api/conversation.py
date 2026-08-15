import asyncio
import json
import logging
from contextlib import suppress
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
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
    send_message,
    send_message_stream as stream_message,
)


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
    session: SessionDependency,
    api_key: Annotated[
        str,
        Header(alias="X-DeepSeek-API-Key", min_length=1),
    ],
    tavily_api_key: Annotated[
        str | None,
        Header(alias="X-Tavily-API-Key", min_length=1),
    ] = None,
) -> SendMessageResponse:
    try:
        assistant_message = await send_message(
            session=session,
            conversation_id=conversation_id,
            content=request.message,
            api_key=api_key,
            tavily_api_key=tavily_api_key,
            use_rag=request.use_rag,
        )
    except ConversationNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        ) from error

    return SendMessageResponse(
        conversation_id=conversation_id,
        assistant_message=MessageResponse.model_validate(assistant_message),
    )


@router.post("/{conversation_id}/messages/stream")
async def create_message_stream(
    conversation_id: UUID,
    request: SendMessageRequest,
    session: SessionDependency,
    api_key: Annotated[
        str,
        Header(alias="X-DeepSeek-API-Key", min_length=1),
    ],
    tavily_api_key: Annotated[
        str | None,
        Header(alias="X-Tavily-API-Key", min_length=1),
    ] = None,
) -> StreamingResponse:
    async def generate():
        stream = stream_message(
            session=session,
            conversation_id=conversation_id,
            content=request.message,
            api_key=api_key,
            tavily_api_key=tavily_api_key,
            use_rag=request.use_rag,
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

    return ConversationMessagesResponse(
        conversation_id=conversation_id,
        messages=[MessageResponse.model_validate(message) for message in messages],
    )
