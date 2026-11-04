"""Requirement attachments: one document per task, extracted once and capped.

The composer field stays at 2000 characters; a long document is uploaded instead and its
text is stored beside the task, then merged into the requirement only when the model runs.
"""
from pathlib import Path
import tempfile

from .doc_extractor import extract_text

MAX_BYTES = 10 * 1024 * 1024
MAX_TEXT = 8000
# file suffix -> the type name doc_extractor understands
ALLOWED = {'.pdf': 'pdf', '.docx': 'docx', '.txt': 'txt', '.md': 'markdown', '.markdown': 'markdown'}


class AttachmentError(ValueError):
    """A user-facing rejection; the message is safe to show verbatim."""


def normalize(filename: str, data: bytes) -> dict:
    """Validate, extract and cap one upload. Returns the payload stored on the task."""
    suffix = Path(filename or '').suffix.lower()
    if suffix not in ALLOWED:
        raise AttachmentError('附件仅支持 PDF、DOCX、TXT、Markdown')
    if not data:
        raise AttachmentError('附件内容为空')
    if len(data) > MAX_BYTES:
        raise AttachmentError('附件不能超过 10MB')
    with tempfile.TemporaryDirectory() as workspace:
        path = Path(workspace)/('upload' + suffix)
        path.write_bytes(data)
        try:
            text = extract_text(str(path), ALLOWED[suffix])
        except Exception as error:
            raise AttachmentError('无法从附件中提取文字，请检查文件是否损坏') from error
    text = (text or '').strip()
    if not text:
        raise AttachmentError('附件中没有可提取的文字')
    capped = text[:MAX_TEXT]
    return {'name': (filename or '附件')[:255], 'text': capped,
            'charCount': len(capped), 'truncated': len(text) > MAX_TEXT}


def merged(requirement: str, attachment_text: str | None) -> str:
    """What the model sees: the typed requirement plus the attachment body."""
    if not attachment_text:
        return requirement
    return requirement.rstrip() + '\n\n【附件正文】\n' + attachment_text.strip()
