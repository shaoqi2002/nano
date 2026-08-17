import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.tools.local_read import (
    LocalPathError,
    ensure_workspace_directory,
    local_list_files,
    local_read_text,
    local_search_files,
)


class LocalReadToolTests(unittest.TestCase):
    def test_lists_reads_and_searches_inside_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "notes").mkdir()
            (root / "notes" / "hello.md").write_text("你好 Nano", encoding="utf-8")
            with patch("app.tools.local_read.AGENT_WORKSPACE_DIR", root):
                listing = local_list_files.invoke({"relative_path": "."})
                content = local_read_text.invoke({"relative_path": "notes/hello.md"})
                search = local_search_files.invoke({"pattern": "*.md"})

            self.assertEqual(listing["entries"][0]["path"], "notes")
            self.assertEqual(content["content"], "你好 Nano")
            self.assertEqual(search["matches"][0]["path"], "notes/hello.md")

    def test_rejects_workspace_escape(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with patch("app.tools.local_read.AGENT_WORKSPACE_DIR", Path(directory)):
                with self.assertRaises(LocalPathError):
                    local_read_text.invoke({"relative_path": "../secret.txt"})

    def test_initializes_workspace_and_missing_subdirectory_is_empty(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "workspace"
            with patch("app.tools.local_read.AGENT_WORKSPACE_DIR", root):
                self.assertEqual(ensure_workspace_directory(), root.resolve())
                result = local_list_files.invoke({"relative_path": "not-created"})

            self.assertTrue(root.is_dir())
            self.assertFalse(result["exists"])
            self.assertEqual(result["entries"], [])


if __name__ == "__main__":
    unittest.main()
