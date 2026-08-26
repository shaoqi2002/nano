from typing import Annotated

from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.database import get_db_session
from app.model.document import Document
from app.model.workspace import Workspace
from app.schema.workspace import WorkspaceCreate, WorkspaceLookup, WorkspaceResponse
from app.service.chat_artifact import delete_workspace_artifacts
from app.service.document_cache import DocumentCacheError, document_cache
from app.service.object_storage import delete_object
from app.service.workspace import (
    CH4_WORKSPACE_ID,
    WORKSPACE_FEATURES,
    create_workspace,
    find_workspace_by_name,
    list_workspaces,
)


router = APIRouter(prefix="/workspaces", tags=["workspaces"])
SessionDependency = Annotated[AsyncSession, Depends(get_db_session)]


def _response(workspace) -> WorkspaceResponse:
    features = WORKSPACE_FEATURES if workspace.id == CH4_WORKSPACE_ID else []
    return WorkspaceResponse.model_validate(
        {**workspace.__dict__, "restricted_features": features}
    )


@router.get("", response_model=list[WorkspaceResponse])
async def read_workspaces(
    session: SessionDependency,
    ids: Annotated[list[UUID] | None, Query()] = None,
) -> list[WorkspaceResponse]:
    return [_response(item) for item in await list_workspaces(session, ids or [])]


@router.post("/resolve", response_model=WorkspaceResponse)
async def resolve_workspace(
    body: WorkspaceLookup, session: SessionDependency
) -> WorkspaceResponse:
    workspace = await find_workspace_by_name(session, body.name)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return _response(workspace)


@router.post("", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
async def add_workspace(
    body: WorkspaceCreate, session: SessionDependency
) -> WorkspaceResponse:
    return _response(await create_workspace(session, body.name))


@router.delete("/{selected_workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_workspace(
    selected_workspace_id: UUID,
    session: SessionDependency,
    active_workspace_id: Annotated[
        UUID, Header(alias="X-Workspace-ID")
    ],
) -> Response:
    if selected_workspace_id != active_workspace_id:
        raise HTTPException(status_code=403, detail="Workspace selection mismatch")
    if selected_workspace_id == CH4_WORKSPACE_ID:
        raise HTTPException(status_code=409, detail="The ch4 workspace cannot be deleted")
    workspace = await session.get(Workspace, selected_workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    documents = list(await session.scalars(
        select(Document).where(Document.workspace_id == selected_workspace_id)
    ))
    try:
        for document in documents:
            await run_in_threadpool(delete_object, document.object_key)
            try:
                await run_in_threadpool(document_cache.remove, document.object_key)
            except DocumentCacheError:
                pass
        await run_in_threadpool(delete_workspace_artifacts, selected_workspace_id)
    except Exception as error:
        raise HTTPException(status_code=502, detail="Unable to clean workspace files") from error
    await session.delete(workspace)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
