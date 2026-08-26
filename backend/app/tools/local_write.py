import shutil
import tempfile
from pathlib import Path
from typing import Any
from uuid import UUID

from langchain_core.tools import tool
from starlette.concurrency import run_in_threadpool

from app.core.database import SessionLocal
from app.service.document import (
    cached_document_path,
    require_document,
)
from app.service.chat_artifact import get_chat_artifact, store_chat_artifact
from app.service.presentation_artifact import create_presentation, edit_presentation
from app.service.word_artifact import (
    convert_word_to_pdf,
    create_word_document,
    edit_word_document,
    safe_artifact_filename,
)
from app.tools.local_read import LocalPathError, resolve_workspace_path


@tool
def local_write_text(relative_path: str, content: str, overwrite: bool = False) -> dict:
    """在受限 Agent 工作区内创建 UTF-8 文本文件；默认拒绝覆盖已有文件。"""
    path = resolve_workspace_path(relative_path)
    if path.exists() and not overwrite:
        raise LocalPathError("目标文件已存在；如需覆盖请明确设置 overwrite")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return {"path": relative_path, "size_bytes": path.stat().st_size}


@tool
def local_move_file(source: str, destination: str) -> dict:
    """在受限 Agent 工作区内部移动文件；拒绝覆盖目标文件。"""
    source_path = resolve_workspace_path(source)
    destination_path = resolve_workspace_path(destination)
    if not source_path.is_file():
        raise LocalPathError("源文件不存在")
    if destination_path.exists():
        raise LocalPathError("目标文件已存在")
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source_path), str(destination_path))
    return {"source": source, "destination": destination}


async def _store_outputs(
    docx_path: Path,
    filename: str,
    create_pdf: bool,
) -> dict[str, Any]:
    pdf_path: Path | None = None
    page_count: int | None = None
    if create_pdf:
        pdf_path = docx_path.with_suffix(".pdf")
        page_count = await run_in_threadpool(convert_word_to_pdf, docx_path, pdf_path)
    word = await run_in_threadpool(store_chat_artifact, docx_path, filename)
    word["kind"] = "word"
    outputs = [word]
    if pdf_path is not None:
        pdf = await run_in_threadpool(store_chat_artifact, pdf_path, pdf_path.name)
        pdf.update({"kind": "pdf", "page_count": page_count})
        outputs.append(pdf)
    return {"outputs": outputs}


@tool
async def word_create_document(
    filename: str,
    title: str,
    blocks: list[dict[str, Any]],
    subtitle: str = "",
    create_pdf: bool = False,
) -> dict:
    """生成可直接下载的 Word。默认只生成 DOCX；仅当用户明确要求 PDF 时设置 create_pdf=true。blocks 支持 heading(level,text)、paragraph(text)、quote(text)、bullets(items)、numbered(items)、table(headers,rows,column_widths) 和 page_break。"""
    name = safe_artifact_filename(filename, ".docx")
    with tempfile.TemporaryDirectory(prefix="nano-word-") as directory:
        path = Path(directory) / name
        await run_in_threadpool(create_word_document, path, title, subtitle, blocks)
        return await _store_outputs(path, name, create_pdf)


@tool
async def word_edit_document(
    document_id: str,
    output_filename: str,
    operations: list[dict[str, Any]],
    create_pdf: bool = False,
) -> dict:
    """编辑文档库中的 Word 并返回可直接下载的新版本。默认只生成 DOCX；仅当用户明确要求 PDF 时设置 create_pdf=true。operations 支持 replace_text(old,new)、delete_paragraph(contains)、append_blocks(blocks)，且不覆盖原件。"""
    async with SessionLocal() as session:
        document = await require_document(session, UUID(document_id))
        if document.preview_kind != "word":
            raise ValueError("只能编辑 DOCX 文档")
        source = await run_in_threadpool(cached_document_path, document)
    name = safe_artifact_filename(output_filename, ".docx")
    with tempfile.TemporaryDirectory(prefix="nano-word-edit-") as directory:
        output = Path(directory) / name
        counts = await run_in_threadpool(edit_word_document, source, output, operations)
        result = await _store_outputs(output, name, create_pdf)
        result["edit_summary"] = counts
        result["source_document_id"] = document_id
        return result


@tool
async def word_convert_to_pdf(document_id: str, output_filename: str) -> dict:
    """将文档库中的 DOCX 转换为可直接下载的 PDF，不保存回文档库。"""
    async with SessionLocal() as session:
        document = await require_document(session, UUID(document_id))
        if document.preview_kind != "word":
            raise ValueError("只能转换 DOCX 文档")
        source = await run_in_threadpool(cached_document_path, document)
    name = safe_artifact_filename(output_filename, ".pdf")
    with tempfile.TemporaryDirectory(prefix="nano-pdf-") as directory:
        output = Path(directory) / name
        pages = await run_in_threadpool(convert_word_to_pdf, source, output)
        pdf = await run_in_threadpool(store_chat_artifact, output, name)
        pdf.update({"kind": "pdf", "page_count": pages})
    return {
        "outputs": [pdf],
        "source_document_id": document_id,
    }


@tool
async def presentation_create(
    filename: str,
    title: str,
    slides: list[dict[str, Any]],
    subtitle: str = "",
) -> dict:
    """生成可直接下载的 16:9 PPTX。slides 支持 content(blocks)、section、two_column(left/right) 和 table(headers/rows)；content blocks 支持 heading、paragraph、bullets、numbered、quote。"""
    name = safe_artifact_filename(filename, ".pptx")
    with tempfile.TemporaryDirectory(prefix="nano-ppt-") as directory:
        path = Path(directory) / name
        await run_in_threadpool(create_presentation, path, title, subtitle, slides)
        output = await run_in_threadpool(store_chat_artifact, path, name)
        output["kind"] = "presentation"
        return {"outputs": [output]}


@tool
async def presentation_edit_attachment(
    artifact_id: str,
    output_filename: str,
    operations: list[dict[str, Any]],
) -> dict:
    """编辑聊天中上传的 PPTX 并返回新版本。artifact_id 来自附件上下文；operations 支持 replace_text(old,new)、delete_slide(slide_number) 和 append_slides(slides)，不会覆盖原文件。"""
    source, _ = await run_in_threadpool(get_chat_artifact, UUID(artifact_id))
    if source.suffix.lower() != ".pptx":
        raise ValueError("只能编辑聊天中上传的 PPTX 文件。")
    name = safe_artifact_filename(output_filename, ".pptx")
    with tempfile.TemporaryDirectory(prefix="nano-ppt-edit-") as directory:
        output_path = Path(directory) / name
        summary = await run_in_threadpool(edit_presentation, source, output_path, operations)
        output = await run_in_threadpool(store_chat_artifact, output_path, name)
        output["kind"] = "presentation"
        return {
            "outputs": [output],
            "edit_summary": summary,
            "source_artifact_id": artifact_id,
        }


def create_local_write_tools():
    return [
        local_write_text,
        local_move_file,
        word_create_document,
        word_edit_document,
        word_convert_to_pdf,
        presentation_create,
        presentation_edit_attachment,
    ]
