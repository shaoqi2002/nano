import unittest

from app.tools import create_tools


class ToolsTests(unittest.TestCase):
    def test_no_tavily_key_disables_web_tools(self) -> None:
        self.assertEqual(
            [tool.name for tool in create_tools(None)],
            ["local_system_status", "local_list_files", "local_read_text", "local_search_files"],
        )

    def test_tavily_key_registers_search_extract_and_research(self) -> None:
        tools = create_tools("test-key")
        self.assertEqual(
            [registered.name for registered in tools],
            [
                "local_system_status", "local_list_files", "local_read_text", "local_search_files",
                "web_search", "web_extract", "deep_research",
            ],
        )


if __name__ == "__main__":
    unittest.main()
