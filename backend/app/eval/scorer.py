from dataclasses import dataclass
from typing import Any

from app.eval.dataset import EvalCase
from app.eval.citations import citation_report


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
    roles = {
        str(role)
        for event in events
        for role in (
            event.get("agent"), event.get("from_agent"), event.get("to_agent")
        )
        if role
    }
    event_types = {str(event.get("type")) for event in events if event.get("type")}
    citations = citation_report(answer, events)
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
    for role in case.expected_roles:
        checks[f"role:{role}"] = role in roles
    for event_type in case.expected_events:
        checks[f"event:{event_type}"] = event_type in event_types
    if case.min_citations:
        checks["citations:min_count"] = (
            citations["citation_count"] >= case.min_citations
        )
        checks["citations:valid"] = not citations["invalid_urls"]
    if case.require_citation_provenance:
        checks["citations:provenance"] = (
            bool(citations["cited_urls"]) and not citations["ungrounded_urls"]
        )
    if case.max_duration_ms is not None:
        checks["within_latency_budget"] = duration_ms <= case.max_duration_ms

    score = sum(checks.values()) / max(len(checks), 1)
    metrics = {
        "checks": checks,
        "answer_chars": len(answer),
        "duration_ms": duration_ms,
        "tools": sorted(tools),
        "nodes": sorted(nodes),
        "roles": sorted(roles),
        "events": sorted(event_types),
        "citations": citations,
    }
    return EvalScore(
        passed=score >= case.pass_threshold,
        score=round(score, 4),
        metrics=metrics,
    )
