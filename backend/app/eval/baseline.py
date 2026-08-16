from typing import Any


def compare_case(score: float, baseline: dict[str, Any]) -> dict[str, Any]:
    baseline_score = float(baseline["score"])
    return {
        "score": round(baseline_score, 4),
        "score_delta": round(score - baseline_score, 4),
        "passed": bool(baseline["passed"]),
    }


def compare_suite(
    *,
    run_id: str,
    current_scores: dict[str, float],
    baseline_results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    matched_ids = [case_id for case_id in current_scores if case_id in baseline_results]
    baseline_score = sum(
        float(baseline_results[case_id]["score"]) for case_id in matched_ids
    ) / max(len(matched_ids), 1)
    current_score = sum(current_scores[case_id] for case_id in matched_ids) / max(
        len(matched_ids), 1
    )
    return {
        "run_id": run_id,
        "matched_case_count": len(matched_ids),
        "baseline_score": round(baseline_score, 4),
        "current_score": round(current_score, 4),
        "score_delta": round(current_score - baseline_score, 4),
    }
