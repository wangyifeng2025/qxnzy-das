from io import BytesIO

import pdfplumber

from app.ingestion.parsers.base import ParsedBlock, ParsedDocument, ParsedSheet


def parse_pdf(content: bytes) -> ParsedDocument:
    document = ParsedDocument()
    with pdfplumber.open(BytesIO(content)) as pdf:
        document.page_count = len(pdf.pages)
        for number, page in enumerate(pdf.pages, start=1):
            tables = page.extract_tables() or []
            text = page.extract_text() or ""
            if text.strip() and not tables:
                document.blocks.append(ParsedBlock({"page": number, "snippet": text[:80]}, text))
            for index, table in enumerate(tables, start=1):
                rows: list[list[object]] = [
                    [None if cell is None else str(cell).strip() for cell in row] for row in table
                ]
                if len(rows) < 2 or not any(rows[0]):
                    continue
                document.cell_count += sum(len(row) for row in rows)
                document.sheets.append(
                    ParsedSheet(
                        name=f"第{number}页表{index}",
                        rows=rows,
                        row_numbers=list(range(1, len(rows) + 1)),
                    )
                )
    return document
