"use client";

import { FormEvent, useEffect, useState } from "react";
import { adminApiFetch } from "./auth-provider";
import { responseError } from "../lib/api-request";

type Settings = {
  timeoutSeconds: number; timeoutRetries: number;
};
const path = "/admin/model-configs/timeout-settings";

export function ModelTimeoutSettings() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [seconds, setSeconds] = useState("");
  const [retries, setRetries] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  function apply(data: Settings) {
    setSettings(data); setSeconds(String(data.timeoutSeconds)); setRetries(String(data.timeoutRetries));
  }
  async function load() {
    setLoading(true); setError("");
    try {
      const response = await adminApiFetch(path, { cache: "no-store" });
      if (!response.ok) throw await responseError(response, "超时设置加载失败");
      apply(await response.json());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "超时设置加载失败");
    } finally { setLoading(false); }
  }
  useEffect(() => { void load(); }, []);

  async function save(event: FormEvent) {
    event.preventDefault();
    if (saving) return;
    setMessage(""); setError("");
    const timeoutSeconds = Number(seconds), timeoutRetries = Number(retries);
    if (!Number.isFinite(timeoutSeconds) || timeoutSeconds <= 0 || !Number.isSafeInteger(timeoutRetries) || timeoutRetries < 0) {
      setError("超时时间须大于 0，重试次数须为非负整数。"); return;
    }
    setSaving(true);
    try {
      const response = await adminApiFetch(path, {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ timeoutSeconds, timeoutRetries }),
      });
      if (!response.ok) throw await responseError(response, "超时设置保存失败");
      const data: Settings = await response.json();
      apply(data);
      setMessage("设置已保存，新发起的模型调用立即生效。");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "超时设置保存失败");
    } finally { setSaving(false); }
  }

  return <section className="card" aria-labelledby="model-timeout-title">
    <h2 id="model-timeout-title">超时与重试</h2>
    <p className="muted">所有模型统一使用，仅超时自动重试。保存后新发起的模型调用立即生效，已发出的请求按原设置完成。</p>
    {loading ? <p className="muted">正在加载超时设置…</p> : settings && <form className="form-grid" onSubmit={save}>
      <div className="form-row"><label htmlFor="model-timeout-seconds">单次超时（秒）</label>
        <input id="model-timeout-seconds" type="number" min="0" step="any" required value={seconds} disabled={saving} onChange={event => setSeconds(event.target.value)} />
      </div>
      <div className="form-row"><label htmlFor="model-timeout-retries">超时重试次数</label>
        <input id="model-timeout-retries" type="number" min="0" step="1" required value={retries} disabled={saving} onChange={event => setRetries(event.target.value)} />
        <span className="muted">首次请求之外的重试次数，0 表示不重试。</span>
      </div>
      <div className="form-span-two">
        <button type="submit" disabled={saving}>{saving ? "保存中…" : "保存超时设置"}</button>
      </div>
    </form>}
    {message && <p role="status">{message}</p>}
    {error && <div className="inline-error-actions"><p className="error-text" role="alert">{error}</p>
      {!settings && <button type="button" className="secondary-btn" disabled={loading} onClick={() => void load()}>重新加载超时设置</button>}
    </div>}
  </section>;
}
