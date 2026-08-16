import unittest

import httpx

from app.service.deepseek_account import (
    DEEPSEEK_BALANCE_URL,
    DeepSeekBalanceError,
    fetch_deepseek_balance,
)


class DeepSeekAccountTests(unittest.IsolatedAsyncioTestCase):
    async def test_fetches_and_validates_balance(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url, httpx.URL(DEEPSEEK_BALANCE_URL))
            self.assertEqual(request.headers["Authorization"], "Bearer sk-test")
            return httpx.Response(200, json={
                "is_available": True,
                "balance_infos": [{
                    "currency": "CNY",
                    "total_balance": "110.00",
                    "granted_balance": "10.00",
                    "topped_up_balance": "100.00",
                }],
            })

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as client:
            balance = await fetch_deepseek_balance(client, "sk-test")

        self.assertTrue(balance.is_available)
        self.assertEqual(balance.balance_infos[0].total_balance, "110.00")

    async def test_reports_invalid_api_key_without_leaking_provider_body(self) -> None:
        async def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": "provider secret details"})

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as client:
            with self.assertRaises(DeepSeekBalanceError) as context:
                await fetch_deepseek_balance(client, "bad-key")

        self.assertEqual(context.exception.status_code, 401)
        self.assertEqual(context.exception.message, "DeepSeek API Key 无效")

    async def test_rejects_malformed_balance_response(self) -> None:
        async def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"is_available": True})

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as client:
            with self.assertRaises(DeepSeekBalanceError) as context:
                await fetch_deepseek_balance(client, "sk-test")

        self.assertEqual(context.exception.status_code, 502)


if __name__ == "__main__":
    unittest.main()
