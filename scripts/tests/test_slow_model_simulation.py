"""Real loopback checks for the delay proxy; no database or external provider."""
from contextlib import contextmanager
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import time
import unittest

from scripts.simulate_slow_model import slow_proxy


class Capture:
    def __init__(self):
        self.rows = []
        self.sequence = 0
        self.lock = threading.Lock()
        self.waiting = threading.Event()

    def request_id(self):
        with self.lock:
            self.sequence += 1
            return self.sequence

    def emit(self, event, **values):
        with self.lock:
            self.rows.append({'event': event, **values})
        if event == 'response_waiting':
            self.waiting.set()


@contextmanager
def upstream(status=200):
    requests = []
    body = b'{"choices":[{"message":{"content":"synthetic result"},"finish_reason":"stop"}]}'

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            requests.append((self.path, self.rfile.read(int(self.headers['Content-Length'])),
                             self.headers.get('Authorization')))
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Retry-After', '9')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=.01), daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}/v1', requests, body
    finally:
        server.shutdown()
        server.server_close()
        thread.join(1)


class SlowModelProxyTests(unittest.TestCase):
    def test_delay_preserves_request_response_and_upstream_status(self):
        for status in (200, 429):
            with self.subTest(status=status), upstream(status) as (url, received, body):
                events = Capture()
                with slow_proxy(url, delay=.2, port=0, events=events) as server:
                    client = http.client.HTTPConnection('127.0.0.1', server.server_port)
                    payload = b'{"model":"synthetic","messages":[{"role":"user","content":"private-probe"}]}'
                    started = time.monotonic()
                    client.request('POST', '/v1/chat/completions', payload,
                                   {'Authorization': 'Bearer synthetic-private-key'})
                    response = client.getresponse()
                    self.assertEqual(response.read(), body)
                    self.assertGreaterEqual(time.monotonic() - started, .19)
                    self.assertEqual(response.status, status)
                    self.assertEqual(response.getheader('Retry-After'), '9')
                    client.close()
                self.assertEqual(received, [('/v1/chat/completions', payload, 'Bearer synthetic-private-key')])
                self.assertNotIn('private-probe', json.dumps(events.rows))
                self.assertNotIn('synthetic-private-key', json.dumps(events.rows))

    def test_client_chooses_timeout_and_proxy_does_not_retry(self):
        with upstream() as (url, received, _):
            with slow_proxy(url, delay=.3, port=0, events=Capture()) as server:
                client = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=.05)
                client.request('POST', '/v1/chat/completions', b'{"model":"synthetic"}')
                with self.assertRaises(TimeoutError):
                    client.getresponse()
                client.close()
                time.sleep(.4)
                self.assertEqual(len(received), 1)

    def test_stop_interrupts_delay_and_streaming_is_not_forwarded(self):
        with upstream() as (url, received, _):
            events = Capture()
            with slow_proxy(url, delay=180, port=0, events=events) as server:
                invalid = http.client.HTTPConnection('127.0.0.1', server.server_port)
                invalid.request('POST', '/v1/chat/completions', b'{"stream":true}')
                self.assertEqual(invalid.getresponse().status, 400)
                invalid.close()
                self.assertEqual(received, [])
                client = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=2)
                client.request('POST', '/v1/chat/completions', b'{"model":"synthetic"}')
                self.assertTrue(events.waiting.wait(2))
                started = time.monotonic()
            self.assertLess(time.monotonic() - started, 1)
            with self.assertRaises(http.client.RemoteDisconnected):
                client.getresponse()
            client.close()


if __name__ == '__main__':
    unittest.main()
