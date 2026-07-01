"use client";

import { useEffect, useState } from "react";


type ConnectionState = "checking" | "online" | "offline";

type HealthResponse = {
  status: string;
  service: string;
};

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";


export function HealthStatus() {
  const [connectionState, setConnectionState] = useState<ConnectionState>("checking");
  const [detail, setDetail] = useState("正在检查后端服务...");

  useEffect(() => {
    const controller = new AbortController();

    async function checkHealth() {
      try {
        const response = await fetch(`${apiBaseUrl}/health`, {
          cache: "no-store",
          signal: controller.signal,
        });

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        const data = (await response.json()) as HealthResponse;
        if (data.status !== "ok") {
          throw new Error("后端状态异常");
        }

        setConnectionState("online");
        setDetail(`${data.service} 响应正常`);
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setConnectionState("offline");
        setDetail("无法连接后端，请确认 FastAPI 已在 8000 端口启动");
      }
    }

    void checkHealth();
    return () => controller.abort();
  }, []);

  const statusText = {
    checking: "检查中",
    online: "后端已连接",
    offline: "后端未连接",
  }[connectionState];

  return (
    <article className="card">
      <h2>系统状态</h2>
      <p>{detail}</p>
      <div className="status-row" aria-live="polite">
        <span aria-hidden="true" className={`status-dot ${connectionState}`} />
        <span className="status-label">{statusText}</span>
      </div>
    </article>
  );
}
