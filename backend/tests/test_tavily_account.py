import unittest

import httpx

from app.service.tavily_account import (
    TAVILY_USAGE_URL,
    TavilyUsageError,
    fetch_tavily_usage,
)


class TavilyAccountTests(unittest.IsolatedAsyncioTestCase):
    async def test_fetches_key_and_account_usage(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url, httpx.URL(TAVILY_USAGE_URL))
            self.assertEqual(request.headers["Authorization"], "Bearer tvly-test")
            return httpx.Response(200, json={
                "key": {
                    "usage": 150,
                    "limit": 1000,
                    "search_usage": 100,
                    "extract_usage": 25,
                    "crawl_usage": 15,
                    "map_usage": 7,
                    "research_usage": 3,
                },
                "account": {
                    "current_plan": "Bootstrap",
                    "plan_usage": 500,
                    "plan_limit": 15000,
                    "paygo_usage": 25,
                    "paygo_limit": 100,
                    "search_usage": 350,
                    "extract_usage": 75,
                    "crawl_usage": 50,
                    "map_usage": 15,
                    "research_usage": 10,
                },
            })

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as client:
            usage = await fetch_tavily_usage(client, "tvly-test")

        self.assertEqual(usage.key.limit - usage.key.usage, 850)
        self.assertEqual(usage.account.current_plan, "Bootstrap")

    async def test_reports_invalid_key(self) -> None:
        async def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(401)

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as client:
            with self.assertRaises(TavilyUsageError) as context:
                await fetch_tavily_usage(client, "bad-key")

        self.assertEqual(context.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
