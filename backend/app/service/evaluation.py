import time
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_deepseek import ChatDeepSeek
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent import build_agent_graph, initial_agent_state
from app.core.config import DEEPSEEK_MODEL, EVAL_JUDGE_MODEL
from app.eval.dataset import EvalCase
from app.eval.judge import combine_with_judge, judge_agent_output
from app.eval.scorer import score_agent_output
from app.model.agent_eval import AgentEvalRun
from app.repository.agent_eval import add_eval_result, create_eval_run
from app.service.conversation import create_model
from app.tools import create_tools


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def stream_eval_run(
    *,
    session: AsyncSession,
    dataset_version: str,
    cases: list[EvalCase],
    api_key: str,
    tavily_api_key: str | None,
    checkpointer: Any,
    judge_enabled: bool = False,
    judge_weight: float = 0.5,
) -> AsyncIterator[dict[str, Any]]:
    async with session.begin():
        run = await create_eval_run(
            session,
            dataset_version,
            len(cases),
            {
                "case_ids": [case.id for case in cases],
                "model": DEEPSEEK_MODEL,
                "judge_enabled": judge_enabled,
                "judge_model": EVAL_JUDGE_MODEL if judge_enabled else None,
                "judge_weight": judge_weight,
                "case_snapshots": [case.model_dump() for case in cases],
            },
        )
        run.status = "running"
    yield {
        "type": "eval.started",
        "run_id": str(run.id),
        "dataset_version": dataset_version,
        "case_count": len(cases),
        "judge_enabled": judge_enabled,
    }

    suite_started = time.monotonic()
    scores: list[float] = []
    passed_count = 0
    model = create_model(api_key)
    judge_model = (
        ChatDeepSeek(
            model=EVAL_JUDGE_MODEL,
            api_key=SecretStr(api_key),
            temperature=0,
            max_retries=2,
        )
        if judge_enabled
        else None
    )
    tools = create_tools(tavily_api_key)

    for index, case in enumerate(cases, start=1):
        yield {
            "type": "case.started",
            "run_id": str(run.id),
            "case_id": case.id,
            "title": case.title,
            "index": index,
            "total": len(cases),
        }
        case_started = time.monotonic()
        output = ""
        events: list[dict[str, Any]] = []
        error_message: str | None = None
        try:
            graph = build_agent_graph(model, tools, case.mode, checkpointer)
            thread_id = f"eval:{run.id}:{case.id}"
            config = {"configurable": {"thread_id": thread_id}}
            state = initial_agent_state(
                run_id=thread_id,
                conversation_id="evaluation",
                query=case.prompt,
                messages=[
                    SystemMessage(content=(
                        "你是 Nano Agent，准确完成评测任务。需要最新信息时使用联网工具，"
                        "无法确认时明确说明，不得编造来源。"
                    )),
                    HumanMessage(content=case.prompt),
                ],
                rag_sources=[],
            )
            async for event in graph.astream(
                state, config=config, stream_mode="custom"
            ):
                if isinstance(event, dict) and event.get("type") != "message.delta":
                    events.append(event)
            snapshot = await graph.aget_state(config)
            output = str((snapshot.values or {}).get("final_answer") or "")
        except Exception as error:
            error_message = str(error)[:2000]

        agent_duration_ms = round((time.monotonic() - case_started) * 1000)
        scored = score_agent_output(case, output, events, agent_duration_ms)
        if error_message:
            scored = type(scored)(passed=False, score=0.0, metrics={
                **scored.metrics,
                "execution_error": True,
            })
        elif judge_model is not None:
            yield {
                "type": "case.judging",
                "run_id": str(run.id),
                "case_id": case.id,
                "title": case.title,
            }
            try:
                verdict = await judge_agent_output(
                    judge_model, case, output, events
                )
                scored = combine_with_judge(
                    scored,
                    verdict,
                    judge_weight=judge_weight,
                    pass_threshold=case.pass_threshold,
                )
            except Exception as judge_error:
                scored = type(scored)(
                    passed=scored.passed,
                    score=scored.score,
                    metrics={
                        **scored.metrics,
                        "judge_error": str(judge_error)[:1000],
                    },
                )
        duration_ms = round((time.monotonic() - case_started) * 1000)
        scored = type(scored)(
            passed=scored.passed,
            score=scored.score,
            metrics={
                **scored.metrics,
                "agent_duration_ms": agent_duration_ms,
                "judge_duration_ms": max(0, duration_ms - agent_duration_ms),
            },
        )
        scores.append(scored.score)
        if scored.passed:
            passed_count += 1
        async with session.begin():
            result = await add_eval_result(
                session,
                eval_run_id=run.id,
                case_id=case.id,
                title=case.title,
                passed=scored.passed,
                score=scored.score,
                output=output,
                metrics=scored.metrics,
                error=error_message,
                duration_ms=duration_ms,
            )
        yield {
            "type": "case.completed",
            "run_id": str(run.id),
            "result": {
                "id": result.id,
                "case_id": result.case_id,
                "title": result.title,
                "passed": result.passed,
                "score": result.score,
                "duration_ms": result.duration_ms,
                "error": result.error,
                "metrics": result.metrics,
                "output": result.output,
            },
        }

    duration_ms = round((time.monotonic() - suite_started) * 1000)
    suite_score = round(sum(scores) / max(len(scores), 1), 4)
    async with session.begin():
        current = await session.get(AgentEvalRun, run.id, with_for_update=True)
        if current is None:
            raise RuntimeError("Eval run disappeared")
        current.status = "completed"
        current.passed_count = passed_count
        current.score = suite_score
        current.duration_ms = duration_ms
        current.completed_at = _now()
    yield {
        "type": "eval.completed",
        "run": {
            "id": str(run.id),
            "status": "completed",
            "case_count": len(cases),
            "passed_count": passed_count,
            "score": suite_score,
            "duration_ms": duration_ms,
        },
    }
