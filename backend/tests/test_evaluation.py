import unittest

from app.eval.dataset import EvalCase, load_golden_dataset
from app.eval.scorer import score_agent_output


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


if __name__ == "__main__":
    unittest.main()
