import tempfile
import unittest
from pathlib import Path

from pptx import Presentation

from app.service.presentation_artifact import (
    create_presentation,
    edit_presentation,
    presentation_text,
)


class PresentationArtifactTests(unittest.TestCase):
    def test_creates_structured_widescreen_presentation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "generated.pptx"
            create_presentation(
                output,
                "Nano 演示",
                "聊天中直接生成",
                [
                    {
                        "type": "content",
                        "title": "核心能力",
                        "blocks": [
                            {"type": "heading", "text": "聊天式工作流"},
                            {"type": "bullets", "items": ["创建 PPT", "编辑附件"]},
                        ],
                    },
                    {
                        "type": "table",
                        "title": "功能清单",
                        "headers": ["功能", "状态"],
                        "rows": [["生成", "可用"], ["编辑", "可用"]],
                    },
                ],
            )
            deck = Presentation(output)

            self.assertEqual(len(deck.slides), 3)
            self.assertGreater(deck.slide_width, deck.slide_height)
            extracted = presentation_text(output.read_bytes())
            self.assertIn("Nano 演示", extracted)
            self.assertIn("编辑附件", extracted)
            self.assertIn("功能\t状态", extracted)

    def test_edits_copy_without_modifying_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pptx"
            output = root / "edited.pptx"
            create_presentation(
                source,
                "原始标题",
                "",
                [{"type": "content", "title": "旧内容", "blocks": []}],
            )
            summary = edit_presentation(
                source,
                output,
                [
                    {"type": "replace_text", "old": "旧内容", "new": "新内容"},
                    {
                        "type": "append_slides",
                        "slides": [{"type": "section", "title": "附录"}],
                    },
                ],
            )

            self.assertEqual(summary["replacements"], 1)
            self.assertEqual(summary["appended_slides"], 1)
            self.assertIn("旧内容", presentation_text(source.read_bytes()))
            self.assertIn("新内容", presentation_text(output.read_bytes()))
            self.assertEqual(len(Presentation(output).slides), 3)


if __name__ == "__main__":
    unittest.main()
