# Resume edit contract

- Reference: `C:\Users\Lenovo\Desktop\简历\邵棋_NUS_SE.docx`
- SHA-256: `cbeae3a0125f28822e1728059cba6e267ad5e09475ad9ff00d9436d1fd51fea9`
- Evidence: `.resume_work/source_render.pdf`, `.resume_work/source_pages/page-1.png`, `.resume_work/source_style.json`, section/style/heading/image/field/footnote/content-control audits run on 2026-08-19.
- Scope: one-page Chinese software-engineering resume; one section; no tables, headings, fields, footnotes, endnotes, or content controls; one floating portrait image.

## Page system

- A4 portrait, 8.27 x 11.69 inches.
- Margins: 0.50 inch on all sides.
- One section, NEW_PAGE start, no distinct first page or odd/even headers.
- Source and final should remain one page.

## Visual and typography system

- Source is a dense single-page resume using direct formatting in Normal paragraphs.
- Primary font: SimSun/宋体; Latin fallback: Times New Roman.
- Name: centered, 14 pt, bold.
- Section bands: bold 10.5 pt-equivalent text with a bottom rule; single line spacing.
- Entry headers: bold, single line, three visual columns (role, organization/project, date) formed by source spacing.
- Detail lines: 10 pt, single line spacing, source bullet glyph `U+F0B7`, hanging-wrap effect supported by an embedded tab where needed.
- Preserve the floating 0.85 x 1.19 inch portrait and all existing contact, education, internship, remaining project, and skills formatting.

## Content flow and editable slots

1. Identity/contact block: preserve.
2. Education: preserve.
3. Internship: preserve.
4. Project section heading (`word/document.xml`, body paragraph 16 in one-based visual order): preserve.
5. Existing NUS-ISS project block: preserve.
6. Existing FNII research block: preserve.
7. Bottom crawler block (`word/document.xml`, python-docx paragraphs 24-27): remove completely.
8. New Nano project: insert immediately after the Project Experience heading and before the NUS-ISS project, using the same four-paragraph pattern as the removed block (combined header + first bullet, followed by three bullet paragraphs).
9. Skills section: preserve unless pagination requires a minimal local spacing correction; do not change factual content.

## New project content contract

- Role: 独立开发者.
- Project: Nano Multi-Agent Research Assistant.
- Date: 2026.08 - 至今, supported by repository history beginning 2026-08-14 and current work on 2026-08-19.
- Four bullets: LangGraph multi-agent orchestration; FastAPI/Vue/SSE/checkpoint/trace; RAG and governed Tool Registry; versioned evaluation plus CI/container deployment.
- Do not claim user counts, latency gains, accuracy percentages, awards, or production scale not present in repository evidence.

## Package preservation

- Only `word/document.xml` may change.
- Preserve byte-for-byte: content types, all relationships, footnotes/endnotes, image, theme, settings, numbering, styles, web settings, font table, and document properties.
- Baseline package hashes were recorded in the tool log; notably image SHA-256 `a580c65233fd35ad5b24c61eda55a648826f28d63e3a33aeceb633dde1da7ee7`, styles SHA-256 `19998815879fde0e7c7db5850b2d9b5e876738a409defc923637bc68d8113779`, numbering SHA-256 `b9bb49d95409d1b15fc411e813ec86140ae97e30d0d87ca4960383de118217c4`.

## Fidelity gates

- Original reference hash remains unchanged.
- Final has one A4 page with the portrait in the original position.
- No clipping, overlap, unexpected wrap, orphan section heading, or loss of the bottom Skills section.
- Nano block matches the source entry hierarchy and body type.
- Paragraph order is Project heading -> Nano -> NUS-ISS -> FNII -> Skills.
- All package parts except `word/document.xml` remain byte-identical.
