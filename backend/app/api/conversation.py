from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
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
)


router = APIRouter(prefix="/conversations", tags=["conversations"])
SessionDependency = Annotated[AsyncSession, Depends(get_db_session)]


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
