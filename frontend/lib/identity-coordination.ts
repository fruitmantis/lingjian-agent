/** Coordinate the few browser-identity mutations when HTTP has no Web Locks. */
const channelName = "banfei-browser-identity";
const requests = new Map<string, number>();
let active: { id: string; until: number } | null = null;
const channel = typeof window !== "undefined" && typeof BroadcastChannel !== "undefined"
  ? new BroadcastChannel(channelName) : null;

function randomId(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return Array.from(bytes, value => value.toString(16).padStart(2, "0")).join("");
}

function broadcast(type: "request" | "active" | "release", id: string, at = Date.now(), reply = false) {
  channel?.postMessage({ type, id, at, reply });
}

if (channel) channel.onmessage = event => {
  const data = event.data;
  if (!data || typeof data.id !== "string" || !["request", "active", "release"].includes(data.type)) return;
  if (data.type === "request") {
    requests.set(data.id, data.at);
    if (active && active.until > Date.now()) broadcast("active", active.id, active.until);
    if (!data.reply) for (const [id, at] of requests) {
      if (id !== data.id) broadcast("request", id, at, true);
    }
  } else if (data.type === "active") {
    active = { id: data.id, until: data.at };
  } else {
    requests.delete(data.id);
    if (active?.id === data.id) active = null;
  }
};

const pause = (ms: number) => new Promise<void>(resolve => setTimeout(resolve, ms));

async function broadcastLock<T>(action: () => Promise<T>): Promise<T> {
  if (!channel) throw new Error("此浏览器无法协调多个标签页，请关闭其他伴飞标签页后刷新重试");
  const id = randomId();
  const at = Date.now();
  requests.set(id, at);
  broadcast("request", id, at);
  // Allow simultaneous tabs to discover one another before either mutates identity.
  await pause(120);
  while (true) {
    const now = Date.now();
    for (const [key, stamp] of requests) if (stamp < now - 45_000) requests.delete(key);
    if (active && active.until <= now) active = null;
    const first = [...requests].sort(([a, ta], [b, tb]) => ta - tb || a.localeCompare(b))[0]?.[0];
    if (first === id && !active) break;
    await pause(30);
  }
  active = { id, until: Date.now() + 45_000 };
  broadcast("active", id, active.until);
  try { return await action(); }
  finally {
    requests.delete(id);
    active = null;
    broadcast("release", id);
  }
}

export async function identityLock<T>(action: () => Promise<T>): Promise<T> {
  if (typeof navigator.locks?.request === "function") return navigator.locks.request(channelName, action);
  return broadcastLock(action);
}
