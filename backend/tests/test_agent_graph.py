import unittest

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver

from app.agent.graph import build_agent_graph, initial_agent_state, resolve_agent_mode
from app.agent.state import ResearchPlan, ResearchTask, ReviewResult
from app.service.agent_run import _safe_trace_value, _trace_payload


class StructuredModel:
    def __init__(self, schema):
        self.schema = schema

    async def ainvoke(self, _messages):
        if self.schema is ResearchPlan:
            return ResearchPlan(
                objective="Compare the evidence",
                tasks=[
                    ResearchTask(id="one", question="Find source one"),
                    ResearchTask(id="two", question="Find source two"),
                ],
                expected_output="A sourced report",
            )
        return ReviewResult(passed=True)


class FakeGraphModel:
    def __init__(self, responses=None):
        self.responses = list(responses or [])

    def bind_tools(self, _tools):
        return self

    def with_structured_output(self, schema):
        return StructuredModel(schema)

    async def ainvoke(self, _messages):
        if self.responses:
            return self.responses.pop(0)
        return AIMessage(content="final research report")

    async def astream(self, _messages):
        if self.responses:
            yield self.responses.pop(0)
        else:
            yield AIMessage(content="research evidence")


def state(run_id: str = "run-1"):
    return initial_agent_state(
        run_id=run_id,
        conversation_id="conversation-1",
        query="research this",
        messages=[HumanMessage(content="research this")],
        rag_sources=[],
    )


class AgentGraphTests(unittest.IsolatedAsyncioTestCase):
    async def test_chat_graph_streams_tool_progress_and_answer(self) -> None:
        @tool
        async def echo(query: str) -> str:
            """Echo a query."""
            return f"result:{query}"

        model = FakeGraphModel([
            AIMessage(
                content="checking",
                tool_calls=[{
                    "name": "echo",
                    "args": {"query": "nano"},
                    "id": "call-1",
                    "type": "tool_call",
                }],
            ),
            AIMessage(content="final answer"),
        ])
        graph = build_agent_graph(model, [echo], "chat", InMemorySaver())
        config = {"configurable": {"thread_id": "run-1"}}
        events = [
            event
            async for event in graph.astream(
                state(), config=config, stream_mode="custom"
            )
        ]

        event_types = [event["type"] for event in events]
        self.assertIn("message.reset", event_types)
        self.assertIn("tool.started", event_types)
        self.assertIn("tool.completed", event_types)
        snapshot = await graph.aget_state(config)
        self.assertEqual(snapshot.values["final_answer"], "final answer")

    async def test_research_graph_plans_fans_out_and_reviews(self) -> None:
        graph = build_agent_graph(
            FakeGraphModel(), [], "research", InMemorySaver()
        )
        config = {"configurable": {"thread_id": "research-1"}}
        events = [
            event
            async for event in graph.astream(
                state("research-1"), config=config, stream_mode="custom"
            )
        ]

        self.assertTrue(any(event["type"] == "plan.ready" for event in events))
        researcher_starts = [
            event for event in events
            if event["type"] == "node.started" and event["node"] in {"one", "two"}
        ]
        self.assertEqual(len(researcher_starts), 2)
        self.assertTrue(any(event["type"] == "review.completed" for event in events))
        snapshot = await graph.aget_state(config)
        self.assertEqual(snapshot.values["final_answer"], "final research report")

    def test_auto_mode_is_predictable(self) -> None:
        self.assertEqual(resolve_agent_mode("auto", "请深入研究这个项目"), "research")
        self.assertEqual(resolve_agent_mode("auto", "你好"), "chat")
        self.assertEqual(resolve_agent_mode("chat", "深入研究"), "chat")

    def test_trace_payload_redacts_secrets_and_drops_deltas(self) -> None:
        payload = _trace_payload({
            "type": "tool.started",
            "name": "example",
            "delta": "do not persist streamed answer",
            "input": {
                "query": "safe",
                "api_key": "secret-key",
                "Authorization": "Bearer secret",
            },
        })

        self.assertNotIn("delta", payload)
        self.assertEqual(payload["input"]["query"], "safe")
        self.assertEqual(payload["input"]["api_key"], "[redacted]")
        self.assertEqual(payload["input"]["Authorization"], "[redacted]")
        self.assertEqual(len(_safe_trace_value("x" * 3000)), 2000)


if __name__ == "__main__":
    unittest.main()
