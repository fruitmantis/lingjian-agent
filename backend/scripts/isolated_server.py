"""Serve private runtime data; only loopback and enabled model endpoints may be reached."""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'backend'))
from dotenv import load_dotenv
load_dotenv(ROOT / '.env', override=False)
private = ROOT / '.isolation/runtime'
for key in ('LINGJIAN_UPLOADS_DIR', 'LINGJIAN_CHROMA_DIR'):
    value = Path(os.environ[key])
    if not value.resolve().is_relative_to(private) or value.is_symlink():
        raise RuntimeError('Isolated runtime paths must remain inside this worktree')
from app.database import get_readonly_db
from app.model_network_policy import install_model_network_policy

def enabled_endpoints():
    with get_readonly_db() as connection:
        endpoints=[row['base_url'] for row in connection.execute(
            'SELECT base_url FROM model_configs WHERE enabled = 1'
        ).fetchall() if row['base_url']]
        if os.getenv('BANFEI_RUNTIME_EXTERNAL_DATA_APPROVED')=='1':
            from app import agent_settings
            from app.runtime_endpoint import validate_endpoint
            import json
            settings=agent_settings.read(connection)
            candidates=[value.get('runtimeUrl') for value in settings['agents'].values() if value.get('executor')=='runtime']
            # Accepted runs keep their destination even when an administrator edits settings.
            for row in connection.execute("SELECT a.value FROM app_metadata a JOIN match_records m ON a.key='match_understanding:'||m.id WHERE m.task_status IN ('matching','enriching')"):
                snapshot=json.loads(row[0]);execution=snapshot.get('agent_execution') or {}
                candidates.append(execution.get('runtimeUrl'))
            for row in connection.execute("SELECT input_snapshot FROM development_runs WHERE status IN ('pending','running')"):
                candidates.append((json.loads(row[0]).get('agent_execution') or {}).get('runtimeUrl'))
            endpoints.extend(validate_endpoint(value,external_approved=True)[0] for value in candidates if value)
        return endpoints

install_model_network_policy(enabled_endpoints)

import uvicorn
uvicorn.run('app.main:app', host='127.0.0.1', port=8000,
            proxy_headers=True, forwarded_allow_ips='127.0.0.1')
