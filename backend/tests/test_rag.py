import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.model.document import Document
from app.service.rag import build_rag_context, parse_document_chunks, public_sources


class RagParsingTests(unittest.TestCase):
    def test_markdown_preserves_heading_and_splits_content(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "notes.md"
            path.write_text("# 第一章\n\n" + "这是测试内容。" * 150, encoding="utf-8")
            document = Document(
                original_name="notes.md",
                object_key="documents/test/original.md",
                content_type="text/markdown",
                preview_kind="markdown",
                size_bytes=path.stat().st_size,
                checksum_sha256="0" * 64,
            )

            chunks = parse_document_chunks(document, path)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(chunk.section_title == "第一章" for chunk in chunks))
        self.assertTrue(all(chunk.content_hash for chunk in chunks))

    def test_context_labels_and_public_sources(self) -> None:
        sources = [{
            "document_id": "00000000-0000-0000-0000-000000000001",
            "document_name": "manual.pdf",
            "chunk_id": 1,
            "page_number": 3,
            "section_title": None,
            "excerpt": "摘要",
            "similarity": 0.9,
            "content": "内部全文",
        }]

        self.assertIn("[来源 1] manual.pdf，第 3 页", build_rag_context(sources))
        self.assertNotIn("content", public_sources(sources)[0])


if __name__ == "__main__":
    unittest.main()
