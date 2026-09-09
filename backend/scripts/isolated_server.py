"""Serve private runtime data; only loopback and enabled model endpoints may be reached."""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from dotenv import load_dotenv
load_dotenv(ROOT / '.env', override=False)
private = ROOT / '.isolation/runtime'
for key in ('LINGJIAN_DATABASE_PATH', 'LINGJIAN_UPLOADS_DIR', 'LINGJIAN_CHROMA_DIR'):
    value = Path(os.environ[key])
    if not value.resolve().is_relative_to(private) or value.is_symlink():
        raise RuntimeError('Isolated runtime paths must remain inside this worktree')
from app.database import get_readonly_db
from app.model_network_policy import install_model_network_policy

with get_readonly_db() as connection:
    endpoints = [row['base_url'] for row in connection.execute(
        'SELECT base_url FROM model_configs WHERE enabled = 1'
    ).fetchall() if row['base_url']]
install_model_network_policy(endpoints)

import uvicorn
uvicorn.run('app.main:app', host='127.0.0.1', port=8000)
