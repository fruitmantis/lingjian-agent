"""Check the actual service entrypoint without starting HTTP or running lifespan."""
import json
import os
from pathlib import Path
import subprocess
import sys


def test_standard_entrypoint_loads_business_package_once_from_unrelated_cwd(tmp_path):
    root = Path(__file__).resolve().parents[2]
    entry = root / 'backend/scripts/isolated_server.py'
    env = dict(os.environ)
    env.update(
        PYTHONDONTWRITEBYTECODE='1',
        LINGJIAN_UPLOADS_DIR=str(root / '.isolation/runtime/startup-check/uploads'),
        LINGJIAN_CHROMA_DIR=str(root / '.isolation/runtime/startup-check/chroma'),
        LLM_API_KEY='synthetic-startup-only',
        BANFEI_ERROR_LOG_PATH=str(tmp_path / 'errors.jsonl'),
    )
    # These runtime paths are only checked by the entrypoint; lifespan is never
    # invoked, so no files/directories or business records are created there.
    env.pop('PYTHONPATH', None)
    child = r"""
import importlib,json,runpy,sys
import uvicorn
entry=sys.argv[1]
def inspect(app,**options):
    module,name=app.split(':')
    loaded=importlib.import_module(module)
    paths=getattr(loaded,name).openapi()['paths']
    assert app=='app.main:app'
    assert options['host']=='127.0.0.1' and options['port']==8000
    assert '/agents' in paths and '/admin/agents' in paths
    assert not any(k=='backend.app' or k.startswith('backend.app.') for k in sys.modules)
    assert 'backend.business.common' in sys.modules
    print(json.dumps({'entrypoint_imported':True,'new_routes_present':True,'duplicate_app_namespace':False}))
uvicorn.run=inspect
runpy.run_path(entry,run_name='__main__')
"""
    completed = subprocess.run(
        [sys.executable, '-B', '-c', child, str(entry)], cwd=tmp_path,
        env=env, capture_output=True, text=True, timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        'entrypoint_imported': True, 'new_routes_present': True,
        'duplicate_app_namespace': False,
    }
