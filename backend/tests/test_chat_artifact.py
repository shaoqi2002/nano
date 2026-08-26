import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.service.chat_artifact import (
    ChatArtifactNotFoundError,
    get_chat_artifact,
    store_chat_artifact,
)
from app.tools.local_write import word_create_document, word_edit_document


class ChatArtifactTests(unittest.TestCase):
    def test_stores_and_resolves_download_without_document_library(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.docx"
            source.write_bytes(b"docx-content")
            artifact_root = root / "artifacts"
            with patch("app.service.chat_artifact.CHAT_ARTIFACT_DIR", artifact_root):
                result = store_chat_artifact(source, "report.docx")
                stored, media_type = get_chat_artifact(result["artifact_id"])

            self.assertEqual(stored.read_bytes(), b"docx-content")
            self.assertEqual(stored.name, "report.docx")
            self.assertIn("wordprocessingml.document", media_type)
            self.assertEqual(result["download_url"], f"/api/artifacts/{result['artifact_id']}")

    def test_missing_artifact_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch(
            "app.service.chat_artifact.CHAT_ARTIFACT_DIR", Path(directory)
        ):
            with self.assertRaises(ChatArtifactNotFoundError):
                get_chat_artifact("00000000-0000-0000-0000-000000000000")

    def test_word_tools_default_to_docx_only(self) -> None:
        self.assertFalse(word_create_document.args_schema.model_fields["create_pdf"].default)
        self.assertFalse(word_edit_document.args_schema.model_fields["create_pdf"].default)


class ChatArtifactToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_word_create_returns_one_direct_download(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch(
            "app.service.chat_artifact.CHAT_ARTIFACT_DIR", Path(directory)
        ):
            result = await word_create_document.ainvoke({
                "filename": "report.docx",
                "title": "Report",
                "blocks": [{"type": "paragraph", "text": "Direct download"}],
            })

        self.assertEqual(len(result["outputs"]), 1)
        output = result["outputs"][0]
        self.assertEqual(output["kind"], "word")
        self.assertEqual(output["filename"], "report.docx")
        self.assertTrue(output["download_url"].startswith("/api/artifacts/"))
        self.assertNotIn("document_id", output)


if __name__ == "__main__":
    unittest.main()
