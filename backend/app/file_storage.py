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


async def save_upload_limited(upload: UploadFile, destination: Path) -> int:
    """Stream an upload to disk and remove partial data when it exceeds the limit."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    limit = max_upload_size()
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


def validate_office_document(path: Path, file_type: str) -> None:
    """Reject obvious extension/content mismatches before invoking document parsers."""
    valid = False
    if file_type == "pdf":
        with path.open("rb") as source:
            valid = source.read(5) == b"%PDF-"
    elif file_type in {"docx", "pptx", "xlsx"} and zipfile.is_zipfile(path):
        expected_prefix = {"docx": "word/", "pptx": "ppt/", "xlsx": "xl/"}[file_type]
        try:
            with zipfile.ZipFile(path) as archive:
                valid = any(name.startswith(expected_prefix) for name in archive.namelist())
        except (OSError, zipfile.BadZipFile):
            valid = False
    if not valid:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="文件内容与扩展名不匹配")
