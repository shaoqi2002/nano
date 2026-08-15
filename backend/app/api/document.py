import re
from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Header,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import PlainTextResponse, Response, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.database import get_db_session
from app.schema.document import DocumentResponse
from app.service.document import (
    DocumentNotFoundError,
    InvalidDocumentError,
    create_document,
    delete_document,
    document_text,
    get_documents,
    require_document,
)
from app.service.object_storage import (
    ObjectStorageConfigurationError,
    ObjectStorageError,
    object_stream,
)


router = APIRouter(prefix="/documents", tags=["documents"])
SessionDependency = Annotated[AsyncSession, Depends(get_db_session)]
RANGE_PATTERN = re.compile(r"^bytes=(\d*)-(\d*)$")


def valid_range_header(value: str) -> bool:
    match = RANGE_PATTERN.fullmatch(value)
    if not match:
        return False
    start, end = match.groups()
    if not start and not end:
        return False
    return not (start and end and int(start) > int(end))


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
    range_header: Annotated[str | None, Header(alias="Range")] = None,
) -> Response:
    if range_header and not valid_range_header(range_header):
        raise HTTPException(status_code=416, detail="Invalid byte range")
    try:
        document = await require_document(session, document_id)
        chunks, content_length, content_range = await run_in_threadpool(
            object_stream,
            document.object_key,
            range_header,
        )
    except DocumentNotFoundError as error:
        raise HTTPException(status_code=404, detail="Document not found") from error
    except (ObjectStorageConfigurationError, ObjectStorageError) as error:
        raise storage_http_error(error) from error

    disposition = "attachment" if download else "inline"
    ascii_name = "document" + (
        "." + document.original_name.rsplit(".", 1)[-1]
        if "." in document.original_name
        else ""
    )
    encoded_name = quote(document.original_name, safe="")
    headers = {
        "Content-Disposition": (
            f'{disposition}; filename="{ascii_name}"; '
            f"filename*=UTF-8''{encoded_name}"
        ),
        "X-Content-Type-Options": "nosniff",
        "Accept-Ranges": "bytes",
    }
    if content_length is not None:
        headers["Content-Length"] = str(content_length)
    if content_range:
        headers["Content-Range"] = content_range
    return StreamingResponse(
        chunks,
        media_type=document.content_type,
        headers=headers,
        status_code=206 if content_range else 200,
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
