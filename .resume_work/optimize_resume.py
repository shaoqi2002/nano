from __future__ import annotations

import copy
import os
import zipfile
from pathlib import Path

from lxml import etree


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"


def qn(local: str) -> str:
    return f"{{{W_NS}}}{local}"


def node_text(node: etree._Element) -> str:
    return "".join(t.text or "" for t in node.findall(".//w:t", NS))


def clear_run(run: etree._Element) -> None:
    rpr = run.find("w:rPr", NS)
    for child in list(run):
        if child is not rpr:
            run.remove(child)


def add_text(run: etree._Element, text: str) -> None:
    t = etree.SubElement(run, qn("t"))
    t.set(XML_SPACE, "preserve")
    t.text = text


def add_line_break(run: etree._Element, indent: bool = False) -> None:
    etree.SubElement(run, qn("br"))
    if indent:
        etree.SubElement(run, qn("tab"))


def make_run(template: etree._Element, pieces: list[tuple[str, str | None]]) -> etree._Element:
    run = copy.deepcopy(template)
    clear_run(run)
    for kind, value in pieces:
        if kind == "text":
            add_text(run, value or "")
        elif kind == "tab":
            etree.SubElement(run, qn("tab"))
        elif kind == "break":
            add_line_break(run, indent=False)
        elif kind == "indented_break":
            add_line_break(run, indent=True)
        else:
            raise ValueError(kind)
    return run


def body_run_template(paragraph: etree._Element) -> etree._Element:
    runs = paragraph.findall("w:r", NS)
    for run in runs:
        if "\uf0b7" in node_text(run):
            return run
    for run in runs:
        if run.find("w:rPr/w:sz", NS) is not None and node_text(run).strip():
            return run
    raise RuntimeError("No body run template found")


def replace_bullet(paragraph: etree._Element, lines: list[str]) -> None:
    template = body_run_template(paragraph)
    ppr = paragraph.find("w:pPr", NS)
    for child in list(paragraph):
        if child is not ppr:
            paragraph.remove(child)
    pieces: list[tuple[str, str | None]] = [("text", "\uf0b7  " + lines[0])]
    for line in lines[1:]:
        pieces.extend([("indented_break", None), ("text", line)])
    paragraph.append(make_run(template, pieces))


def replace_combined_entry_bullet(paragraph: etree._Element, lines: list[str]) -> None:
    template = body_run_template(paragraph)
    children = list(paragraph)
    break_index = None
    for index, child in enumerate(children):
        if child.tag == qn("r") and child.find("w:br", NS) is not None:
            break_index = index
            break
    if break_index is None:
        raise RuntimeError("Combined entry paragraph has no header/body break")
    for child in children[break_index + 1 :]:
        paragraph.remove(child)
    pieces: list[tuple[str, str | None]] = [("text", "\uf0b7  " + lines[0])]
    for line in lines[1:]:
        pieces.extend([("indented_break", None), ("text", line)])
    paragraph.append(make_run(template, pieces))


def replace_plain_paragraph(
    paragraph: etree._Element,
    lines: list[str],
    leading_tab: bool = False,
) -> None:
    template = paragraph.find("w:r", NS)
    if template is None:
        raise RuntimeError("Paragraph has no run template")
    ppr = paragraph.find("w:pPr", NS)
    for child in list(paragraph):
        if child is not ppr:
            paragraph.remove(child)
    pieces: list[tuple[str, str | None]] = []
    if leading_tab:
        pieces.append(("tab", None))
    pieces.append(("text", lines[0]))
    for line in lines[1:]:
        pieces.extend([("indented_break" if leading_tab else "break", None), ("text", line)])
    paragraph.append(make_run(template, pieces))


def replace_skills(paragraph: etree._Element) -> None:
    runs = paragraph.findall("w:r", NS)
    label_template = next(r for r in runs if node_text(r) == "技术技能：")
    body_template = next(r for r in runs if node_text(r).startswith("Java"))
    ppr = paragraph.find("w:pPr", NS)
    for child in list(paragraph):
        if child is not ppr:
            paragraph.remove(child)

    blocks = [
        (
            "技术技能：",
            "Java | Python | TypeScript | Spring Boot | FastAPI | Vue 3 | React | LangGraph | RESTful API | PostgreSQL / pgvector | MongoDB | Kafka | Docker | GitHub Actions | Linux",
        ),
        ("语言能力：", "普通话（母语）、英语（雅思 7.5，GRE 324）"),
        ("兴趣爱好：", "编程、阅读、跑步、小号、萨克斯、ACGN"),
    ]
    for index, (label, value) in enumerate(blocks):
        if index:
            paragraph.append(make_run(body_template, [("break", None)]))
        paragraph.append(make_run(label_template, [("text", label)]))
        paragraph.append(make_run(body_template, [("text", value)]))


def main() -> None:
    source = Path(os.environ["RESUME_SOURCE"])
    output = Path(os.environ["RESUME_OUTPUT"])

    with zipfile.ZipFile(source, "r") as src_zip:
        root = etree.fromstring(src_zip.read("word/document.xml"))
        body = root.find("w:body", NS)
        if body is None:
            raise RuntimeError("word/document.xml has no body")
        paragraphs = body.findall("w:p", NS)
        if len(paragraphs) != 29:
            raise RuntimeError(f"Unexpected paragraph count: {len(paragraphs)}")

        replace_plain_paragraph(
            paragraphs[5],
            [
                "核心课程：软件设计与分析、软件设计模式、可扩展系统架构、云原生解决方案设计、DevSecOps 工程与自动化、",
                "平台工程、安全软件开发生命周期、可解释与负责任的人工智能系统",
            ],
            leading_tab=True,
        )
        replace_plain_paragraph(
            paragraphs[7],
            [
                "核心课程：数据结构与算法、面向对象程序设计、数据库、操作系统、计算机网络、软件工程、计算机体系结构",
                "竞赛获奖：校级编程竞赛一等奖（2025）、二等奖（2024）、三等奖（2023）",
            ],
            leading_tab=True,
        )

        internship = [
            [
                "独立负责安防监控平台核心模块的全栈开发，基于 React + Spring Boot 交付设备管理、Workflow 配置与",
                "视觉分析（VA）任务管理，持续改善交互一致性与代码可维护性。",
            ],
            [
                "主导 VisionX Adaptor 设计与开发，整合 WebSocket、REST API 与 Kafka，打通第三方视觉分析平台和",
                "内部微服务的数据链路，实现分析结果自动接入与处理。",
            ],
            [
                "设计 RESTful API 并集成外部系统与 RTSP 流媒体服务，支持设备控制、实时视频、录像回放及业务流程管理。",
            ],
            [
                "构建 VA Job 生命周期状态机（FSM）与 Health Check 异常检测机制，自动识别异常任务并更新状态，",
                "提高系统运行可靠性与维护效率。",
            ],
            [
                "完成多微服务开发环境部署、联调与故障排查，解决 Kafka、MongoDB、PostgreSQL、Docker Compose",
                "相关问题，保障环境稳定并提升团队问题定位效率。",
            ],
        ]
        for index, lines in enumerate(internship, start=10):
            replace_bullet(paragraphs[index], lines)

        replace_combined_entry_bullet(
            paragraphs[19],
            [
                "承担用户管理模块全栈开发，使用 Spring Boot 3、MyBatis-Plus、Vue 3 与 TypeScript 实现用户、角色、",
                "权限管理及 RBAC 访问控制。",
            ],
        )
        replace_bullet(
            paragraphs[20],
            [
                "设计 RESTful API，结合 AOP、自定义注解与全局异常处理统一权限校验和错误响应，提升模块复用性",
                "与扩展性。",
            ],
        )
        replace_bullet(
            paragraphs[21],
            [
                "搭建 GitHub Actions CI/CD 流水线，集成自动化测试、Snyk 安全扫描与 Railway 部署，实现持续集成",
                "和自动交付。",
            ],
        )
        replace_bullet(
            paragraphs[22],
            ["优化前后端接口与数据处理流程，减少重复请求和冗余传输，改善系统响应与用户体验。"],
        )

        replace_combined_entry_bullet(
            paragraphs[23],
            [
                "设计 3D 场景描述生成算法，将点云与 Mesh 数据转换为结构化描述，增强下游 AI 系统的场景理解",
                "与结果可解释性。",
            ],
        )
        replace_bullet(
            paragraphs[24],
            [
                "开发多视角数据处理与空间关系建模算法，完成场景变换预测，为环境重建、空间推理和智能体感知提供支持。"
            ],
        )
        replace_bullet(
            paragraphs[25],
            [
                "设计相机外参到运动轨迹的转换方法，形成面向智能体仿真、路径规划和三维可视化的轨迹生成流程。"
            ],
        )
        replace_bullet(
            paragraphs[26],
            ["沉淀实验文档与技术报告，确保算法流程可复现，并支持团队后续模型迭代。"],
        )
        replace_skills(paragraphs[28])

        document_xml = etree.tostring(
            root,
            xml_declaration=True,
            encoding="UTF-8",
            standalone=True,
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output, "w") as out_zip:
            for info in src_zip.infolist():
                data = document_xml if info.filename == "word/document.xml" else src_zip.read(info.filename)
                out_zip.writestr(info, data)
    print(output)


if __name__ == "__main__":
    main()
