import unittest

from app.tools import create_tools


class ToolsTests(unittest.TestCase):
    def test_no_tavily_key_disables_web_tools(self) -> None:
        self.assertEqual(create_tools(None), [])
        self.assertEqual(create_tools("   "), [])

    def test_tavily_key_registers_search_extract_and_research(self) -> None:
        tools = create_tools("test-key")
        self.assertEqual(
            [registered.name for registered in tools],
            ["web_search", "web_extract", "deep_research"],
        )


if __name__ == "__main__":
    unittest.main()
