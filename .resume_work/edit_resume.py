from __future__ import annotations

import copy
import os
import zipfile
from pathlib import Path

from lxml import etree


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}


def qn(local: str) -> str:
    return f"{{{W_NS}}}{local}"


def paragraph_text(paragraph: etree._Element) -> str:
    chunks: list[str] = []
    for node in paragraph.iter():
        if node.tag == qn("t") and node.text:
            chunks.append(node.text)
        elif node.tag == qn("tab"):
            chunks.append("\t")
        elif node.tag in {qn("br"), qn("cr")}:
            chunks.append("\n")
    return "".join(chunks)


def set_run_text(run: etree._Element, text: str) -> None:
    rpr = run.find("w:rPr", NS)
    for child in list(run):
        if child is not rpr:
            run.remove(child)
    text_node = etree.SubElement(run, qn("t"))
    text_node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    text_node.text = text


def replace_paragraph_content(
    paragraph: etree._Element,
    header_text: str | None,
    bullet_text: str,
    header_run_template: etree._Element,
    body_run_template: etree._Element,
) -> None:
    ppr = paragraph.find("w:pPr", NS)
    for child in list(paragraph):
        if child is not ppr:
            paragraph.remove(child)

    if header_text is not None:
        header_run = copy.deepcopy(header_run_template)
        set_run_text(header_run, header_text)
        paragraph.append(header_run)

        break_run = copy.deepcopy(body_run_template)
        rpr = break_run.find("w:rPr", NS)
        for child in list(break_run):
            if child is not rpr:
                break_run.remove(child)
        etree.SubElement(break_run, qn("br"))
        paragraph.append(break_run)

    body_run = copy.deepcopy(body_run_template)
    set_run_text(body_run, bullet_text)
    paragraph.append(body_run)


def main() -> None:
    source = Path(os.environ["RESUME_SOURCE"])
    output = Path(os.environ["RESUME_OUTPUT"])

    with zipfile.ZipFile(source, "r") as src_zip:
        document_xml = src_zip.read("word/document.xml")
        root = etree.fromstring(document_xml)
        body = root.find("w:body", NS)
        if body is None:
            raise RuntimeError("word/document.xml has no body")

        paragraphs = body.findall("w:p", NS)
        project_heading = next(
            p for p in paragraphs if paragraph_text(p).strip() == "项目经历"
        )
        crawler_start_index = next(
            i
            for i, p in enumerate(paragraphs)
            if "2023.03" in paragraph_text(p) and "香港中文大学（深圳）" in paragraph_text(p)
        )
        crawler_block = paragraphs[crawler_start_index : crawler_start_index + 4]
        if len(crawler_block) != 4:
            raise RuntimeError("Crawler experience block is incomplete")

        first_runs = crawler_block[0].findall("w:r", NS)
        header_run_template = next(
            r
            for r in first_runs
            if r.find("w:rPr/w:b", NS) is not None and paragraph_text(r).strip()
        )
        body_run_template = next(
            r
            for r in first_runs
            if r.find("w:rPr/w:sz", NS) is not None and "\uf0b7" in paragraph_text(r)
        )

        new_block = [copy.deepcopy(p) for p in crawler_block[:3]]
        replace_paragraph_content(
            new_block[0],
            "独立开发者               Nano Multi-Agent Research Assistant               2026.08 – 至今",
            "\uf0b7  基于 LangGraph 独立开发多智能体研究助手，实现 Supervisor–Worker 并行编排、失败重试与审核修订。",
            header_run_template,
            body_run_template,
        )
        replace_paragraph_content(
            new_block[1],
            None,
            "\uf0b7  搭建 FastAPI + Vue 3 全栈应用，结合 SSE、PostgreSQL checkpoint 和 Trace 支持任务可视化、取消与恢复。",
            header_run_template,
            body_run_template,
        )
        replace_paragraph_content(
            new_block[2],
            None,
            "\uf0b7  实现 RAG、受控 Tool Registry 与 LLM Judge 评测，并以 GitHub Actions + Docker 自动交付 ARM64 镜像。",
            header_run_template,
            body_run_template,
        )
        for paragraph in crawler_block:
            body.remove(paragraph)

        insertion_index = body.index(project_heading) + 1
        for offset, paragraph in enumerate(new_block):
            body.insert(insertion_index + offset, paragraph)

        new_document_xml = etree.tostring(
            root,
            xml_declaration=True,
            encoding="UTF-8",
            standalone=True,
        )

        output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output, "w") as out_zip:
            for info in src_zip.infolist():
                data = (
                    new_document_xml
                    if info.filename == "word/document.xml"
                    else src_zip.read(info.filename)
                )
                out_zip.writestr(info, data)

    print(output)


if __name__ == "__main__":
    main()
