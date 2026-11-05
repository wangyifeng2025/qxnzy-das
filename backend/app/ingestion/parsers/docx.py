from io import BytesIO

from docx import Document

from app.ingestion.parsers.base import ParsedBlock, ParsedDocument, ParsedSheet


def parse_docx(content: bytes) -> ParsedDocument:
    document = Document(BytesIO(content))
    parsed = ParsedDocument(page_count=1)
    for index, paragraph in enumerate(document.paragraphs, start=1):
        text = paragraph.text.strip()
        if text:
            parsed.blocks.append(ParsedBlock({"paragraph": index, "snippet": text[:80]}, text))
    for index, table in enumerate(document.tables, start=1):
        rows: list[list[object]] = [[cell.text.strip() for cell in row.cells] for row in table.rows]
        if len(rows) < 2:
            continue
        parsed.cell_count += sum(len(row) for row in rows)
        parsed.sheets.append(
            ParsedSheet(
                name=f"表格{index}",
                rows=rows,
                row_numbers=list(range(1, len(rows) + 1)),
            )
        )
    return parsed
