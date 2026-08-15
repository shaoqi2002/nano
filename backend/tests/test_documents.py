import unittest
import hashlib
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from docx import Document as WordDocument

from app.service.document import (
    InvalidDocumentError,
    decode_text,
    preview_kind_for,
    safe_filename,
    word_text,
)
from app.service.document_cache import DocumentCache, DocumentCacheError


class DocumentServiceTests(unittest.TestCase):
    def test_safe_filename_removes_client_paths(self) -> None:
        self.assertEqual(safe_filename("C:\\fakepath\\报告.pdf"), "报告.pdf")
        self.assertEqual(safe_filename("../../notes.md"), "notes.md")

    def test_preview_kind_accepts_supported_extensions_case_insensitively(self) -> None:
        self.assertEqual(preview_kind_for("manual.PDF"), "pdf")
        self.assertEqual(preview_kind_for("notes.md"), "markdown")
        self.assertEqual(preview_kind_for("report.docx"), "word")

    def test_preview_kind_rejects_active_content(self) -> None:
        with self.assertRaisesRegex(InvalidDocumentError, "不支持"):
            preview_kind_for("page.html")
        with self.assertRaisesRegex(InvalidDocumentError, "不支持"):
            preview_kind_for("image.svg")

    def test_decode_text_supports_utf8_and_common_chinese_encoding(self) -> None:
        self.assertEqual(decode_text("你好".encode()), "你好")
        self.assertEqual(decode_text("你好".encode("gb18030")), "你好")

    def test_word_text_extracts_paragraphs_and_tables(self) -> None:
        document = WordDocument()
        document.add_paragraph("标题")
        table = document.add_table(rows=1, cols=2)
        table.cell(0, 0).text = "名称"
        table.cell(0, 1).text = "Nano"
        stream = BytesIO()
        document.save(stream)

        extracted = word_text(stream.getvalue())

        self.assertIn("标题", extracted)
        self.assertIn("名称\tNano", extracted)



class DocumentCacheTests(unittest.TestCase):
    def test_downloads_once_then_uses_cached_file(self) -> None:
        payload = b"cached document"
        checksum = hashlib.sha256(payload).hexdigest()
        calls = []
        with TemporaryDirectory() as directory:
            cache = DocumentCache(Path(directory), maximum_bytes=1024)

            def download(object_key: str, destination: Path) -> None:
                calls.append(object_key)
                destination.write_bytes(payload)

            first = cache.ensure("documents/1/original.pdf", len(payload), checksum, download)
            second = cache.ensure("documents/1/original.pdf", len(payload), checksum, download)

            self.assertEqual(first, second)
            self.assertEqual(first.read_bytes(), payload)
            self.assertEqual(calls, ["documents/1/original.pdf"])

    def test_rejects_download_with_wrong_checksum(self) -> None:
        payload = b"expected"
        checksum = hashlib.sha256(payload).hexdigest()
        with TemporaryDirectory() as directory:
            cache = DocumentCache(Path(directory), maximum_bytes=1024)

            with self.assertRaisesRegex(DocumentCacheError, "校验失败"):
                cache.ensure(
                    "documents/1/original.pdf",
                    len(payload),
                    checksum,
                    lambda _key, destination: destination.write_bytes(b"tampered"),
                )

            self.assertFalse(cache.path_for("documents/1/original.pdf").exists())

    def test_evicts_oldest_file_when_capacity_is_reached(self) -> None:
        first_payload = b"first"
        second_payload = b"second"
        with TemporaryDirectory() as directory:
            cache = DocumentCache(Path(directory), maximum_bytes=len(second_payload))
            first_path = cache.store_stream(
                "documents/1/original.txt",
                BytesIO(first_payload),
                len(first_payload),
                hashlib.sha256(first_payload).hexdigest(),
            )
            second_path = cache.store_stream(
                "documents/2/original.txt",
                BytesIO(second_payload),
                len(second_payload),
                hashlib.sha256(second_payload).hexdigest(),
            )

            self.assertFalse(first_path.exists())
            self.assertEqual(second_path.read_bytes(), second_payload)


if __name__ == "__main__":
    unittest.main()
