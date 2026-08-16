from dataclasses import dataclass
from typing import Any

from app.eval.dataset import EvalCase


@dataclass(frozen=True)
class EvalScore:
    passed: bool
    score: float
    metrics: dict[str, Any]


def score_agent_output(
    case: EvalCase,
    answer: str,
    events: list[dict[str, Any]],
    duration_ms: int,
) -> EvalScore:
    normalized = answer.casefold()
    tools = {
        str(event.get("name"))
        for event in events
        if event.get("type") == "tool.started" and event.get("name")
    }
    nodes = {
        str(event.get("node"))
        for event in events
        if event.get("type") == "node.completed" and event.get("node")
    }
    checks: dict[str, bool] = {
        "completed": bool(answer.strip()),
        "min_chars": len(answer.strip()) >= case.min_chars,
    }
    for term in case.required_terms:
        checks[f"contains:{term}"] = term.casefold() in normalized
    for term in case.forbidden_terms:
        checks[f"excludes:{term}"] = term.casefold() not in normalized
    for tool in case.expected_tools:
        checks[f"tool:{tool}"] = tool in tools
    for node in case.expected_nodes:
        checks[f"node:{node}"] = node in nodes
    if case.max_duration_ms is not None:
        checks["within_latency_budget"] = duration_ms <= case.max_duration_ms

    score = sum(checks.values()) / max(len(checks), 1)
    metrics = {
        "checks": checks,
        "answer_chars": len(answer),
        "duration_ms": duration_ms,
        "tools": sorted(tools),
        "nodes": sorted(nodes),
    }
    return EvalScore(
        passed=score >= case.pass_threshold,
        score=round(score, 4),
        metrics=metrics,
    )
