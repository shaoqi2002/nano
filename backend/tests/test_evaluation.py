import unittest

from app.eval.dataset import EvalCase, load_golden_dataset
from app.eval.scorer import score_agent_output
from app.eval.judge import JudgeVerdict, combine_with_judge


class EvaluationTests(unittest.TestCase):
    def test_golden_dataset_has_unique_cases(self) -> None:
        dataset = load_golden_dataset()
        ids = [case.id for case in dataset.cases]

        self.assertEqual(dataset.version, "golden-v1")
        self.assertGreaterEqual(len(ids), 5)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(any(case.mode == "research" for case in dataset.cases))

    def test_scorer_checks_content_tools_nodes_and_latency(self) -> None:
        case = EvalCase(
            id="complete",
            title="Complete",
            prompt="test",
            required_terms=["evidence"],
            forbidden_terms=["guess"],
            expected_tools=["web_search"],
            expected_nodes=["reviewer"],
            min_chars=10,
            max_duration_ms=1000,
        )
        events = [
            {"type": "tool.started", "name": "web_search"},
            {"type": "node.completed", "node": "reviewer"},
        ]

        score = score_agent_output(
            case, "verified evidence from a source", events, 500
        )

        self.assertTrue(score.passed)
        self.assertEqual(score.score, 1.0)
        self.assertTrue(all(score.metrics["checks"].values()))

    def test_scorer_reports_failed_expectations(self) -> None:
        case = EvalCase(
            id="failed",
            title="Failed",
            prompt="test",
            required_terms=["required"],
            expected_tools=["web_search"],
            pass_threshold=1.0,
        )

        score = score_agent_output(case, "an answer", [], 10)

        self.assertFalse(score.passed)
        self.assertFalse(score.metrics["checks"]["contains:required"])
        self.assertFalse(score.metrics["checks"]["tool:web_search"])

    def test_judge_score_is_weighted_and_explained(self) -> None:
        deterministic = score_agent_output(
            EvalCase(id="judge", title="Judge", prompt="test"),
            "answer",
            [],
            10,
        )
        verdict = JudgeVerdict(
            correctness=4,
            completeness=4,
            groundedness=3,
            instruction_following=5,
            reason="Mostly correct and follows the request.",
        )

        combined = combine_with_judge(
            deterministic,
            verdict,
            judge_weight=0.5,
            pass_threshold=0.8,
        )

        self.assertEqual(verdict.normalized_score, 0.8)
        self.assertEqual(combined.score, 0.9)
        self.assertTrue(combined.passed)
        self.assertEqual(combined.metrics["judge"]["reason"], verdict.reason)

    def test_critical_judge_error_forces_failure(self) -> None:
        deterministic = score_agent_output(
            EvalCase(id="critical", title="Critical", prompt="test"),
            "answer",
            [],
            10,
        )
        verdict = JudgeVerdict(
            correctness=5,
            completeness=5,
            groundedness=5,
            instruction_following=5,
            critical_error=True,
            reason="Contains a fabricated source.",
        )

        combined = combine_with_judge(
            deterministic,
            verdict,
            judge_weight=0.5,
            pass_threshold=0.8,
        )

        self.assertEqual(combined.score, 1.0)
        self.assertFalse(combined.passed)


if __name__ == "__main__":
    unittest.main()
