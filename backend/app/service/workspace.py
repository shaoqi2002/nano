import re
from collections.abc import AsyncGenerator
from contextvars import ContextVar
from typing import Annotated
from uuid import UUID

from fastapi import Header, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import SessionLocal
from app.model.workspace import Workspace


CH4_WORKSPACE_ID = UUID("00000000-0000-0000-0000-0000000000c4")
CH4_WORKSPACE_SLUG = "ch4"
WORKSPACE_FEATURES = ["agent-eval", "job-applications"]
_active_workspace_id: ContextVar[UUID] = ContextVar(
    "active_workspace_id", default=CH4_WORKSPACE_ID
)


def active_workspace_id() -> UUID:
    return _active_workspace_id.get()


def current_workspace_id(session: AsyncSession) -> UUID:
    workspace_id = session.info.get("workspace_id", active_workspace_id())
    if not isinstance(workspace_id, UUID):
        raise RuntimeError("Workspace-scoped database session is required")
    return workspace_id


async def get_workspace_session(
    x_workspace_id: Annotated[str | None, Header(alias="X-Workspace-ID")] = None,
    workspace_id: Annotated[str | None, Query()] = None,
) -> AsyncGenerator[AsyncSession, None]:
    raw_id = x_workspace_id or workspace_id
    if not raw_id:
        raise HTTPException(status_code=400, detail="Workspace is required")
    try:
        selected_id = UUID(raw_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail="Invalid workspace") from error

    async with SessionLocal() as session:
        workspace = await session.get(Workspace, selected_id)
        if workspace is None:
            raise HTTPException(status_code=404, detail="Workspace not found")
        selected_workspace_id = workspace.id
        selected_workspace_slug = workspace.slug
        # session.get() starts an implicit read transaction. Scoped write
        # services open their own transaction, so finish this lookup first.
        if session.in_transaction():
            await session.rollback()
        session.info["workspace_id"] = selected_workspace_id
        session.info["workspace_slug"] = selected_workspace_slug
        token = _active_workspace_id.set(selected_workspace_id)
        try:
            yield session
        finally:
            _active_workspace_id.reset(token)


async def get_ch4_workspace_session(
    x_workspace_id: Annotated[str | None, Header(alias="X-Workspace-ID")] = None,
    workspace_id: Annotated[str | None, Query()] = None,
) -> AsyncGenerator[AsyncSession, None]:
    async for session in get_workspace_session(x_workspace_id, workspace_id):
        require_ch4_workspace(session)
        yield session


def require_ch4_workspace(session: AsyncSession) -> None:
    if current_workspace_id(session) != CH4_WORKSPACE_ID:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This feature is only available in the ch4 workspace",
        )


async def list_workspaces(
    session: AsyncSession, workspace_ids: list[UUID]
) -> list[Workspace]:
    if not workspace_ids:
        return []
    result = await session.scalars(
        select(Workspace)
        .where(Workspace.id.in_(workspace_ids))
        .order_by(Workspace.created_at, Workspace.name)
    )
    return list(result)


async def find_workspace_by_name(
    session: AsyncSession, name: str
) -> Workspace | None:
    clean_name = " ".join(name.split())
    if not clean_name:
        return None
    return await session.scalar(
        select(Workspace).where(func.lower(Workspace.name) == clean_name.lower())
    )


async def create_workspace(session: AsyncSession, name: str) -> Workspace:
    clean_name = " ".join(name.split())
    if not clean_name:
        raise HTTPException(status_code=422, detail="Workspace name is required")
    existing = await session.scalar(
        select(Workspace).where(func.lower(Workspace.name) == clean_name.lower())
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="Workspace name already exists")
    base_slug = re.sub(r"[^a-z0-9]+", "-", clean_name.lower()).strip("-") or "workspace"
    slug = base_slug
    suffix = 2
    while await session.scalar(select(Workspace.id).where(Workspace.slug == slug)):
        slug = f"{base_slug}-{suffix}"
        suffix += 1
    workspace = Workspace(name=clean_name, slug=slug)
    session.add(workspace)
    await session.commit()
    await session.refresh(workspace)
    return workspace
