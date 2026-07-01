"""Extract text from PPT/DOC/EXCEL/PDF files."""

from pathlib import Path

MAX_TEXT_LENGTH = 30000


def extract_text(file_path: str, file_type: str) -> str:
    p = Path(file_path)
    if not p.exists():
        return ""
    try:
        if file_type == "pdf":
            return _extract_pdf(p)
        elif file_type == "docx":
            return _extract_docx(p)
        elif file_type == "pptx":
            return _extract_pptx(p)
        elif file_type == "xlsx":
            return _extract_xlsx(p)
        else:
            return ""
    except Exception:
        return ""


def _extract_pdf(path: Path) -> str:
    from PyPDF2 import PdfReader
    reader = PdfReader(str(path))
    texts = []
    for page in reader.pages:
        t = page.extract_text()
        if t:
            texts.append(t)
    return "\n".join(texts)[:MAX_TEXT_LENGTH]


def _extract_docx(path: Path) -> str:
    from docx import Document
    doc = Document(str(path))
    texts = []
    for para in doc.paragraphs:
        if para.text.strip():
            texts.append(para.text)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                if cell.text.strip():
                    texts.append(cell.text)
    return "\n".join(texts)[:MAX_TEXT_LENGTH]


def _extract_pptx(path: Path) -> str:
    from pptx import Presentation
    prs = Presentation(str(path))
    texts = []
    for slide in prs.slides:
        for shape in slide.shapes:
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    if para.text.strip():
                        texts.append(para.text)
    return "\n".join(texts)[:MAX_TEXT_LENGTH]


def _extract_xlsx(path: Path) -> str:
    from openpyxl import load_workbook
    wb = load_workbook(str(path), read_only=True, data_only=True)
    texts = []
    for ws in wb.worksheets:
        for row in ws.iter_rows(max_row=200, values_only=True):
            for cell in row:
                if cell and str(cell).strip():
                    texts.append(str(cell))
    wb.close()
    return "\n".join(texts)[:MAX_TEXT_LENGTH]


def get_file_type(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    mapping = {".pdf": "pdf", ".docx": "docx", ".doc": "docx", ".pptx": "pptx", ".ppt": "pptx", ".xlsx": "xlsx", ".xls": "xlsx"}
    return mapping.get(ext, "")
