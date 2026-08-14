import json
import unittest

import httpx
from langchain_core.tools import ToolException

from app.tools.websearch import _search_tavily, create_web_search_tool


class WebSearchTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_returns_normalized_and_limited_results(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url, httpx.URL("https://api.tavily.com/search"))
            self.assertEqual(request.headers["authorization"], "Bearer test-key")
            request_body = json.loads(request.content)
            self.assertEqual(request_body["search_depth"], "advanced")
            self.assertEqual(request_body["chunks_per_source"], 3)
            self.assertEqual(request_body["topic"], "news")
            self.assertEqual(request_body["time_range"], "week")
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "title": "Example",
                            "url": "https://example.com",
                            "content": "Useful search result",
                            "score": 0.95,
                            "published_date": "2026-08-14",
                        }
                    ]
                },
            )

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            result = await _search_tavily(
                "nano agent",
                "test-key",
                client,
                depth="advanced",
                topic="news",
                time_range="week",
            )

        self.assertEqual(result["query"], "nano agent")
        self.assertEqual(result["search_depth"], "advanced")
        self.assertEqual(result["topic"], "news")
        self.assertEqual(result["time_range"], "week")
        self.assertEqual(
            result["results"],
            [
                {
                    "title": "Example",
                    "url": "https://example.com",
                    "snippet": "Useful search result",
                    "score": 0.95,
                    "published_date": "2026-08-14",
                }
            ],
        )

    async def test_search_converts_http_error_to_tool_error(self) -> None:
        transport = httpx.MockTransport(
            lambda request: httpx.Response(429, request=request)
        )
        async with httpx.AsyncClient(transport=transport) as client:
            with self.assertRaisesRegex(ToolException, "HTTP 429"):
                await _search_tavily("nano agent", "test-key", client)

    async def test_tool_rejects_blank_query_before_network_request(self) -> None:
        web_search = create_web_search_tool("test-key")
        with self.assertRaisesRegex(ToolException, "不能为空"):
            await web_search.ainvoke({"query": "   "})

    async def test_tool_has_model_friendly_schema(self) -> None:
        web_search = create_web_search_tool("test-key")
        schema = web_search.args_schema.model_json_schema()
        self.assertIn("query", schema["properties"])
        self.assertIn("depth", schema["properties"])
        self.assertIn("topic", schema["properties"])
        self.assertIn("time_range", schema["properties"])
        self.assertIn("query", schema["required"])
        self.assertNotIn("api_key", schema["properties"])

    async def test_result_is_json_serializable(self) -> None:
        transport = httpx.MockTransport(
            lambda request: httpx.Response(200, json={"results": []})
        )
        async with httpx.AsyncClient(transport=transport) as client:
            result = await _search_tavily("nothing", "test-key", client)

        self.assertEqual(json.loads(json.dumps(result)), result)


if __name__ == "__main__":
    unittest.main()
