import json
import unittest
from unittest.mock import patch

import httpx
from langchain_core.tools import ToolException

from app.tools.deep_research import _research_tavily, create_deep_research_tool


class DeepResearchTests(unittest.IsolatedAsyncioTestCase):
    async def test_research_submits_polls_and_normalizes_result(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.method == "POST":
                body = json.loads(request.content)
                self.assertEqual(body["input"], "compare agent frameworks")
                self.assertEqual(body["model"], "pro")
                self.assertFalse(body["stream"])
                self.assertEqual(body["citation_format"], "numbered")
                return httpx.Response(
                    201,
                    json={"request_id": "research-1", "status": "pending"},
                )
            return httpx.Response(
                200,
                json={
                    "request_id": "research-1",
                    "status": "completed",
                    "content": "report with [1]",
                    "sources": [
                        {
                            "title": "Source",
                            "url": "https://example.com/source",
                            "favicon": "https://example.com/favicon.ico",
                        },
                        {"title": "Missing URL"},
                    ],
                },
            )

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            with patch("app.tools.deep_research.asyncio.sleep"):
                result = await _research_tavily(
                    "compare agent frameworks",
                    "test-key",
                    client,
                    model="pro",
                )

        self.assertEqual(len(requests), 2)
        self.assertEqual(
            requests[1].url,
            httpx.URL("https://api.tavily.com/research/research-1"),
        )
        self.assertEqual(requests[1].headers["authorization"], "Bearer test-key")
        self.assertEqual(
            result,
            {
                "status": "completed",
                "request_id": "research-1",
                "content": "report with [1]",
                "sources": [
                    {"title": "Source", "url": "https://example.com/source"}
                ],
            },
        )

    async def test_research_reports_failed_task(self) -> None:
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                201,
                json={
                    "request_id": "research-2",
                    "status": "failed",
                    "error": "quota exceeded",
                },
            )
        )
        async with httpx.AsyncClient(transport=transport) as client:
            with self.assertRaisesRegex(ToolException, "quota exceeded"):
                await _research_tavily("topic", "test-key", client)

    async def test_research_requires_task_id(self) -> None:
        transport = httpx.MockTransport(
            lambda request: httpx.Response(201, json={"status": "pending"})
        )
        async with httpx.AsyncClient(transport=transport) as client:
            with self.assertRaisesRegex(ToolException, "任务 ID"):
                await _research_tavily("topic", "test-key", client)

    async def test_tool_rejects_blank_input(self) -> None:
        deep_research = create_deep_research_tool("test-key")
        with self.assertRaisesRegex(ToolException, "不能为空"):
            await deep_research.ainvoke({"research_input": "   "})

    async def test_tool_has_model_friendly_schema(self) -> None:
        deep_research = create_deep_research_tool("test-key")
        schema = deep_research.args_schema.model_json_schema()
        self.assertIn("research_input", schema["properties"])
        self.assertIn("model", schema["properties"])
        self.assertIn("research_input", schema["required"])
        self.assertNotIn("api_key", schema["properties"])


if __name__ == "__main__":
    unittest.main()
