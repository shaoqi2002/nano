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
    create_document_from_path,
    require_document,
)
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
    async with SessionLocal() as session:
        word = await create_document_from_path(session, docx_path, filename)
    outputs = [{"document_id": str(word.id), "filename": word.original_name, "kind": "word"}]
    if pdf_path is not None:
        async with SessionLocal() as session:
            pdf = await create_document_from_path(session, pdf_path, pdf_path.name)
        outputs.append({
            "document_id": str(pdf.id),
            "filename": pdf.original_name,
            "kind": "pdf",
            "page_count": page_count,
        })
    return {"outputs": outputs, "index_status": "pending"}


@tool
async def word_create_document(
    filename: str,
    title: str,
    blocks: list[dict[str, Any]],
    subtitle: str = "",
    create_pdf: bool = True,
) -> dict:
    """生成专业 Word 并入库。blocks 支持 heading(level,text)、paragraph(text)、quote(text)、bullets(items)、numbered(items)、table(headers,rows,column_widths) 和 page_break；可同时生成 PDF。"""
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
    create_pdf: bool = True,
) -> dict:
    """编辑库中 Word 并另存新版本。operations 支持 replace_text(old,new)、delete_paragraph(contains)、append_blocks(blocks)；可同时生成 PDF且不覆盖原件。"""
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
    """将文档库中的 DOCX 转换为 PDF，并把生成的 PDF 保存回文档库。"""
    async with SessionLocal() as session:
        document = await require_document(session, UUID(document_id))
        if document.preview_kind != "word":
            raise ValueError("只能转换 DOCX 文档")
        source = await run_in_threadpool(cached_document_path, document)
    name = safe_artifact_filename(output_filename, ".pdf")
    with tempfile.TemporaryDirectory(prefix="nano-pdf-") as directory:
        output = Path(directory) / name
        pages = await run_in_threadpool(convert_word_to_pdf, source, output)
        async with SessionLocal() as session:
            pdf = await create_document_from_path(session, output, name)
    return {
        "outputs": [{
            "document_id": str(pdf.id), "filename": pdf.original_name,
            "kind": "pdf", "page_count": pages,
        }],
        "source_document_id": document_id,
        "index_status": "pending",
    }


def create_local_write_tools():
    return [
        local_write_text,
        local_move_file,
        word_create_document,
        word_edit_document,
        word_convert_to_pdf,
    ]
