"""Small, bounded file-storage helpers for the single-node MVP."""

import os
import zipfile
from pathlib import Path

from fastapi import HTTPException, UploadFile, status


def max_upload_size() -> int:
    try:
        return max(1024, int(os.getenv("MAX_UPLOAD_SIZE_BYTES", str(20 * 1024 * 1024))))
    except ValueError:
        return 20 * 1024 * 1024


async def save_upload_limited(upload: UploadFile, destination: Path, *, size_limit: int | None = None) -> int:
    """Stream an upload to disk and remove partial data when it exceeds the limit."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    limit = min(max_upload_size(), size_limit) if size_limit is not None else max_upload_size()
    total = 0
    try:
        with destination.open("xb") as output:
            while chunk := await upload.read(1024 * 1024):
                total += len(chunk)
                if total > limit:
                    raise HTTPException(
                        status.HTTP_413_CONTENT_TOO_LARGE,
                        detail=f"文件大小不能超过 {limit} 字节",
                    )
                output.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return total


def validate_material(path: Path, kind: str) -> None:
    """Six native formats, bounded Office containers, no extension-only acceptance."""
    from .doc_extractor import decode_text
    from .material_contract import CONTRACT
    try:
        if kind == 'pdf':
            from PyPDF2 import PdfReader
            if path.read_bytes()[:5] != b'%PDF-': raise ValueError('PDF 文件头不正确')
            reader = PdfReader(str(path))
            if not reader.is_encrypted: len(reader.pages)
        elif kind in ('docx', 'pptx'):
            from defusedxml.ElementTree import fromstring
            target = {'docx':'word/document.xml','pptx':'ppt/presentation.xml'}[kind]
            with zipfile.ZipFile(path) as archive:
                entries = archive.infolist()
                if len(entries)>10000 or sum(e.file_size for e in entries)>200*1024*1024:
                    raise ValueError('Office 解压后的内容过大')
                if any(e.flag_bits & 1 or '..' in Path(e.filename).parts or e.filename.startswith('/') for e in entries):
                    raise ValueError('Office 文件结构不安全')
                if target not in archive.namelist() or '[Content_Types].xml' not in archive.namelist():
                    raise ValueError('Office 文件结构不正确')
                if any('vbaproject' in e.filename.lower() for e in entries): raise ValueError('不支持带宏的文档')
                for e in entries:
                    if e.filename.endswith(('.xml','.rels')):
                        fromstring(archive.read(e))
                # Invoke the native parser once to reject malformed but correctly named ZIPs.
                if kind=='docx':
                    from docx import Document
                    Document(str(path))
                else:
                    from pptx import Presentation
                    Presentation(str(path))
        elif kind in ('txt','markdown','html'):
            raw=path.read_bytes()
            if raw.startswith((b'PK\x03\x04',b'%PDF-',b'\x89PNG',b'\xff\xd8',b'MZ')): raise ValueError('文件内容与扩展名不匹配')
            text=decode_text(raw)
            if kind=='html':
                import re
                if not re.search(r'<(?:!doctype\s+html|html|body|head|p|div|h[1-6]|ul|ol|table|article|section)\b',text,re.I):
                    raise ValueError('HTML 文件没有静态正文结构')
        else:
            raise HTTPException(400, CONTRACT['unsupported_message'])
    except HTTPException: raise
    except Exception as error:
        raise HTTPException(400, '文件内容与格式不匹配或结构损坏，请检查文件。') from error
