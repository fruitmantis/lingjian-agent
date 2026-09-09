"""Minimal feedback submission and administrator-only review, without model calls."""
import uuid
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException
from PIL import Image, UnidentifiedImageError

from ..auth import require_active_user, require_admin
from ..database import get_db, UPLOADS_DIR
from ..file_storage import save_upload_limited

MAX_IMAGES = 5
MAX_IMAGE_BYTES = 5 * 1024 * 1024
FORMATS = {'PNG': ('.png', 'image/png'), 'JPEG': ('.jpg', 'image/jpeg'),
           'WEBP': ('.webp', 'image/webp'), 'GIF': ('.gif', 'image/gif')}
EXTENSIONS = {'.png': 'PNG', '.jpg': 'JPEG', '.jpeg': 'JPEG', '.webp': 'WEBP', '.gif': 'GIF'}


def private(response: Response):
    response.headers['Cache-Control'] = 'no-store'


router = APIRouter(prefix='/feedback', tags=['feedback'], dependencies=[Depends(private)])
admin_router = APIRouter(prefix='/admin/feedback', tags=['admin-feedback'],
                         dependencies=[Depends(require_admin), Depends(private)])


def validate_image(path: Path, filename: str, content_type: str):
    expected = EXTENSIONS.get(Path(filename).suffix.lower())
    if not expected or content_type not in {v[1] for v in FORMATS.values()}:
        raise HTTPException(422, '截图仅支持 PNG、JPEG、WebP、GIF 图片')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(path) as picture:
                actual = picture.format
                if actual != expected or FORMATS[actual][1] != content_type:
                    raise ValueError('Image format mismatch')
                if picture.width * picture.height > 25_000_000:
                    raise ValueError('Too many pixels')
                picture.verify()
            with Image.open(path) as picture:
                picture.load()
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise HTTPException(422, '截图内容无效或分辨率过大，请使用不超过 2500 万像素的图片') from None


@router.post('', status_code=201)
async def submit(request: Request, user: dict = Depends(require_active_user)):
    saved = []
    committed = False
    try:
        # Bound multipart file count and text size before accepting the body.
        async with request.form(max_files=MAX_IMAGES, max_fields=1, max_part_size=20_000) as form:
            if any(k not in ('description', 'images') for k in form):
                raise HTTPException(422, '反馈参数无效')
            description = form.get('description')
            if not isinstance(description, str) or not 1 <= len(description.strip()) <= 5000:
                raise HTTPException(422, '请填写问题描述，最多 5000 字')
            images = form.getlist('images')
            if len(images) > MAX_IMAGES or any(not isinstance(f, UploadFile) for f in images):
                raise HTTPException(422, '最多上传 5 张截图')
            issue_id = str(uuid.uuid4())
            stamp = datetime.now(timezone.utc).isoformat()
            attachments = []
            for upload in images:
                filename = Path((upload.filename or '').replace('\\', '/')).name[:200]
                suffix = Path(filename).suffix.lower()
                if suffix not in EXTENSIONS:
                    raise HTTPException(422, '截图仅支持 PNG、JPEG、WebP、GIF 图片')
                attachment_id = str(uuid.uuid4())
                storage_name = attachment_id + suffix
                destination = UPLOADS_DIR / 'feedback' / storage_name
                saved.append(destination)
                size = await save_upload_limited(upload, destination, size_limit=MAX_IMAGE_BYTES)
                validate_image(destination, filename, upload.content_type or '')
                attachments.append((attachment_id, issue_id, filename, storage_name, upload.content_type, size, stamp))
            with get_db() as conn:
                conn.execute('INSERT INTO feedback_issue (id, submitter_id, description, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)',
                             (issue_id, user['id'], description.strip(), 'pending', stamp, stamp))
                for attachment in attachments:
                    conn.execute('INSERT INTO feedback_attachment (id, issue_id, filename, storage_name, content_type, size_bytes, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)', attachment)
            committed = True
            return {'message': '问题已提交'}
    except StarletteHTTPException as exc:
        if not isinstance(exc, HTTPException):
            raise HTTPException(exc.status_code, '上传内容无效，最多 5 张截图，问题描述最多 5000 字') from None
        raise
    except Exception:
        raise HTTPException(500, '问题提交失败，请稍后重试') from None
    finally:
        if not committed:
            for path in saved:
                path.unlink(missing_ok=True)


@admin_router.get('')
def list_issues(limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0)):
    with get_db() as conn:
        total = conn.execute('SELECT count(*) FROM feedback_issue').fetchone()[0]
        rows = conn.execute("""SELECT f.id, f.created_at, f.status, substr(f.description, 1, 100) AS summary,
            COALESCE(NULLIF(u.display_name, ''), u.username) AS submitter,
            (SELECT count(*) FROM feedback_attachment a WHERE a.issue_id=f.id) AS screenshot_count
            FROM feedback_issue f JOIN users u ON u.id=f.submitter_id
            ORDER BY f.created_at DESC, f.id DESC LIMIT ? OFFSET ?""", (limit, offset)).fetchall()
    return {'items': [dict(r) for r in rows], 'total': total}


@admin_router.get('/{issue_id}')
def detail(issue_id: str):
    with get_db() as conn:
        row = conn.execute("""SELECT f.id, f.description, f.status, f.created_at,
            COALESCE(NULLIF(u.display_name, ''), u.username) AS submitter
            FROM feedback_issue f JOIN users u ON u.id=f.submitter_id WHERE f.id=?""", (issue_id,)).fetchone()
        if not row:
            raise HTTPException(404, '问题不存在')
        attachments = conn.execute('SELECT id, filename, content_type, size_bytes FROM feedback_attachment WHERE issue_id=? ORDER BY created_at, id', (issue_id,)).fetchall()
    return {**dict(row), 'attachments': [dict(a) for a in attachments]}


class StatusUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: Literal['pending', 'resolved']


@admin_router.patch('/{issue_id}', status_code=204)
def update_status(issue_id: str, body: StatusUpdate):
    with get_db() as conn:
        result = conn.execute('UPDATE feedback_issue SET status=?, updated_at=? WHERE id=?',
                              (body.status, datetime.now(timezone.utc).isoformat(), issue_id))
        if result.rowcount != 1:
            raise HTTPException(404, '问题不存在')


@admin_router.get('/{issue_id}/attachments/{attachment_id}')
def attachment(issue_id: str, attachment_id: str):
    with get_db() as conn:
        row = conn.execute('SELECT storage_name, content_type FROM feedback_attachment WHERE issue_id=? AND id=?', (issue_id, attachment_id)).fetchone()
    if not row:
        raise HTTPException(404, '截图不存在')
    root = (UPLOADS_DIR / 'feedback').resolve()
    path = (root / row['storage_name']).resolve()
    if path.parent != root or not path.is_file():
        raise HTTPException(404, '截图不存在')
    return FileResponse(path, media_type=row['content_type'], headers={
        'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
        'Content-Security-Policy': "default-src 'none'; sandbox",
    })
