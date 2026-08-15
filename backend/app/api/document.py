from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, PlainTextResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.database import get_db_session
from app.schema.document import DocumentResponse
from app.service.document import (
    DocumentNotFoundError,
    InvalidDocumentError,
    cached_document_path,
    create_document,
    delete_document,
    document_text,
    get_documents,
    require_document,
)
from app.service.document_cache import DocumentCacheError
from app.service.object_storage import (
    ObjectStorageConfigurationError,
    ObjectStorageError,
)


router = APIRouter(prefix="/documents", tags=["documents"])
SessionDependency = Annotated[AsyncSession, Depends(get_db_session)]


def storage_http_error(error: Exception) -> HTTPException:
    if isinstance(error, ObjectStorageConfigurationError):
        return HTTPException(status_code=503, detail=str(error))
    return HTTPException(status_code=502, detail=str(error))


@router.get("", response_model=list[DocumentResponse])
async def read_documents(session: SessionDependency) -> list[DocumentResponse]:
    documents = await get_documents(session)
    return [DocumentResponse.model_validate(document) for document in documents]


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    session: SessionDependency,
    file: Annotated[UploadFile, File(...)],
) -> DocumentResponse:
    try:
        document = await create_document(session, file)
    except InvalidDocumentError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except (ObjectStorageConfigurationError, ObjectStorageError) as error:
        raise storage_http_error(error) from error
    finally:
        await file.close()
    return DocumentResponse.model_validate(document)


@router.get("/{document_id}/content")
async def read_document_content(
    document_id: UUID,
    session: SessionDependency,
    download: Annotated[bool, Query()] = False,
) -> Response:
    try:
        document = await require_document(session, document_id)
        path = await run_in_threadpool(
            cached_document_path,
            document,
        )
    except DocumentNotFoundError as error:
        raise HTTPException(status_code=404, detail="Document not found") from error
    except (ObjectStorageConfigurationError, ObjectStorageError) as error:
        raise storage_http_error(error) from error
    except DocumentCacheError as error:
        raise HTTPException(status_code=507, detail=str(error)) from error

    return FileResponse(
        path,
        media_type=document.content_type,
        filename=document.original_name,
        content_disposition_type="attachment" if download else "inline",
        headers={
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, max-age=3600",
        },
    )


@router.get("/{document_id}/text", response_class=PlainTextResponse)
async def read_document_text(
    document_id: UUID,
    session: SessionDependency,
) -> PlainTextResponse:
    try:
        document = await require_document(session, document_id)
        content = await run_in_threadpool(document_text, document)
    except DocumentNotFoundError as error:
        raise HTTPException(status_code=404, detail="Document not found") from error
    except InvalidDocumentError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except (ObjectStorageConfigurationError, ObjectStorageError) as error:
        raise storage_http_error(error) from error
    except DocumentCacheError as error:
        raise HTTPException(status_code=507, detail=str(error)) from error
    return PlainTextResponse(content)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_document_endpoint(
    document_id: UUID,
    session: SessionDependency,
) -> Response:
    try:
        await delete_document(session, document_id)
    except DocumentNotFoundError as error:
        raise HTTPException(status_code=404, detail="Document not found") from error
    except (ObjectStorageConfigurationError, ObjectStorageError) as error:
        raise storage_http_error(error) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)
