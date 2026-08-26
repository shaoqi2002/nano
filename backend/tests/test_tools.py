import unittest

from app.tools import create_tools


class ToolsTests(unittest.TestCase):
    def test_no_tavily_key_disables_web_tools(self) -> None:
        self.assertEqual(
            [tool.name for tool in create_tools(None)],
            [
                "local_system_status", "local_list_files", "local_read_text", "local_search_files",
                "local_write_text", "local_move_file", "word_create_document",
                "word_edit_document", "word_convert_to_pdf",
                "presentation_create", "presentation_edit_attachment",
            ],
        )

    def test_tavily_key_registers_search_extract_and_research(self) -> None:
        tools = create_tools("test-key")
        self.assertEqual(
            [registered.name for registered in tools],
            [
                "local_system_status", "local_list_files", "local_read_text", "local_search_files",
                "local_write_text", "local_move_file", "word_create_document",
                "word_edit_document", "word_convert_to_pdf",
                "presentation_create", "presentation_edit_attachment",
                "web_search", "web_extract", "deep_research",
            ],
        )


if __name__ == "__main__":
    unittest.main()
