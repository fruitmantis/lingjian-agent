import json
import os
import socket
from backend.app.database import get_db
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROCESS_SECRET = "process-validation-secret-0123456789-ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_health(url: str, process: subprocess.Popen, timeout: float = 15) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"process exited before health check: {process.returncode}")
        try:
            with urllib.request.urlopen(url, timeout=0.5) as response:
                if response.status == 200:
                    return
        except (OSError, urllib.error.URLError):
            time.sleep(0.1)
    raise TimeoutError(f"health check timed out: {url}")


def stop_process(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def request_json(url: str, *, token: str | None = None, payload: dict | None = None, timeout: float = 20):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode() if payload is not None else None,
        headers=headers, method="POST" if payload is not None else "GET",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.status, json.loads(response.read() or b"{}")


def task_state(requirement: str):
    with get_db() as connection:
        return connection.execute(
            "SELECT id, task_status, last_error_stage FROM match_records WHERE requirement = ?",
            (requirement,),
        ).fetchone()


@pytest.mark.parametrize("crash_stage", ["matching", "enriching"])
def test_real_process_crash_recovers_task_and_allows_retry(tmp_path, crash_stage):
    uploads = tmp_path / f"{crash_stage}-uploads"
    fake_port = free_port()
    backend_port = free_port()
    base_env = os.environ.copy()
    base_env.update({
        "LINGJIAN_UPLOADS_DIR": str(uploads),
        "LINGJIAN_CHROMA_DIR": str(tmp_path / f"{crash_stage}-chroma"),
        "JWT_SECRET_KEY": PROCESS_SECRET,
        "BOOTSTRAP_ADMIN_USERNAME": "unused_bootstrap",
        "BOOTSTRAP_ADMIN_PASSWORD": "UnusedBootstrap123",
        "VALIDATION_FAKE_LLM_BASE_URL": f"http://127.0.0.1:{fake_port}/v1",
    })
    fake_env = base_env.copy()
    fake_env["FAKE_LLM_MATCH_DELAY_SECONDS"] = "4" if crash_stage == "matching" else "0"
    fake_env["FAKE_LLM_ENRICH_DELAY_SECONDS"] = "0"
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    fake_log = (log_dir / "fake.log").open("w")
    backend_log = (log_dir / "backend.log").open("w")
    fake = backend = restarted = None
    try:
        subprocess.run(
            [sys.executable, "-m", "backend.tests.support.seed_validation_db"],
            cwd=PROJECT_ROOT, env=base_env, check=True, capture_output=True, text=True,
        )
        fake = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "backend.tests.support.fake_llm_server:app", "--host", "127.0.0.1", "--port", str(fake_port)],
            cwd=PROJECT_ROOT, env=fake_env, stdout=fake_log, stderr=subprocess.STDOUT,
        )
        wait_health(f"http://127.0.0.1:{fake_port}/health", fake)
        command=[sys.executable,"-m","uvicorn","app.main:app","--app-dir","backend","--host","127.0.0.1","--port",str(backend_port)]
        marker=tmp_path/'enrichment-entered'
        if crash_stage=='enriching':
            # Block the actual persistence-stage entry, after recommendations commit.
            # A supplier delay now belongs to matching, not to derivative persistence.
            script=f"""
import sys,time
from pathlib import Path
sys.path.insert(0,{str(PROJECT_ROOT/'backend')!r})
from app.routers import match
def held(*args,**kwargs):
    Path({str(marker)!r}).write_text('enrichment entered')
    while True:time.sleep(.05)
match._run_task_enrichment=held
from app.main import app
import uvicorn
uvicorn.run(app,host='127.0.0.1',port={backend_port},log_level='error')
"""
            command=[sys.executable,'-c',script]
        backend = subprocess.Popen(command,cwd=PROJECT_ROOT,env=base_env,stdout=backend_log,stderr=subprocess.STDOUT)
        wait_health(f"http://127.0.0.1:{backend_port}/health", backend)
        token = jwt.encode(
            {
                "sub": "user-a-id", "username": "user_a", "role": "user", "ver": 0, "amr": "key", "sid": "fixture-session-user-a-id",
                "iat": datetime.now(timezone.utc), "exp": datetime.now(timezone.utc) + timedelta(hours=1),
            },
            PROCESS_SECRET, algorithm="HS256",
        )
        requirement = f"PROCESS-CRASH-{crash_stage}"
        request_error = []

        def submit_task():
            try:
                request_json(
                    f"http://127.0.0.1:{backend_port}/agent/match", token=token,
                    payload={"requirement": requirement}, timeout=15,
                )
            except Exception as exc:  # expected when the owned backend process is killed
                request_error.append(type(exc).__name__)

        thread = threading.Thread(target=submit_task, daemon=True)
        thread.start()
        deadline = time.time() + 10
        state = None
        while time.time() < deadline:
            state = task_state(requirement)
            if state and state[1] == crash_stage and (crash_stage!='enriching' or marker.exists()):
                break
            time.sleep(0.05)
        assert state is not None and state[1] == crash_stage
        if crash_stage=='enriching':
            assert marker.read_text()=='enrichment entered'
            with get_db() as connection:
                assert json.loads(connection.execute('SELECT recommendations_json FROM match_records WHERE id=?',(state[0],)).fetchone()[0])

        backend.kill()
        backend.wait(timeout=5)
        thread.join(timeout=6)
        # Simulate the recovery deadline in this disposable DB, without a runtime override.
        with get_db() as connection:
            connection.execute("UPDATE match_records SET updated_at=? WHERE id=?", ((datetime.now(timezone.utc)-timedelta(days=1)).isoformat(), state[0]))
        restarted = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--app-dir", "backend", "--host", "127.0.0.1", "--port", str(backend_port)],
            cwd=PROJECT_ROOT, env=base_env, stdout=backend_log, stderr=subprocess.STDOUT,
        )
        wait_health(f"http://127.0.0.1:{backend_port}/health", restarted)
        recovered = task_state(requirement)
        assert recovered[1:] == ("failed", "interrupted")
        status_code, response = request_json(
            f"http://127.0.0.1:{backend_port}/agent/tasks/{recovered[0]}/retry",
            token=token, payload={}, timeout=20,
        )
        assert status_code == 200
        assert response["taskStatus"] == "ready"
        assert task_state(requirement)[1] == "ready"
    finally:
        stop_process(restarted)
        stop_process(backend)
        stop_process(fake)
        backend_log.close()
        fake_log.close()
