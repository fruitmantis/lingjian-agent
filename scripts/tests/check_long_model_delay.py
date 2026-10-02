"""Opt-in real HTTP >=120s delay check. Synthetic loopback only; no application/DB."""
import argparse
from datetime import datetime, timezone
import hashlib
import http.client
import json
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.simulate_slow_model import slow_proxy
from scripts.tests.test_slow_model_simulation import Capture, upstream


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--delay-seconds', type=float, default=120)
    args = parser.parse_args()
    if not 120 <= args.delay_seconds <= 300:
        parser.error('Use a bounded real delay between 120 and 300 seconds')
    evidence = Path(tempfile.mkdtemp(prefix='banfei-long-model-delay-', dir='/tmp'))
    report = {'result': 'running', 'configured_delay_seconds': args.delay_seconds,
              'started_at_utc': datetime.now(timezone.utc).isoformat(),
              'scope': 'synthetic HTTP proxy only; no application, browser, database or real model',
              'evidence_directory': str(evidence)}
    print(json.dumps(report), flush=True)
    events = Capture()
    started = time.monotonic()
    try:
        with upstream() as (url, received, expected):
            with slow_proxy(url, delay=args.delay_seconds, port=0, events=events) as server:
                report.update(upstream_url=url, proxy_host='127.0.0.1', proxy_port=server.server_port)
                client = http.client.HTTPConnection('127.0.0.1', server.server_port,
                                                    timeout=args.delay_seconds + 30)
                payload = json.dumps({'model': 'synthetic', 'messages': [
                    {'role': 'user', 'content': 'Synthetic long response probe; no partner data.'}]}).encode()
                started = time.monotonic()
                try:
                    client.request('POST', '/v1/chat/completions', payload,
                                   {'Content-Type': 'application/json'})
                    response = client.getresponse()
                    body = response.read()
                    elapsed = time.monotonic() - started
                    report.update(http_status=response.status, elapsed_seconds=elapsed,
                                  upstream_request_count=len(received),
                                  response_sha256=hashlib.sha256(body).hexdigest(),
                                  expected_response_sha256=hashlib.sha256(expected).hexdigest(),
                                  body_preserved=body == expected,
                                  request_preserved=len(received) == 1 and received[0][1] == payload)
                    assert response.status == 200, 'Unexpected HTTP status'
                    assert elapsed >= args.delay_seconds, 'Response returned before configured wall-clock delay'
                    assert elapsed < args.delay_seconds + 30, 'Unexpected excessive elapsed time'
                    assert body == expected, 'Response body changed'
                    assert len(received) == 1 and received[0][1] == payload, 'Upstream request duplicated or changed'
                finally:
                    client.close()
        report['result'] = 'passed'
        return 0
    except Exception as error:
        report.update(result='failed', error_type=type(error).__name__, error=str(error),
                      elapsed_seconds=time.monotonic() - started)
        return 1
    finally:
        report['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
        report['proxy_events'] = events.rows
        (evidence/'result.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
        print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    raise SystemExit(main())
