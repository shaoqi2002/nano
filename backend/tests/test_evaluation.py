import unittest

from langchain_deepseek import ChatDeepSeek
from pydantic import SecretStr

from app.agent.structured import model_for_structured_output
from app.eval.dataset import EVAL_FORM_OPTIONS, EvalCase, load_golden_dataset
from app.eval.baseline import compare_case, compare_suite
from app.eval.scorer import score_agent_output
from app.eval.judge import JudgeVerdict, combine_with_judge
from app.schema.evaluation import EvalCaseDefinition
from app.core.database import Base
import app.model  # noqa: F401


class EvaluationTests(unittest.TestCase):
    def test_baseline_comparison_uses_only_matching_cases(self) -> None:
        baseline_results = {
            "one": {"score": 0.6, "passed": False},
            "old-only": {"score": 1.0, "passed": True},
        }

        case = compare_case(0.8, baseline_results["one"])
        suite = compare_suite(
            run_id="baseline-run",
            current_scores={"one": 0.8, "new-only": 0.2},
            baseline_results=baseline_results,
        )

        self.assertEqual(case["score_delta"], 0.2)
        self.assertEqual(suite["matched_case_count"], 1)
        self.assertEqual(suite["baseline_score"], 0.6)
        self.assertEqual(suite["current_score"], 0.8)
        self.assertEqual(suite["score_delta"], 0.2)

    def test_builtin_case_exclusion_table_is_registered(self) -> None:
        self.assertIn("agent_eval_case_exclusions", Base.metadata.tables)

    def test_custom_case_schema_accepts_supported_agent_modes(self) -> None:
        case = EvalCaseDefinition(
            title="Custom research case",
            prompt="Research this topic",
            mode="research",
        )

        self.assertEqual(case.mode, "research")

    def test_structured_output_disables_thinking_without_mutating_model(self) -> None:
        model = ChatDeepSeek(
            model="deepseek-v4-flash",
            api_key=SecretStr("test-key"),
            extra_body={"existing_option": True},
        )

        configured = model_for_structured_output(model)

        self.assertEqual(model.extra_body, {"existing_option": True})
        self.assertEqual(configured.extra_body, {
            "existing_option": True,
            "thinking": {"type": "disabled"},
        })

    def test_golden_dataset_has_unique_cases(self) -> None:
        dataset = load_golden_dataset()
        ids = [case.id for case in dataset.cases]

        self.assertEqual(dataset.version, "golden-v2")
        self.assertGreaterEqual(len(ids), 10)
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
            expected_roles=["reviewer"],
            expected_events=["review.completed"],
            min_chars=10,
            max_duration_ms=1000,
        )
        events = [
            {"type": "tool.started", "name": "web_search"},
            {"type": "node.completed", "node": "reviewer"},
            {"type": "review.completed", "agent": "reviewer"},
        ]

        score = score_agent_output(
            case, "verified evidence from a source", events, 500
        )

        self.assertTrue(score.passed)
        self.assertEqual(score.score, 1.0)
        self.assertTrue(all(score.metrics["checks"].values()))

    def test_form_options_cover_multi_agent_expectations(self) -> None:
        self.assertIn("web_search", EVAL_FORM_OPTIONS["tools"])
        self.assertIn("reviewer", EVAL_FORM_OPTIONS["roles"])
        self.assertIn("agent.delegated", EVAL_FORM_OPTIONS["events"])
        self.assertIn("researcher_once", EVAL_FORM_OPTIONS["fault_injections"])

    def test_scorer_validates_citation_provenance(self) -> None:
        case = EvalCase(
            id="citations",
            title="Citations",
            prompt="test",
            min_citations=1,
            require_citation_provenance=True,
            pass_threshold=1.0,
        )
        events = [{
            "type": "tool.completed",
            "name": "web_search",
            "urls": ["https://docs.example.com/guide/"],
        }]

        grounded = score_agent_output(
            case,
            "See https://docs.example.com/guide for evidence.",
            events,
            10,
        )
        invented = score_agent_output(
            case,
            "See https://invented.example/report for evidence.",
            events,
            10,
        )

        self.assertTrue(grounded.passed)
        self.assertEqual(grounded.metrics["citations"]["grounded_ratio"], 1.0)
        self.assertFalse(invented.passed)
        self.assertFalse(invented.metrics["checks"]["citations:provenance"])

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
