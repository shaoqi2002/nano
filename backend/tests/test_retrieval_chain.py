import unittest
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool

from app.service.conversation import invoke_model_with_tools


class FakeModel:
    def __init__(self, responses: list[AIMessage]) -> None:
        self.responses = list(responses)
        self.invocations: list[list[Any]] = []

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        self.invocations.append(list(messages))
        return self.responses.pop(0)


class RetrievalChainTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_then_extract_then_answer(self) -> None:
        calls: list[str] = []

        @tool
        async def web_search(query: str) -> str:
            """Discover sources."""
            calls.append("search")
            return '{"results":[{"url":"https://example.com/source"}]}'

        @tool
        async def web_extract(urls: list[str], query: str) -> str:
            """Read source content."""
            calls.append("extract")
            return '{"results":[{"url":"https://example.com/source","content":"evidence"}]}'

        model = FakeModel(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "web_search",
                            "args": {"query": "current topic"},
                            "id": "search-1",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "web_extract",
                            "args": {
                                "urls": ["https://example.com/source"],
                                "query": "verify the claim",
                            },
                            "id": "extract-1",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(content="answer with https://example.com/source"),
            ]
        )

        response = await invoke_model_with_tools(
            model,
            [web_search, web_extract],
            [HumanMessage(content="research this")],
        )

        self.assertEqual(calls, ["search", "extract"])
        self.assertEqual(response.content, "answer with https://example.com/source")
        tool_messages = [
            message
            for invocation in model.invocations
            for message in invocation
            if isinstance(message, ToolMessage)
        ]
        self.assertTrue(any(message.tool_call_id == "search-1" for message in tool_messages))
        self.assertTrue(any(message.tool_call_id == "extract-1" for message in tool_messages))


if __name__ == "__main__":
    unittest.main()
