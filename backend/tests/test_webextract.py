import json
import unittest
from unittest.mock import patch

import httpx
from langchain_core.tools import ToolException

from app.tools.webextract import (
    _extract_tavily,
    _validated_urls,
    create_web_extract_tool,
)


class WebExtractTests(unittest.IsolatedAsyncioTestCase):
    async def test_extract_sends_focused_request_and_normalizes_results(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url, httpx.URL("https://api.tavily.com/extract"))
            self.assertEqual(request.headers["authorization"], "Bearer test-key")
            body = json.loads(request.content)
            self.assertEqual(
                body["urls"],
                ["https://example.com/a", "https://example.org/b"],
            )
            self.assertEqual(body["query"], "核实发布日期和主要结论")
            self.assertEqual(body["extract_depth"], "advanced")
            self.assertEqual(body["chunks_per_source"], 5)
            self.assertEqual(body["format"], "markdown")
            self.assertFalse(body["include_images"])
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "url": "https://example.com/a",
                            "raw_content": "source A content",
                        },
                        {
                            "url": "https://example.org/b",
                            "raw_content": "source B content",
                        },
                    ],
                    "failed_results": [
                        {
                            "url": "https://example.net/c",
                            "error": "blocked",
                        }
                    ],
                },
            )

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            result = await _extract_tavily(
                ["https://example.com/a", "https://example.org/b"],
                "核实发布日期和主要结论",
                "test-key",
                client,
            )

        self.assertEqual(
            result["results"],
            [
                {"url": "https://example.com/a", "content": "source A content"},
                {"url": "https://example.org/b", "content": "source B content"},
            ],
        )
        self.assertEqual(
            result["failed_results"],
            [{"url": "https://example.net/c", "error": "blocked"}],
        )

    async def test_extract_converts_http_error_to_tool_error(self) -> None:
        transport = httpx.MockTransport(
            lambda request: httpx.Response(429, request=request)
        )
        async with httpx.AsyncClient(transport=transport) as client:
            with self.assertRaisesRegex(ToolException, "HTTP 429"):
                await _extract_tavily(
                    ["https://example.com"],
                    "topic",
                    "test-key",
                    client,
                )

    def test_url_validation_deduplicates_and_rejects_private_urls(self) -> None:
        self.assertEqual(
            _validated_urls(
                ["https://example.com/a", "https://example.com/a"]
            ),
            ["https://example.com/a"],
        )
        for url in (
            "file:///etc/passwd",
            "http://localhost/admin",
            "http://127.0.0.1/private",
            "http://user:password@example.com/private",
        ):
            with self.subTest(url=url):
                with self.assertRaises(ToolException):
                    _validated_urls([url])

    async def test_tool_rejects_invalid_input_before_network_request(self) -> None:
        web_extract = create_web_extract_tool("test-key")
        with self.assertRaisesRegex(ToolException, "至少需要"):
            await web_extract.ainvoke({"urls": [], "query": "topic"})
        with self.assertRaisesRegex(ToolException, "提取目标不能为空"):
            await web_extract.ainvoke(
                {"urls": ["https://example.com"], "query": "   "}
            )

    async def test_tool_has_model_friendly_schema(self) -> None:
        web_extract = create_web_extract_tool("test-key")
        schema = web_extract.args_schema.model_json_schema()
        self.assertIn("urls", schema["properties"])
        self.assertIn("query", schema["properties"])
        self.assertIn("depth", schema["properties"])
        self.assertIn("urls", schema["required"])
        self.assertIn("query", schema["required"])
        self.assertNotIn("api_key", schema["properties"])

    async def test_result_content_is_distributed_across_sources(self) -> None:
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "results": [
                        {"url": "https://a.example", "raw_content": "a" * 100},
                        {"url": "https://b.example", "raw_content": "b" * 100},
                    ]
                },
            )
        )
        async with httpx.AsyncClient(transport=transport) as client:
            with patch("app.tools.webextract.WEB_EXTRACT_MAX_CONTENT_LENGTH", 20):
                result = await _extract_tavily(
                    ["https://a.example", "https://b.example"],
                    "topic",
                    "test-key",
                    client,
                )

        self.assertEqual(len(result["results"][0]["content"]), 10)
        self.assertEqual(len(result["results"][1]["content"]), 10)
        self.assertLessEqual(
            sum(len(item["content"]) for item in result["results"]),
            20,
        )


if __name__ == "__main__":
    unittest.main()
