import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.eval.dataset import EvalCase
from app.eval.scorer import EvalScore
from app.agent.structured import with_structured_output


class JudgeVerdict(BaseModel):
    correctness: int = Field(ge=1, le=5)
    completeness: int = Field(ge=1, le=5)
    groundedness: int = Field(ge=1, le=5)
    instruction_following: int = Field(ge=1, le=5)
    critical_error: bool = False
    reason: str = Field(min_length=1, max_length=1200)

    @property
    def normalized_score(self) -> float:
        total = (
            self.correctness
            + self.completeness
            + self.groundedness
            + self.instruction_following
        )
        return round(total / 20, 4)


def judge_expectations(case: EvalCase) -> dict[str, Any]:
    return {
        "rubric": case.judge_rubric,
        "required_terms": case.required_terms,
        "forbidden_terms": case.forbidden_terms,
        "expected_tools": case.expected_tools,
        "expected_nodes": case.expected_nodes,
        "minimum_characters": case.min_chars,
    }


async def judge_agent_output(
    model: Any,
    case: EvalCase,
    answer: str,
    observed_events: list[dict[str, Any]],
) -> JudgeVerdict:
    tools = sorted({
        str(event.get("name"))
        for event in observed_events
        if event.get("type") == "tool.started" and event.get("name")
    })
    nodes = sorted({
        str(event.get("node"))
        for event in observed_events
        if event.get("type") == "node.completed" and event.get("node")
    })
    payload = {
        "user_prompt": case.prompt,
        "expectations": judge_expectations(case),
        "observed_tools": tools,
        "observed_nodes": nodes,
        "assistant_answer": answer,
    }
    return await with_structured_output(model, JudgeVerdict).ainvoke([
        SystemMessage(content=(
            "你是严格、独立的 Agent 评测员。按 1 到 5 分分别评价正确性、完整性、"
            "依据性和指令遵循。不要因为文风华丽而加分。无法从提供材料验证的事实应降低"
            "依据性；编造来源、严重事实错误或违背核心指令时 critical_error=true。"
        )),
        HumanMessage(content=json.dumps(payload, ensure_ascii=False)),
    ])


def combine_with_judge(
    deterministic: EvalScore,
    verdict: JudgeVerdict,
    *,
    judge_weight: float,
    pass_threshold: float,
) -> EvalScore:
    weight = min(max(judge_weight, 0.0), 1.0)
    final_score = round(
        deterministic.score * (1 - weight) + verdict.normalized_score * weight,
        4,
    )
    metrics = {
        **deterministic.metrics,
        "deterministic_score": deterministic.score,
        "judge": {
            **verdict.model_dump(),
            "normalized_score": verdict.normalized_score,
            "weight": weight,
        },
    }
    return EvalScore(
        passed=final_score >= pass_threshold and not verdict.critical_error,
        score=final_score,
        metrics=metrics,
    )
