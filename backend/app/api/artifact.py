from uuid import UUID

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.service.chat_artifact import ChatArtifactNotFoundError, get_chat_artifact
from app.service.workspace import current_workspace_id, get_workspace_session


router = APIRouter(prefix="/artifacts", tags=["artifacts"])
SessionDependency = Annotated[AsyncSession, Depends(get_workspace_session)]


@router.get("/{artifact_id}")
async def download_artifact(
    artifact_id: UUID, session: SessionDependency
) -> FileResponse:
    try:
        path, media_type = get_chat_artifact(artifact_id, current_workspace_id(session))
    except ChatArtifactNotFoundError as error:
        raise HTTPException(status_code=404, detail="下载文件不存在或已过期") from error
    return FileResponse(path, media_type=media_type, filename=path.name)
