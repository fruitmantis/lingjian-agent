// Same-origin transport. Model deadlines belong to the API's saved policy, so
// this proxy must not impose Next's independent 30-second idle timeout.
import http from "node:http";
import { Readable } from "node:stream";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const hopHeaders = new Set(["connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
  "te", "trailer", "transfer-encoding", "upgrade"]);

function filtered(headers: Headers) {
  const excluded = new Set([...hopHeaders, ...(headers.get("connection") || "").split(",").map(s => s.trim().toLowerCase())]);
  const result = new Headers();
  headers.forEach((value, name) => { if (!excluded.has(name)) result.append(name, value); });
  return result;
}

async function proxy(request: Request): Promise<Response> {
  const origin = process.env.BANFEI_API_PROXY_TARGET;
  if (!origin) return new Response(null, { status: 404 });
  const target = new URL(origin);
  if (target.protocol !== "http:" || target.hostname !== "127.0.0.1" || !/^\d+$/.test(target.port)
      || target.username || target.password || target.search || target.hash || target.pathname !== "/") {
    return new Response(null, { status: 503 });
  }
  const incoming = new URL(request.url);
  target.pathname = incoming.pathname.replace(/^\/api(?=\/)/, "");
  target.search = incoming.search;
  const headers = filtered(request.headers);
  headers.set("x-forwarded-host", request.headers.get("host") || incoming.host);
  headers.set("x-forwarded-proto", "http");
  headers.set("host", target.host);

  return new Promise(resolve => {
    const upstream = http.request(target, {
      method: request.method, headers: Object.fromEntries(headers), signal: request.signal,
    }, response => {
      const raw = new Headers();
      for (const [key, value] of Object.entries(response.headers)) {
        if (value !== undefined) for (const item of Array.isArray(value) ? value : [value]) raw.append(key, item);
      }
      const status = response.statusCode || 502;
      const body = request.method === "HEAD" || [204, 205, 304].includes(status)
        ? null : Readable.toWeb(response) as ReadableStream<Uint8Array>;
      if (body === null) response.resume();
      // Keep cancellation wired until the response body finishes streaming.
      const abort = () => response.destroy();
      request.signal.addEventListener("abort", abort, { once: true });
      response.on("close", () => request.signal.removeEventListener("abort", abort));
      resolve(new Response(body, { status, headers: filtered(raw) }));
    });
    upstream.on("error", () => resolve(Response.json({ detail: "服务异常，请联系管理员。" }, { status: 502 })));
    if (request.body) {
      const body = Readable.fromWeb(request.body as import("node:stream/web").ReadableStream<Uint8Array>);
      body.on("error", error => upstream.destroy(error));
      upstream.on("close", () => body.destroy());
      body.pipe(upstream);
    } else upstream.end();
  });
}

export { proxy as GET, proxy as HEAD, proxy as POST, proxy as PUT, proxy as PATCH, proxy as DELETE, proxy as OPTIONS };
