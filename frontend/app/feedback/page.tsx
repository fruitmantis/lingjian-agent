"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { apiFetch } from "../../components/auth-provider";
import { responseError } from "../../lib/api-request";

const IMAGE_TYPES = new Set(["image/png", "image/jpeg", "image/webp", "image/gif"]);
type Screenshot = { id: number; file: File; url: string };

export default function FeedbackPage() {
  const [description, setDescription] = useState("");
  const [images, setImages] = useState<Screenshot[]>([]);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);
  const [busy, setBusy] = useState(false);
  const current = useRef<Screenshot[]>([]), nextId = useRef(0), submitting = useRef(false);
  const input = useRef<HTMLInputElement>(null);

  const addImages = useCallback((files: File[]) => {
    if (submitting.current || !files.length) return;
    setSuccess(false);
    if (files.some(file => !IMAGE_TYPES.has(file.type) || !/\.(png|jpe?g|webp|gif)$/i.test(file.name))) {
      setError("截图仅支持 PNG、JPEG、WebP、GIF 图片"); return;
    }
    if (files.some(file => file.size === 0 || file.size > 5 * 1024 * 1024)) {
      setError("每张截图须大于 0 字节且不超过 5 MB"); return;
    }
    if (current.current.length + files.length > 5) { setError("最多上传 5 张截图"); return; }
    setError("");
    current.current = [...current.current, ...files.map(file => ({ id: nextId.current++, file, url: URL.createObjectURL(file) }))];
    setImages(current.current);
  }, []);

  useEffect(() => {
    function paste(event: ClipboardEvent) {
      const files = Array.from(event.clipboardData?.files || []).filter(file => file.type.startsWith("image/"));
      if (files.length) { event.preventDefault(); addImages(files); }
    }
    window.addEventListener("paste", paste);
    return () => { window.removeEventListener("paste", paste); current.current.forEach(image => URL.revokeObjectURL(image.url)); };
  }, [addImages]);

  function remove(id: number) {
    const image = current.current.find(item => item.id === id);
    if (image) URL.revokeObjectURL(image.url);
    current.current = current.current.filter(item => item.id !== id);
    setImages(current.current);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (submitting.current) return;
    if (!description.trim()) { setError("请填写问题描述"); return; }
    submitting.current = true; setBusy(true); setError(""); setSuccess(false);
    try {
      const body = new FormData(); body.append("description", description.trim());
      current.current.forEach(image => body.append("images", image.file));
      const response = await apiFetch("/feedback", { method: "POST", body, timeoutMs: 60_000 });
      if (!response.ok) throw await responseError(response, "问题提交失败");
      current.current.forEach(image => URL.revokeObjectURL(image.url));
      current.current = []; setImages([]); setDescription(""); setSuccess(true);
    } catch (reason) { setError((reason as Error).message); }
    finally { submitting.current = false; setBusy(false); }
  }

  return <div className="feedback-page">
    <h1>问题反馈</h1>
    <form className="card feedback-form" onSubmit={submit}>
      <label className="enablement-field" htmlFor="feedback-description"><span>问题描述<span aria-hidden="true"> *</span></span>
        <textarea id="feedback-description" required maxLength={5000} rows={7} disabled={busy} value={description}
          onChange={event => { setDescription(event.target.value); setSuccess(false); }} placeholder="请描述你遇到的问题…" />
      </label>
      <div className="feedback-upload">
        <p>截图<span className="muted">（可选）</span></p>
        <p className="muted" id="feedback-image-help">可直接按 Ctrl+V 粘贴截图，或点击上传。支持 PNG、JPEG、WebP、GIF，最多 5 张，每张不超过 5 MB。</p>
        <input ref={input} type="file" aria-label="上传截图" aria-describedby="feedback-image-help" accept="image/png,image/jpeg,image/webp,image/gif" multiple hidden disabled={busy}
          onChange={event => { addImages(Array.from(event.target.files || [])); event.target.value = ""; }} />
        <button type="button" className="secondary-btn" disabled={busy || images.length >= 5} onClick={() => input.current?.click()}>上传图片</button>
        <div className="feedback-images">
          {images.map((image, index) => <figure key={image.id} className="feedback-thumbnail">
            {/* Local object URLs provide immediate previews without uploading. */}
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={image.url} alt={`截图 ${index + 1}`} />
            <figcaption><span title={image.file.name}>{image.file.name}</span><button type="button" className="secondary-btn" disabled={busy} aria-label={`删除截图 ${index + 1}`} onClick={() => remove(image.id)}>删除</button></figcaption>
          </figure>)}
        </div>
      </div>
      {error && <p role="alert" className="feedback-error">{error}</p>}
      {success && <p role="status" className="feedback-success">问题已提交</p>}
      <div><button type="submit" disabled={busy}>{busy ? "正在提交…" : "提交问题"}</button></div>
    </form>
  </div>;
}
