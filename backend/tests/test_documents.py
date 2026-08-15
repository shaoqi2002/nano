import unittest
from io import BytesIO

from docx import Document as WordDocument

from app.api.document import valid_range_header
from app.service.document import (
    InvalidDocumentError,
    decode_text,
    preview_kind_for,
    safe_filename,
    word_text,
)


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

    def test_range_header_validation(self) -> None:
        self.assertTrue(valid_range_header("bytes=0-1023"))
        self.assertTrue(valid_range_header("bytes=1024-"))
        self.assertTrue(valid_range_header("bytes=-512"))
        self.assertFalse(valid_range_header("bytes=-"))
        self.assertFalse(valid_range_header("bytes=20-10"))
        self.assertFalse(valid_range_header("bytes=0-1,4-5"))


if __name__ == "__main__":
    unittest.main()
