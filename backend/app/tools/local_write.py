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
from app.service.chat_artifact import store_chat_artifact
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


def create_local_write_tools():
    return [
        local_write_text,
        local_move_file,
        word_create_document,
        word_edit_document,
        word_convert_to_pdf,
    ]
