from uuid import UUID

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.service.chat_artifact import ChatArtifactNotFoundError, get_chat_artifact


router = APIRouter(prefix="/artifacts", tags=["artifacts"])


@router.get("/{artifact_id}")
async def download_artifact(artifact_id: UUID) -> FileResponse:
    try:
        path, media_type = get_chat_artifact(artifact_id)
    except ChatArtifactNotFoundError as error:
        raise HTTPException(status_code=404, detail="下载文件不存在或已过期") from error
    return FileResponse(path, media_type=media_type, filename=path.name)
