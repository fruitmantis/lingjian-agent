import { test, expect } from '@playwright/test';
import http from 'node:http';
import { once } from 'node:events';
import { GET, POST } from '../app/api/[...path]/route';
import { fetchWithTimeout, responseError, submissionIsUncertain } from '../lib/api-request';

test('asynchronous task creation sends directly and only lost acknowledgement is uncertain', async () => {
  expect(submissionIsUncertain(await responseError(Response.json({detail:'本次处理失败，请重试。',failureCode:'timeout'},{status:502})))).toBe(false);
  expect(submissionIsUncertain(await responseError(Response.json({detail:'failed'},{status:500})))).toBe(true);
  expect(submissionIsUncertain(await responseError(Response.json({detail:'failed',submissionAccepted:false},{status:503})))).toBe(false);
  const original = globalThis.fetch;
  const calls: string[] = [];
  try {
    globalThis.fetch = async input => { calls.push(String(input)); throw new TypeError('synthetic network failure'); };
    let failure: unknown;
    try { await fetchWithTimeout('http://app.test/api/agent/tasks',{method:'POST',body:'{}'}); } catch(error) { failure=error; }
    expect(failure).toBeTruthy();
    expect(submissionIsUncertain(failure)).toBe(true);
    expect(calls).toEqual(['http://app.test/api/agent/tasks']);
    calls.length=0;
    globalThis.fetch = async input => {const url=String(input);calls.push(url);if(new URL(url).pathname.endsWith('/model-timeout-settings'))return Response.json({timeoutSeconds:300,timeoutRetries:3});throw new TypeError('synthetic lost response');};
    try { await fetchWithTimeout('http://app.test/api/agent/tasks',{method:'POST',body:'{}'}); } catch(error) { failure=error; }
    expect(submissionIsUncertain(failure)).toBe(true);
    expect(calls).toEqual(['http://app.test/api/agent/tasks']);
  } finally { globalThis.fetch = original; }
});

test('model request reads current saved policy every time and never retries business POST', async () => {
  const originalFetch = globalThis.fetch, originalTimeout = AbortSignal.timeout;
  const budgets: number[] = [], calls: string[] = [];
  let policy = { timeoutSeconds:300, timeoutRetries:3 };
  try {
    AbortSignal.timeout = ms => { budgets.push(ms); return new AbortController().signal; };
    globalThis.fetch = async (input, init) => {
      const url = String(input); calls.push(url);
      expect(new Headers(init?.headers).get('Authorization')).toBe('Bearer synthetic-user');
      return Response.json(new URL(url).pathname.endsWith('/model-timeout-settings') ? policy : {ok:true});
    };
    const options = {method:'POST',headers:{Authorization:'Bearer synthetic-user'},body:'{"same":"input"}'};
    await fetchWithTimeout('http://app.test/api/admin/model-configs/id/test', options);
    policy = { timeoutSeconds:420, timeoutRetries:0 };
    await fetchWithTimeout('http://app.test/api/admin/model-configs/id/test', options);
    expect(budgets).toEqual([30_000,1_230_000,30_000,450_000]);
    expect(calls).toEqual(Array(2).fill(['http://app.test/api/model-timeout-settings?agent_id=processing','http://app.test/api/admin/model-configs/id/test']).flat());
    globalThis.fetch = async () => new Response(null, {status:401});
    const rejected = await fetchWithTimeout('http://app.test/api/partners/id/profile', options);
    expect(rejected.status).toBe(401);
    expect((await rejected.json()).submissionAccepted).toBe(false);
  } finally { globalThis.fetch = originalFetch; AbortSignal.timeout = originalTimeout; }
});

test('proxy preserves request data, Origin, authorization, multiple cookies and redirects', async () => {
  let received: any;
  const server = http.createServer(async (req, res) => {
    const chunks = []; for await (const chunk of req) chunks.push(chunk);
    received = {url:req.url, headers:req.headers, body:Buffer.concat(chunks)};
    res.writeHead(307, {'Set-Cookie':['session=synthetic; HttpOnly; SameSite=Strict','other=synthetic; HttpOnly'],Location:'/login'});
    res.end('redirect body');
  });
  server.listen(0,'127.0.0.1'); await once(server,'listening');
  const previous = process.env.BANFEI_API_PROXY_TARGET;
  process.env.BANFEI_API_PROXY_TARGET = `http://127.0.0.1:${(server.address() as any).port}`;
  try {
    const body = Buffer.from([0,1,2,253,254,255]);
    const response = await POST(new Request('http://app.test/api/documents?value=a%2Bb', {
      method:'POST',headers:{Origin:'http://app.test',Authorization:'Bearer synthetic',Cookie:'session=synthetic','Content-Type':'application/octet-stream'},body}));
    expect(received.url).toBe('/documents?value=a%2Bb');
    expect(received.headers.origin).toBe('http://app.test');
    expect(received.headers.authorization).toBe('Bearer synthetic');
    expect(received.headers.cookie).toBe('session=synthetic');
    expect(received.headers['x-forwarded-proto']).toBe('http');
    expect(received.body.equals(body)).toBeTruthy();
    expect(response.status).toBe(307);
    expect(response.headers.get('location')).toBe('/login');
    expect(response.headers.getSetCookie()).toHaveLength(2);
    expect(await response.text()).toBe('redirect body');
  } finally {
    if (previous === undefined) delete process.env.BANFEI_API_PROXY_TARGET; else process.env.BANFEI_API_PROXY_TARGET = previous;
    server.closeAllConnections(); await new Promise<void>(resolve => server.close(() => resolve()));
  }
});

test('proxy delivers streaming chunks before the upstream response finishes', async () => {
  let finish = () => {};
  const server = http.createServer((_req, res) => {
    res.writeHead(200, {'Content-Type':'text/plain'});
    res.write('first');
    finish = () => res.end('second');
  });
  server.listen(0,'127.0.0.1'); await once(server,'listening');
  const previous = process.env.BANFEI_API_PROXY_TARGET;
  process.env.BANFEI_API_PROXY_TARGET = `http://127.0.0.1:${(server.address() as any).port}`;
  try {
    const response = await GET(new Request('http://app.test/api/stream'));
    expect(response.status).toBe(200);
    const reader = response.body!.getReader();
    const first = await reader.read();
    expect(new TextDecoder().decode(first.value)).toBe('first');
    finish();
    const second = await reader.read();
    expect(new TextDecoder().decode(second.value)).toBe('second');
    expect((await reader.read()).done).toBe(true);
  } finally {
    finish();
    if (previous === undefined) delete process.env.BANFEI_API_PROXY_TARGET; else process.env.BANFEI_API_PROXY_TARGET = previous;
    server.closeAllConnections(); await new Promise<void>(resolve => server.close(() => resolve()));
  }
});

test('proxy waits past old 30 second idle cap and cancels upstream on client abort', async () => {
  test.setTimeout(45_000);
  let cancelled = false;
  const server = http.createServer((req, res) => {
    if (req.url === '/slow') { const timer = setTimeout(() => res.end('complete'),31_000); res.on('close',()=>clearTimeout(timer)); }
    else res.on('close', () => { cancelled = true; });
  });
  server.listen(0,'127.0.0.1'); await once(server,'listening');
  const previous = process.env.BANFEI_API_PROXY_TARGET;
  process.env.BANFEI_API_PROXY_TARGET = `http://127.0.0.1:${(server.address() as any).port}`;
  try {
    expect(await (await GET(new Request('http://app.test/api/slow'))).text()).toBe('complete');
    const controller = new AbortController();
    const result = GET(new Request('http://app.test/api/cancel', {signal:controller.signal}));
    await once(server,'request'); controller.abort();
    await result;
    await expect.poll(() => cancelled).toBeTruthy();
  } finally {
    if (previous === undefined) delete process.env.BANFEI_API_PROXY_TARGET; else process.env.BANFEI_API_PROXY_TARGET = previous;
    server.closeAllConnections(); await new Promise<void>(resolve => server.close(() => resolve()));
  }
});
