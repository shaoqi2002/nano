from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.model.agent_eval import AgentEvalResult, AgentEvalRun


async def create_eval_run(
    session: AsyncSession,
    dataset_version: str,
    case_count: int,
    config: dict,
) -> AgentEvalRun:
    run = AgentEvalRun(
        dataset_version=dataset_version,
        case_count=case_count,
        config=config,
        status="pending",
    )
    session.add(run)
    await session.flush()
    return run


async def add_eval_result(
    session: AsyncSession,
    *,
    eval_run_id: UUID,
    case_id: str,
    title: str,
    passed: bool,
    score: float,
    output: str,
    metrics: dict,
    error: str | None,
    duration_ms: int,
) -> AgentEvalResult:
    result = AgentEvalResult(
        eval_run_id=eval_run_id,
        case_id=case_id,
        title=title,
        passed=passed,
        score=score,
        output=output,
        metrics=metrics,
        error=error,
        duration_ms=duration_ms,
    )
    session.add(result)
    await session.flush()
    return result


async def get_eval_run(session: AsyncSession, run_id: UUID) -> AgentEvalRun | None:
    return await session.get(AgentEvalRun, run_id)


async def list_eval_runs(session: AsyncSession, limit: int = 20) -> list[AgentEvalRun]:
    statement = (
        select(AgentEvalRun)
        .order_by(AgentEvalRun.created_at.desc())
        .limit(max(1, min(limit, 100)))
    )
    return list(await session.scalars(statement))


async def list_eval_results(
    session: AsyncSession, run_id: UUID
) -> list[AgentEvalResult]:
    statement = (
        select(AgentEvalResult)
        .where(AgentEvalResult.eval_run_id == run_id)
        .order_by(AgentEvalResult.id)
    )
    return list(await session.scalars(statement))
