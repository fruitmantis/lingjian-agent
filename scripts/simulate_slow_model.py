"""Loopback delay proxy: forward a model response unchanged after a fixed delay.

This standalone test utility never reads application configuration or databases,
sets model timeouts, or retries requests. Non-streaming chat completions only.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path
import signal
import tempfile
import threading
import time
from urllib.parse import urlsplit


class Events:
    def __init__(self, path):
        self.path = path
        self.lock = threading.Lock()
        self.sequence = 0

    def request_id(self):
        with self.lock:
            self.sequence += 1
            return self.sequence

    def emit(self, event, **values):
        row = {'time': datetime.now(timezone.utc).isoformat(), 'event': event, **values}
        line = json.dumps(row, ensure_ascii=False)
        with self.lock:
            with self.path.open('a', encoding='utf-8') as stream:
                stream.write(line + '\n')
            print(line, flush=True)


def upstream_url(value):
    parsed = urlsplit(value)
    try:
        valid_port = parsed.port is None or 1 <= parsed.port <= 65535
    except ValueError:
        valid_port = False
    if (parsed.scheme not in ('http', 'https') or not parsed.hostname or
            parsed.username or parsed.password or parsed.query or parsed.fragment or
            not valid_port):
        raise ValueError('上游须为不含凭据、query 或 fragment 的 HTTP(S) Base URL')
    if parsed.scheme == 'http' and parsed.hostname not in ('127.0.0.1', 'localhost', '::1'):
        raise ValueError('非本机上游必须使用 HTTPS')
    return parsed


@contextmanager
def slow_proxy(upstream, *, delay, port, events):
    target = upstream_url(upstream)
    stopped = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # No headers, credentials, model input or output in logs.

        def respond(self, status, body, headers=None):
            self.send_response(status)
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            self.wfile.flush()

        def error(self, status, message):
            self.respond(status, json.dumps({'error': {'message': message}}).encode(),
                         {'Content-Type': 'application/json'})

        def do_GET(self):
            if self.path == '/health':
                self.respond(200, json.dumps({'status': 'ok', 'delay_seconds': delay}).encode(),
                             {'Content-Type': 'application/json'})
            else:
                self.error(404, 'Not found')

        def do_POST(self):
            if self.path != '/v1/chat/completions':
                self.error(404, 'Use /v1/chat/completions')
                return
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if self.headers.get('Transfer-Encoding') or not 0 < size <= 16 * 1024 * 1024:
                    raise ValueError
                payload = self.rfile.read(size)
                parsed = json.loads(payload)
                if len(payload) != size or not isinstance(parsed, dict):
                    raise ValueError
            except (ValueError, OSError):
                self.error(400, 'Expected a JSON request with Content-Length')
                return
            if parsed.get('stream'):
                self.error(400, 'This delay proxy supports non-streaming requests only')
                return

            request_id = events.request_id()
            started = time.monotonic()
            events.emit('request_received', request_id=request_id)
            connection_type = http.client.HTTPSConnection if target.scheme == 'https' else http.client.HTTPConnection
            # No extra model timeout, automatic retry, redirects, or inherited proxy.
            connection = connection_type(target.hostname, target.port, timeout=None)
            try:
                headers = {'Content-Type': self.headers.get('Content-Type', 'application/json')}
                if self.headers.get('Authorization'):
                    headers['Authorization'] = self.headers['Authorization']
                connection.request('POST', target.path.rstrip('/') + '/chat/completions',
                                   body=payload, headers=headers)
                response = connection.getresponse()
                status = response.status
                body = response.read()
                response_headers = {name: response.getheader(name) for name in
                                    ('Content-Type', 'Retry-After', 'X-Request-ID')
                                    if response.getheader(name) is not None}
            except (OSError, http.client.HTTPException) as error:
                events.emit('upstream_error', request_id=request_id, exception_type=type(error).__name__)
                try:
                    self.error(502, 'Delay proxy could not read the upstream response')
                except OSError:
                    pass
                return
            finally:
                connection.close()

            events.emit('response_waiting', request_id=request_id, status=status,
                        upstream_seconds=round(time.monotonic() - started, 3), delay_seconds=delay)
            if stopped.wait(delay):
                return
            try:
                self.respond(status, body, response_headers)
                events.emit('response_sent', request_id=request_id,
                            elapsed_seconds=round(time.monotonic() - started, 3))
            except OSError:
                events.emit('client_disconnected', request_id=request_id)

    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    # A stalled upstream must not prevent this standalone process from stopping.
    server.daemon_threads = True
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=.05), daemon=True)
    thread.start()
    try:
        yield server
    finally:
        stopped.set()
        server.shutdown()
        server.server_close()
        thread.join(2)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream', required=True, help='original model Base URL, e.g. https://api.deepseek.com')
    parser.add_argument('--delay-seconds', type=float, default=180, help='extra response delay, default 180 seconds')
    parser.add_argument('--port', type=int, default=18181, help='loopback listen port, default 18181')
    args = parser.parse_args(argv)
    try:
        upstream_url(args.upstream)
    except ValueError as error:
        parser.error(str(error))
    if not math.isfinite(args.delay_seconds) or args.delay_seconds < 0:
        parser.error('delay-seconds must be finite and >= 0')
    if not 1 <= args.port <= 65535:
        parser.error('port must be between 1 and 65535')
    directory = Path(tempfile.mkdtemp(prefix='banfei-slow-model-', dir='/tmp'))
    events = Events(directory / 'events.jsonl')
    done = threading.Event()
    previous = {sig: signal.signal(sig, lambda *_: done.set()) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        with slow_proxy(args.upstream, delay=args.delay_seconds, port=args.port, events=events) as server:
            events.emit('proxy_started', base_url=f'http://127.0.0.1:{server.server_port}/v1',
                        delay_seconds=args.delay_seconds, events_file=str(events.path))
            done.wait()
    except OSError as error:
        events.emit('proxy_start_failed', exception_type=type(error).__name__)
        return 1
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    events.emit('proxy_stopped')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
