import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.model.document import Document
from app.service.rag import (
    build_rag_context,
    parse_document_chunks,
    public_sources,
    select_relevant_sources,
)


class RagParsingTests(unittest.TestCase):
    def test_relevance_gate_rejects_unrelated_query(self) -> None:
        candidates = [
            {"chunk_id": 1, "similarity": 0.44},
            {"chunk_id": 2, "similarity": 0.38},
        ]

        with (
            patch("app.service.rag.RAG_MIN_SIMILARITY", 0.25),
            patch("app.service.rag.RAG_QUERY_MIN_SIMILARITY", 0.45),
        ):
            self.assertEqual(select_relevant_sources(candidates), [])

    def test_relevance_gate_keeps_only_candidates_close_to_best_match(self) -> None:
        candidates = [
            {"chunk_id": 3, "similarity": 0.50},
            {"chunk_id": 1, "similarity": 0.70},
            {"chunk_id": 2, "similarity": 0.61},
        ]

        with (
            patch("app.service.rag.RAG_MIN_SIMILARITY", 0.25),
            patch("app.service.rag.RAG_QUERY_MIN_SIMILARITY", 0.45),
            patch("app.service.rag.RAG_MAX_SCORE_DROP", 0.12),
        ):
            selected = select_relevant_sources(candidates)

        self.assertEqual([source["chunk_id"] for source in selected], [1, 2])

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
