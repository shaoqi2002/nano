from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.schema.workspace import WorkspaceCreate, WorkspaceResponse
from app.service.workspace import (
    CH4_WORKSPACE_ID,
    WORKSPACE_FEATURES,
    create_workspace,
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
async def read_workspaces(session: SessionDependency) -> list[WorkspaceResponse]:
    return [_response(item) for item in await list_workspaces(session)]


@router.post("", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
async def add_workspace(
    body: WorkspaceCreate, session: SessionDependency
) -> WorkspaceResponse:
    return _response(await create_workspace(session, body.name))
