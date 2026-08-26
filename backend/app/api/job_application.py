from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.service.workspace import current_workspace_id, get_ch4_workspace_session
from app.model.job_application import JobApplication, JobApplicationEvent
from app.repository.job_application import get_job_application, list_job_applications
from app.schema.job_application import (
    JobApplicationCreate,
    JobApplicationResponse,
    JobApplicationUpdate,
    JobStatusUpdate,
)
from app.service.job_application import infer_job_information_with_agent


router = APIRouter(prefix="/job-applications", tags=["job-applications"])
SessionDependency = Annotated[AsyncSession, Depends(get_ch4_workspace_session)]


async def require_application(
    session: AsyncSession, application_id: UUID
) -> JobApplication:
    application = await get_job_application(session, application_id)
    if application is None:
        raise HTTPException(status_code=404, detail="投递记录不存在")
    return application


@router.get("", response_model=list[JobApplicationResponse])
async def read_job_applications(
    session: SessionDependency,
) -> list[JobApplicationResponse]:
    return [
        JobApplicationResponse.model_validate(item)
        for item in await list_job_applications(session)
    ]


@router.post(
    "", response_model=JobApplicationResponse, status_code=status.HTTP_201_CREATED
)
async def create_job_application(
    body: JobApplicationCreate,
    session: SessionDependency,
    deepseek_api_key: Annotated[
        str | None, Header(alias="X-DeepSeek-API-Key", min_length=1)
    ] = None,
    tavily_api_key: Annotated[
        str | None, Header(alias="X-Tavily-API-Key", min_length=1)
    ] = None,
) -> JobApplicationResponse:
    inferred = await infer_job_information_with_agent(
        body.job_url, body.notes, deepseek_api_key, tavily_api_key
    )
    application = JobApplication(
        workspace_id=current_workspace_id(session),
        job_url=body.job_url,
        notes=body.notes,
        **inferred,
    )
    event = JobApplicationEvent(to_status="applied", note="新增投递记录")
    application.events.append(event)
    async with session.begin():
        session.add(application)
    application = await require_application(session, application.id)
    return JobApplicationResponse.model_validate(application)


@router.post("/{application_id}/enrich", response_model=JobApplicationResponse)
async def enrich_job_application(
    application_id: UUID,
    session: SessionDependency,
    deepseek_api_key: Annotated[
        str, Header(alias="X-DeepSeek-API-Key", min_length=1)
    ],
    tavily_api_key: Annotated[
        str, Header(alias="X-Tavily-API-Key", min_length=1)
    ],
) -> JobApplicationResponse:
    application = await require_application(session, application_id)
    inferred = await infer_job_information_with_agent(
        application.job_url,
        application.notes,
        deepseek_api_key,
        tavily_api_key,
    )
    for field, value in inferred.items():
        setattr(application, field, value)
    await session.commit()
    return JobApplicationResponse.model_validate(
        await require_application(session, application_id)
    )


@router.patch("/{application_id}", response_model=JobApplicationResponse)
async def update_job_application(
    application_id: UUID,
    body: JobApplicationUpdate,
    session: SessionDependency,
) -> JobApplicationResponse:
    application = await require_application(session, application_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(application, field, value.strip() if isinstance(value, str) else value)
    await session.commit()
    return JobApplicationResponse.model_validate(
        await require_application(session, application_id)
    )


@router.patch("/{application_id}/status", response_model=JobApplicationResponse)
async def update_job_application_status(
    application_id: UUID,
    body: JobStatusUpdate,
    session: SessionDependency,
) -> JobApplicationResponse:
    application = await require_application(session, application_id)
    if application.status != body.status:
        previous = application.status
        application.status = body.status
        application.events.append(
            JobApplicationEvent(
                from_status=previous, to_status=body.status, note=body.note.strip()
            )
        )
        await session.commit()
    return JobApplicationResponse.model_validate(
        await require_application(session, application_id)
    )


@router.delete("/{application_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job_application(
    application_id: UUID, session: SessionDependency
) -> Response:
    application = await require_application(session, application_id)
    await session.delete(application)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
