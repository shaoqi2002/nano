from pathlib import Path
from typing import Any
from io import BytesIO
from zipfile import BadZipFile, ZipFile

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.util import Inches, Pt


NAVY = RGBColor(0x13, 0x26, 0x3D)
BLUE = RGBColor(0x2E, 0x74, 0xB5)
LIGHT_BLUE = RGBColor(0xE9, 0xF2, 0xFA)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
DARK = RGBColor(0x20, 0x2A, 0x35)
GRAY = RGBColor(0x67, 0x72, 0x7E)
LIGHT_GRAY = RGBColor(0xF3, 0xF5, 0xF7)


class PresentationArtifactError(RuntimeError):
    pass


def presentation_text(content: bytes) -> str:
    try:
        with ZipFile(BytesIO(content)) as archive:
            entries = archive.infolist()
            if len(entries) > 10_000 or sum(item.file_size for item in entries) > 80 * 1024 * 1024:
                raise PresentationArtifactError("PPTX 解压后内容过大")
            if "ppt/presentation.xml" not in {item.filename for item in entries}:
                raise PresentationArtifactError("PPTX 缺少演示文稿内容")
        presentation = Presentation(BytesIO(content))
    except PresentationArtifactError:
        raise
    except BadZipFile as error:
        raise PresentationArtifactError("PPTX 文件无法解析") from error
    except Exception as error:
        raise PresentationArtifactError("PPTX 文件无法解析") from error
    slides: list[str] = []
    for index, slide in enumerate(presentation.slides, start=1):
        blocks: list[str] = []
        for shape in slide.shapes:
            if getattr(shape, "has_text_frame", False):
                text = shape.text.strip()
                if text:
                    blocks.append(text)
            if getattr(shape, "has_table", False):
                for row in shape.table.rows:
                    blocks.append("\t".join(cell.text.strip() for cell in row.cells))
        if blocks:
            slides.append(f"[幻灯片 {index}]\n" + "\n".join(blocks))
    return "\n\n".join(slides)


def _set_run_font(run, size: float, *, bold: bool = False, color=DARK) -> None:
    run.font.name = "Aptos"
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color


def _add_textbox(
    slide,
    left: float,
    top: float,
    width: float,
    height: float,
    text: str,
    *,
    size: float = 20,
    bold: bool = False,
    color=DARK,
    align=PP_ALIGN.LEFT,
    vertical=MSO_ANCHOR.TOP,
):
    shape = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    frame = shape.text_frame
    frame.clear()
    frame.word_wrap = True
    frame.vertical_anchor = vertical
    paragraph = frame.paragraphs[0]
    paragraph.alignment = align
    paragraph.space_after = Pt(0)
    run = paragraph.add_run()
    run.text = str(text)
    _set_run_font(run, size, bold=bold, color=color)
    return shape


def _add_slide_header(slide, title: str, number: int) -> None:
    accent = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(0.18), Inches(7.5)
    )
    accent.fill.solid()
    accent.fill.fore_color.rgb = BLUE
    accent.line.fill.background()
    _add_textbox(slide, 0.68, 0.48, 11.6, 0.62, title, size=28, bold=True, color=NAVY)
    _add_textbox(
        slide, 12.15, 0.57, 0.55, 0.35, str(number), size=11, color=GRAY,
        align=PP_ALIGN.RIGHT,
    )
    line = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(0.68), Inches(1.18), Inches(12.0), Inches(0.025)
    )
    line.fill.solid()
    line.fill.fore_color.rgb = LIGHT_BLUE
    line.line.fill.background()


def _add_bullets(frame, items: list[Any], *, numbered: bool = False, font_size: float = 20) -> None:
    frame.clear()
    frame.word_wrap = True
    if not items:
        items = [""]
    for index, item in enumerate(items):
        paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
        if isinstance(item, dict):
            text = str(item.get("text") or "")
            level = min(max(int(item.get("level", 0)), 0), 4)
        else:
            text = str(item)
            level = 0
        if numbered and level == 0:
            paragraph.text = f"{index + 1}. {text}"
        else:
            paragraph.text = f"{'  ' * level}• {text}"
        paragraph.level = level
        paragraph.space_after = Pt(10)
        paragraph.line_spacing = 1.12
        for run in paragraph.runs:
            _set_run_font(run, max(15, font_size - level * 2), color=DARK)


def _add_content_block(slide, block: dict[str, Any], left: float, top: float, width: float) -> float:
    kind = str(block.get("type") or "paragraph")
    if kind == "heading":
        _add_textbox(slide, left, top, width, 0.42, str(block.get("text") or ""), size=20, bold=True, color=BLUE)
        return 0.52
    if kind == "paragraph":
        text = str(block.get("text") or "")
        height = min(1.55, max(0.48, 0.34 + len(text) / 115))
        _add_textbox(slide, left, top, width, height, text, size=18)
        return height + 0.12
    if kind in {"bullets", "numbered"}:
        items = list(block.get("items") or [])
        height = min(3.9, max(0.62, 0.46 * len(items)))
        shape = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
        _add_bullets(shape.text_frame, items, numbered=kind == "numbered", font_size=18)
        return height + 0.12
    if kind == "quote":
        height = 1.0
        box = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE, Inches(left), Inches(top), Inches(width), Inches(height)
        )
        box.fill.solid()
        box.fill.fore_color.rgb = LIGHT_BLUE
        box.line.fill.background()
        _add_textbox(slide, left + 0.25, top + 0.18, width - 0.5, 0.65, str(block.get("text") or ""), size=18, color=NAVY)
        return height + 0.16
    raise PresentationArtifactError(f"不支持的内容块：{kind}")


def _add_table_slide(slide, spec: dict[str, Any], number: int) -> None:
    _add_slide_header(slide, str(spec.get("title") or ""), number)
    headers = [str(value) for value in spec.get("headers") or []]
    rows = [[str(value) for value in row] for row in spec.get("rows") or []]
    columns = len(headers) or (len(rows[0]) if rows else 0)
    if not columns or any(len(row) != columns for row in rows):
        raise PresentationArtifactError("表格列数不一致")
    table_shape = slide.shapes.add_table(
        len(rows) + (1 if headers else 0), columns,
        Inches(0.75), Inches(1.55), Inches(11.85), Inches(4.95),
    )
    table = table_shape.table
    values = ([headers] if headers else []) + rows
    for row_index, values_row in enumerate(values):
        for column_index, value in enumerate(values_row):
            cell = table.cell(row_index, column_index)
            cell.text = value
            cell.margin_left = Inches(0.12)
            cell.margin_right = Inches(0.12)
            cell.margin_top = Inches(0.08)
            cell.margin_bottom = Inches(0.08)
            cell.fill.solid()
            cell.fill.fore_color.rgb = NAVY if headers and row_index == 0 else (LIGHT_GRAY if row_index % 2 == 0 else WHITE)
            for paragraph in cell.text_frame.paragraphs:
                for run in paragraph.runs:
                    _set_run_font(run, 15, bold=headers and row_index == 0, color=WHITE if headers and row_index == 0 else DARK)


def _first_value(spec: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = spec.get(key)
        if value not in (None, "", []):
            return value
    return None


def _normalize_blocks(value: Any) -> list[dict[str, Any]]:
    if value in (None, "", []):
        return []
    if isinstance(value, str):
        return [{"type": "paragraph", "text": value}]
    if isinstance(value, dict):
        if value.get("type"):
            return [dict(value)]
        nested = _first_value(value, "blocks", "content", "body", "text")
        return _normalize_blocks(nested)
    if isinstance(value, list):
        if all(isinstance(item, dict) and item.get("type") for item in value):
            return [dict(item) for item in value]
        return [{"type": "bullets", "items": value}]
    return [{"type": "paragraph", "text": str(value)}]


def _normalize_slide_spec(raw: dict[str, Any]) -> dict[str, Any]:
    spec = dict(raw)
    requested_kind = str(_first_value(spec, "type", "layout", "kind") or "content").lower()
    kind_aliases = {
        "title": "section",
        "title_slide": "section",
        "title-only": "section",
        "title_only": "section",
        "title_and_content": "content",
        "title-and-content": "content",
        "bullet": "content",
        "bullets": "content",
        "text": "content",
        "two-column": "two_column",
        "two columns": "two_column",
        "comparison": "two_column",
    }
    kind = kind_aliases.get(requested_kind, requested_kind)
    if "headers" in spec or "rows" in spec:
        kind = "table"
    elif "left" in spec or "right" in spec:
        kind = "two_column"
    spec["type"] = kind
    spec["title"] = str(_first_value(spec, "title", "heading", "name") or "")
    spec["subtitle"] = str(_first_value(spec, "subtitle", "description") or "")

    if kind == "content":
        blocks = _normalize_blocks(spec.get("blocks"))
        if not blocks:
            blocks = _normalize_blocks(_first_value(spec, "content", "body", "text"))
        bullets = _first_value(spec, "bullets", "points", "items")
        if bullets not in (None, "", []):
            blocks.extend([{"type": "bullets", "items": list(bullets) if isinstance(bullets, list) else [bullets]}])
        if not blocks and spec["subtitle"]:
            blocks = [{"type": "paragraph", "text": spec["subtitle"]}]
        spec["blocks"] = blocks
        if not spec["title"] and not blocks:
            raise PresentationArtifactError("正文幻灯片缺少标题和内容")
    elif kind == "section":
        if not spec["title"] and not spec["subtitle"]:
            raise PresentationArtifactError("分节幻灯片缺少标题")
    elif kind == "two_column":
        for side in ("left", "right"):
            column = dict(spec.get(side) or {})
            column["heading"] = str(_first_value(column, "heading", "title", "name") or "")
            column_items = _first_value(column, "items", "bullets", "points")
            if column_items is not None:
                column["items"] = column_items if isinstance(column_items, list) else [column_items]
            else:
                column["text"] = str(_first_value(column, "text", "content", "body") or "")
            spec[side] = column
        if not spec["title"] and not any(
            spec[side].get("heading") or spec[side].get("text") or spec[side].get("items")
            for side in ("left", "right")
        ):
            raise PresentationArtifactError("双栏幻灯片缺少内容")
    elif kind != "table":
        raise PresentationArtifactError(f"不支持的幻灯片类型：{requested_kind}")
    return spec


def _append_slide(presentation: Presentation, spec: dict[str, Any], number: int) -> None:
    spec = _normalize_slide_spec(spec)
    kind = str(spec.get("type") or "content")
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    background = slide.background.fill
    background.solid()
    background.fore_color.rgb = WHITE

    if kind == "section":
        band = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(13.333), Inches(7.5))
        band.fill.solid()
        band.fill.fore_color.rgb = NAVY
        band.line.fill.background()
        _add_textbox(slide, 1.0, 2.55, 11.3, 0.9, str(spec.get("title") or ""), size=34, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
        _add_textbox(slide, 1.3, 3.55, 10.7, 0.55, str(spec.get("subtitle") or ""), size=18, color=LIGHT_BLUE, align=PP_ALIGN.CENTER)
        return
    if kind == "table":
        _add_table_slide(slide, spec, number)
        return

    _add_slide_header(slide, str(spec.get("title") or ""), number)
    if kind == "two_column":
        columns = [dict(spec.get("left") or {}), dict(spec.get("right") or {})]
        for index, column in enumerate(columns):
            left = 0.78 + index * 6.05
            panel = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(left), Inches(1.55), Inches(5.65), Inches(4.95))
            panel.fill.solid()
            panel.fill.fore_color.rgb = LIGHT_GRAY
            panel.line.fill.background()
            _add_textbox(slide, left + 0.3, 1.84, 5.05, 0.45, str(column.get("heading") or ""), size=20, bold=True, color=BLUE)
            body = slide.shapes.add_textbox(Inches(left + 0.3), Inches(2.48), Inches(5.05), Inches(3.62))
            items = column.get("items")
            if items is not None:
                _add_bullets(body.text_frame, list(items), font_size=18)
            else:
                body.text_frame.text = str(column.get("text") or "")
                for paragraph in body.text_frame.paragraphs:
                    for run in paragraph.runs:
                        _set_run_font(run, 18)
        return
    top = 1.55
    for block in list(spec.get("blocks") or []):
        top += _add_content_block(slide, dict(block), 0.8, top, 11.75)
        if top > 6.75:
            raise PresentationArtifactError(f"幻灯片“{spec.get('title') or ''}”内容过多")


def create_presentation(
    output_path: Path,
    title: str,
    subtitle: str,
    slides: list[dict[str, Any]],
) -> None:
    if not title.strip():
        raise PresentationArtifactError("PPT 标题不能为空")
    if len(slides) > 49:
        raise PresentationArtifactError("PPT 最多支持 50 页")
    presentation = Presentation()
    presentation.slide_width = Inches(13.333)
    presentation.slide_height = Inches(7.5)
    cover = presentation.slides.add_slide(presentation.slide_layouts[6])
    background = cover.background.fill
    background.solid()
    background.fore_color.rgb = NAVY
    accent = cover.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.72), Inches(1.25), Inches(0.16), Inches(4.35))
    accent.fill.solid()
    accent.fill.fore_color.rgb = BLUE
    accent.line.fill.background()
    _add_textbox(cover, 1.18, 2.05, 10.8, 1.45, title, size=38, bold=True, color=WHITE, vertical=MSO_ANCHOR.MIDDLE)
    if subtitle:
        _add_textbox(cover, 1.2, 3.65, 10.6, 0.72, subtitle, size=20, color=LIGHT_BLUE)
    for number, spec in enumerate(slides, start=2):
        _append_slide(presentation, dict(spec), number)
    presentation.core_properties.title = title
    presentation.core_properties.author = "Nano Agent"
    presentation.save(output_path)


def _delete_slide(presentation: Presentation, one_based_number: int) -> None:
    if one_based_number < 1 or one_based_number > len(presentation.slides):
        raise PresentationArtifactError(f"幻灯片页码不存在：{one_based_number}")
    slide_id = presentation.slides._sldIdLst[one_based_number - 1]
    relationship_id = slide_id.rId
    presentation.part.drop_rel(relationship_id)
    presentation.slides._sldIdLst.remove(slide_id)


def _replace_in_text_frame(frame, old: str, new: str) -> int:
    count = 0
    for paragraph in frame.paragraphs:
        if old not in paragraph.text:
            continue
        if any(old in run.text for run in paragraph.runs):
            for run in paragraph.runs:
                occurrences = run.text.count(old)
                run.text = run.text.replace(old, new)
                count += occurrences
        else:
            occurrences = paragraph.text.count(old)
            paragraph.text = paragraph.text.replace(old, new)
            count += occurrences
    return count


def edit_presentation(
    source_path: Path,
    output_path: Path,
    operations: list[dict[str, Any]],
) -> dict[str, int]:
    presentation = Presentation(source_path)
    counts = {"replacements": 0, "deleted_slides": 0, "appended_slides": 0}
    for operation in operations:
        kind = str(operation.get("type") or "")
        if kind == "replace_text":
            old = str(operation.get("old") or "")
            if not old:
                raise PresentationArtifactError("replace_text.old 不能为空")
            new = str(operation.get("new") or "")
            for slide in presentation.slides:
                for shape in slide.shapes:
                    if getattr(shape, "has_text_frame", False):
                        counts["replacements"] += _replace_in_text_frame(
                            shape.text_frame, old, new
                        )
                    if getattr(shape, "has_table", False):
                        for row in shape.table.rows:
                            for cell in row.cells:
                                counts["replacements"] += _replace_in_text_frame(
                                    cell.text_frame, old, new
                                )
        elif kind == "delete_slide":
            _delete_slide(presentation, int(operation.get("slide_number") or 0))
            counts["deleted_slides"] += 1
        elif kind == "append_slides":
            new_slides = list(operation.get("slides") or [])
            for spec in new_slides:
                _append_slide(presentation, dict(spec), len(presentation.slides) + 1)
            counts["appended_slides"] += len(new_slides)
        else:
            raise PresentationArtifactError(f"不支持的编辑操作：{kind}")
    presentation.save(output_path)
    return counts
