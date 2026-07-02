"use client";

import { useEffect, useState, useRef } from "react";
import { use } from "react";

type Partner = { id: string; name: string; intro: string | null; capabilities: string | null; service_areas: string | null; industries: string | null; ai_profile: string | null; created_at: string; };
type PartnerDoc = { id: string; partner_id: string; filename: string; file_type: string; doc_category: string | null; extracted_text: string | null; created_at: string; };

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

function authHeaders(): Record<string, string> {
  const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export default function PartnerProfilePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [partner, setPartner] = useState<Partner | null>(null);
  const [docs, setDocs] = useState<PartnerDoc[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [generatingProfile, setGeneratingProfile] = useState(false);
  const [previewDoc, setPreviewDoc] = useState<PartnerDoc | null>(null);
  const [previewContent, setPreviewContent] = useState<string>("加载中...");
  const [previewLoading, setPreviewLoading] = useState(false);
  const [pptxHtml, setPptxHtml] = useState("");
  const docxContainerRef = useRef<HTMLDivElement>(null);
  const xlsxContainerRef = useRef<HTMLDivElement>(null);

  async function loadPartner() {
    setLoading(true); setError(null);
    try {
      const [pRes, dRes] = await Promise.all([
        fetch(`${apiBaseUrl}/partners/${id}`, { cache: "no-store", headers: authHeaders() }),
        fetch(`${apiBaseUrl}/partners/${id}/documents`, { cache: "no-store", headers: authHeaders() })
      ]);
      if (!pRes.ok) throw new Error(`Partner HTTP ${pRes.status}`);
      if (!dRes.ok) throw new Error(`Docs HTTP ${dRes.status}`);
      setPartner(await pRes.json());
      setDocs(await dRes.json());
    } catch (e) { setError(e instanceof Error ? e.message : "加载失败"); } finally { setLoading(false); }
  }

  useEffect(() => { loadPartner(); }, [id]);

  async function handleGenerateProfile() {
    setGeneratingProfile(true); setError(null);
    try {
      const res = await fetch(`${apiBaseUrl}/partners/${id}/profile`, { method: "POST", headers: authHeaders() });
      if (!res.ok) { const ed = await res.json().catch(() => ({})); throw new Error(ed.detail || `HTTP ${res.status}`); }
      await loadPartner();
    } catch (e) { setError(e instanceof Error ? e.message : "生成画像失败"); } finally { setGeneratingProfile(false); }
  }

  async function handlePreview(doc: PartnerDoc) {
    setPreviewDoc(doc);
    setPreviewLoading(true);
    setPreviewContent("");
    try {
      const fileRes = await fetch(`${apiBaseUrl}/partners/${id}/documents/${doc.id}/file`, { headers: authHeaders() });
      if (!fileRes.ok) throw new Error(`HTTP ${fileRes.status}`);
      const blob = await fileRes.blob();

      if (doc.file_type === "pdf") {
        const url = URL.createObjectURL(blob);
        setPreviewContent(url);
      } else if (doc.file_type === "docx") {
        const arrayBuffer = await blob.arrayBuffer();
        setPreviewContent("__docx__");
        setTimeout(async () => {
          const { renderAsync } = await import("docx-preview");
          if (docxContainerRef.current) {
            docxContainerRef.current.innerHTML = "";
            await renderAsync(arrayBuffer, docxContainerRef.current);
          }
          setPreviewLoading(false);
        }, 100);
        return;
      } else if (doc.file_type === "xlsx") {
        const arrayBuffer = await blob.arrayBuffer();
        setPreviewContent("__xlsx__");
        setTimeout(async () => {
          const XLSX = await import("xlsx");
          const wb = XLSX.read(arrayBuffer, { type: "array" });
          if (xlsxContainerRef.current) {
            xlsxContainerRef.current.innerHTML = "";
            wb.SheetNames.forEach((sheetName) => {
              const ws = wb.Sheets[sheetName];
              const html = XLSX.utils.sheet_to_html(ws, { editable: false });
              const wrapper = document.createElement("div");
              wrapper.innerHTML = `<h4 style="margin:8px 0 4px;font-size:14px">${sheetName}</h4>${html}`;
              wrapper.querySelector("table")?.setAttribute("style", "border-collapse:collapse;width:100%;font-size:12px");
              xlsxContainerRef.current!.appendChild(wrapper);
            });
          }
          setPreviewLoading(false);
        }, 100);
        return;
      } else if (doc.file_type === "pptx") {
        const previewRes = await fetch(`${apiBaseUrl}/partners/${id}/documents/${doc.id}/preview`, { headers: authHeaders() });
        if (previewRes.ok) {
          const html = await previewRes.text();
          setPptxHtml(html);
          setPreviewContent("__pptx_html__");
        } else {
          setPreviewContent("__pptx_download__");
        }
      } else {
        if (doc.extracted_text) {
          setPreviewContent(doc.extracted_text);
        } else {
          const text = await blob.text();
          setPreviewContent(text || "无法预览此文件内容");
        }
      }
    } catch (e) {
      setPreviewContent("预览加载失败: " + (e instanceof Error ? e.message : "未知错误"));
    } finally {
      if (doc.file_type !== "docx" && doc.file_type !== "xlsx") {
        setPreviewLoading(false);
      }
    }
  }

  return (
    <main className="page">
      <div style={{ marginBottom: "20px" }}>
        <a href="/profiles" style={{ display: "inline-flex", alignItems: "center", gap: "6px", padding: "10px 20px", fontSize: "14px", fontWeight: 600, color: "var(--brand)", background: "white", border: "1px solid var(--brand)", borderRadius: "8px", textDecoration: "none", transition: "all 0.2s" }}>← 返回伙伴画像</a>
      </div>
      <p className="eyebrow">Partner Profile</p>
      <h1>伙伴画像详情</h1>
      <p className="lead">伙伴标识：{id}</p>

      <section className="card">
        <h2>基础信息</h2>
        {loading && <p>加载中...</p>}
        {error && <p className="error-text">{error}</p>}
        {partner && (
          <div style={{ display: "flex", flexDirection: "column", gap: "16px", marginTop: "16px" }}>
            <div style={{ display: "flex", gap: "16px", flexWrap: "wrap" }}>
              <div style={{ flex: "1 1 200px", padding: "16px", background: "#f8f9fa", borderRadius: "8px", border: "1px solid var(--line)" }}>
                <div style={{ fontSize: "12px", color: "var(--muted)", fontWeight: 600, marginBottom: "6px" }}>名称</div>
                <div style={{ fontSize: "16px", fontWeight: 600 }}>{partner.name}</div>
              </div>
              <div style={{ flex: "1 1 200px", padding: "16px", background: "#f8f9fa", borderRadius: "8px", border: "1px solid var(--line)" }}>
                <div style={{ fontSize: "12px", color: "var(--muted)", fontWeight: 600, marginBottom: "6px" }}>创建时间</div>
                <div style={{ fontSize: "14px" }}>{partner.created_at.slice(0, 10)}</div>
              </div>
            </div>
            {partner.intro && (
              <div style={{ padding: "16px", background: "#f8f9fa", borderRadius: "8px", border: "1px solid var(--line)" }}>
                <div style={{ fontSize: "12px", color: "var(--muted)", fontWeight: 600, marginBottom: "6px" }}>简介</div>
                <div style={{ fontSize: "14px", lineHeight: 1.8 }}>{partner.intro}</div>
              </div>
            )}
            <div style={{ display: "flex", gap: "16px", flexWrap: "wrap" }}>
              <div style={{ flex: "1 1 200px", padding: "16px", background: "#fff1f2", borderRadius: "8px", border: "1px solid #ffd0d4" }}>
                <div style={{ fontSize: "12px", color: "var(--brand-dark)", fontWeight: 600, marginBottom: "8px" }}>能力标签</div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
                  {(partner.capabilities || "未分析").split(/[,，]/).filter(Boolean).map((tag, i) => (
                    <span key={i} style={{ display: "inline-block", padding: "4px 10px", fontSize: "13px", borderRadius: "6px", background: "white", color: "var(--brand-dark)", border: "1px solid #ffd0d4", fontWeight: 500 }}>{tag.trim()}</span>
                  ))}
                </div>
              </div>
              <div style={{ flex: "1 1 200px", padding: "16px", background: "#f0f5ff", borderRadius: "8px", border: "1px solid #d6e4ff" }}>
                <div style={{ fontSize: "12px", color: "#1a4fa0", fontWeight: 600, marginBottom: "8px" }}>覆盖区域</div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
                  {(partner.service_areas || "未分析").split(/[,，]/).filter(Boolean).map((tag, i) => (
                    <span key={i} style={{ display: "inline-block", padding: "4px 10px", fontSize: "13px", borderRadius: "6px", background: "white", color: "#1a4fa0", border: "1px solid #d6e4ff", fontWeight: 500 }}>{tag.trim()}</span>
                  ))}
                </div>
              </div>
              <div style={{ flex: "1 1 200px", padding: "16px", background: "#f0fdf4", borderRadius: "8px", border: "1px solid #bbf7d0" }}>
                <div style={{ fontSize: "12px", color: "var(--success)", fontWeight: 600, marginBottom: "8px" }}>行业经验</div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
                  {(partner.industries || "未分析").split(/[,，]/).filter(Boolean).map((tag, i) => (
                    <span key={i} style={{ display: "inline-block", padding: "4px 10px", fontSize: "13px", borderRadius: "6px", background: "white", color: "var(--success)", border: "1px solid #bbf7d0", fontWeight: 500 }}>{tag.trim()}</span>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}
      </section>

      {/* 伙伴资料预览 */}
      <section className="card">
        <h2>伙伴资料预览</h2>
        {docs.length === 0 ? <p className="placeholder-text" style={{ marginTop: "12px" }}>暂无伙伴资料文档。</p> : (
          <div style={{ marginTop: "12px" }}>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "8px", marginBottom: "16px" }}>
              {docs.map((d) => (
                <button key={d.id} onClick={() => handlePreview(d)} className="secondary-btn" style={{
                  fontSize: "12px", padding: "6px 12px",
                  background: previewDoc?.id === d.id ? "var(--brand)" : "white",
                  color: previewDoc?.id === d.id ? "white" : "var(--brand)",
                  border: `1px solid var(--brand)`,
                }}>{d.filename} <span style={{ opacity: 0.7 }}>({d.file_type})</span></button>
              ))}
            </div>
            {previewDoc && (
              <div style={{ border: "1px solid var(--line)", borderRadius: "8px", padding: "16px", background: "white", minHeight: "300px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px", paddingBottom: "8px", borderBottom: "1px solid var(--line)" }}>
                  <span style={{ fontSize: "14px", fontWeight: 600 }}>{previewDoc.filename}</span>
                  <a href={`${apiBaseUrl}/partners/${id}/documents/${previewDoc.id}/file`} target="_blank" rel="noopener noreferrer" className="secondary-btn" style={{ fontSize: "12px", padding: "4px 10px" }}>下载</a>
                </div>
                {previewLoading && <p>加载预览中...</p>}
                {!previewLoading && previewContent === "" && <p className="placeholder-text">点击文件名预览内容</p>}
                {!previewLoading && previewContent === "__pptx_download__" && (
                  <div style={{ padding: "20px", textAlign: "center" }}>
                    <p style={{ fontSize: "14px", color: "var(--muted)", marginBottom: "12px" }}>PPTX 文件暂不支持在线预览，请下载查看</p>
                    <a href={`${apiBaseUrl}/partners/${id}/documents/${previewDoc.id}/file`} target="_blank" rel="noopener noreferrer" className="secondary-btn" style={{ fontSize: "13px", padding: "8px 16px" }}>下载文件</a>
                  </div>
                )}
                {!previewLoading && previewContent.startsWith("http") && previewDoc.file_type === "pdf" && (
                  <iframe src={previewContent} style={{ width: "100%", height: "600px", border: "none" }} title="PDF Preview" />
                )}
                {!previewLoading && previewContent === "__pptx_html__" && (
                  <div dangerouslySetInnerHTML={{ __html: pptxHtml }} style={{ maxHeight: "600px", overflow: "auto" }} />
                )}
                {!previewLoading && !previewContent.startsWith("http") && previewContent !== "__docx__" && previewContent !== "__xlsx__" && previewContent !== "__pptx_download__" && previewContent !== "__pptx_html__" && previewContent !== "" && (
                  <pre style={{ whiteSpace: "pre-wrap", wordBreak: "break-word", fontSize: "13px", lineHeight: 1.8, maxHeight: "600px", overflow: "auto" }}>{previewContent}</pre>
                )}
                {previewContent === "__docx__" && <div ref={docxContainerRef} style={{ maxHeight: "600px", overflow: "auto" }} />}
                {previewContent === "__xlsx__" && <div ref={xlsxContainerRef} style={{ maxHeight: "600px", overflow: "auto" }} />}
              </div>
            )}
          </div>
        )}
      </section>

      <section className="card">
        <h2>AI 能力画像</h2>
        {partner?.ai_profile ? (<div className="ai-profile"><pre className="ai-profile-text">{partner.ai_profile}</pre><button onClick={handleGenerateProfile} disabled={generatingProfile} className="secondary-btn">{generatingProfile ? "生成中..." : "重新生成"}</button></div>) : (<div className="ai-profile-empty"><p className="placeholder-text">暂无 AI 画像。请在伙伴资料管理页面上传文档后生成。</p><button onClick={handleGenerateProfile} disabled={generatingProfile}>{generatingProfile ? "生成中（可能需要数十秒）..." : "生成 AI 画像"}</button></div>)}
      </section>
    </main>
  );
}