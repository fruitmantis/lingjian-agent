"use client";

import { useEffect, useState } from "react";
import { use } from "react";

type Partner = {
  id: string;
  name: string;
  intro: string | null;
  capabilities: string | null;
  service_areas: string | null;
  industries: string | null;
  ai_profile: string | null;
  created_at: string;
};

type Case = {
  id: string;
  partner_id: string;
  title: string;
  description: string | null;
  created_at: string;
};

type Deliverable = {
  id: string;
  case_id: string;
  filename: string;
  file_path: string;
  created_at: string;
};

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export default function PartnerProfilePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [partner, setPartner] = useState<Partner | null>(null);
  const [cases, setCases] = useState<Case[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [caseTitle, setCaseTitle] = useState("");
  const [caseDesc, setCaseDesc] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [deliverablesMap, setDeliverablesMap] = useState<Record<string, Deliverable[]>>({});
  const [uploadingCaseId, setUploadingCaseId] = useState<string | null>(null);
  const [generatingProfile, setGeneratingProfile] = useState(false);

  async function loadPartner() {
    setLoading(true);
    setError(null);
    try {
      const [pRes, cRes] = await Promise.all([
        fetch(`${apiBaseUrl}/partners/${id}`, { cache: "no-store" }),
        fetch(`${apiBaseUrl}/cases/by-partner/${id}`, { cache: "no-store" }),
      ]);
      if (!pRes.ok) throw new Error(`Partner HTTP ${pRes.status}`);
      if (!cRes.ok) throw new Error(`Cases HTTP ${cRes.status}`);
      setPartner(await pRes.json());
      const caseList: Case[] = await cRes.json();
      setCases(caseList);
      const dMap: Record<string, Deliverable[]> = {};
      await Promise.all(
        caseList.map(async (c) => {
          const dRes = await fetch(`${apiBaseUrl}/cases/${c.id}/deliverables`, { cache: "no-store" });
          if (dRes.ok) dMap[c.id] = await dRes.json();
        })
      );
      setDeliverablesMap(dMap);
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { loadPartner(); }, [id]);

  async function handleCreateCase(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch(`${apiBaseUrl}/cases`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ partner_id: id, title: caseTitle, description: caseDesc || null }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setCaseTitle("");
      setCaseDesc("");
      await loadPartner();
    } catch (e) {
      setError(e instanceof Error ? e.message : "新增案例失败");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleUploadDeliverable(caseId: string, file: File) {
    setUploadingCaseId(caseId);
    setError(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await fetch(`${apiBaseUrl}/cases/${caseId}/deliverables`, { method: "POST", body: formData });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await loadPartner();
    } catch (e) {
      setError(e instanceof Error ? e.message : "上传失败");
    } finally {
      setUploadingCaseId(null);
    }
  }

  async function handleGenerateProfile() {
    setGeneratingProfile(true);
    setError(null);
    try {
      const res = await fetch(`${apiBaseUrl}/partners/${id}/profile`, { method: "POST" });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `HTTP ${res.status}`);
      }
      await loadPartner();
    } catch (e) {
      setError(e instanceof Error ? e.message : "生成画像失败");
    } finally {
      setGeneratingProfile(false);
    }
  }

  return (
    <main className="page">
      <p className="eyebrow">Partner Profile</p>
      <h1>伙伴画像详情</h1>
      <p className="lead">伙伴标识：{id}</p>

      <section className="card">
        <h2>基础信息</h2>
        {loading && <p>加载中...</p>}
        {error && <p className="error-text">{error}</p>}
        {partner && (
          <dl className="partner-detail">
            <dt>名称</dt><dd>{partner.name}</dd>
            <dt>简介</dt><dd>{partner.intro || "未填写"}</dd>
            <dt>能力标签</dt><dd>{partner.capabilities || "未填写"}</dd>
            <dt>服务区域</dt><dd>{partner.service_areas || "未填写"}</dd>
            <dt>行业经验</dt><dd>{partner.industries || "未填写"}</dd>
            <dt>创建时间</dt><dd>{partner.created_at}</dd>
          </dl>
        )}
      </section>

      <section className="card">
        <h2>AI 能力画像</h2>
        {partner?.ai_profile ? (
          <div className="ai-profile">
            <pre className="ai-profile-text">{partner.ai_profile}</pre>
            <button onClick={handleGenerateProfile} disabled={generatingProfile} className="secondary-btn">
              {generatingProfile ? "生成中..." : "重新生成"}
            </button>
          </div>
        ) : (
          <div className="ai-profile-empty">
            <p className="placeholder-text">暂无 AI 画像，点击下方按钮基于伙伴资料和案例生成。</p>
            <button onClick={handleGenerateProfile} disabled={generatingProfile}>
              {generatingProfile ? "生成中（可能需要数十秒）..." : "生成 AI 画像"}
            </button>
          </div>
        )}
      </section>

      <section className="card">
        <h2>新增案例</h2>
        <form onSubmit={handleCreateCase} className="partner-form">
          <div className="form-row">
            <label htmlFor="caseTitle">案例标题</label>
            <input id="caseTitle" type="text" value={caseTitle} onChange={(e) => setCaseTitle(e.target.value)} required maxLength={300} placeholder="案例标题" />
          </div>
          <div className="form-row">
            <label htmlFor="caseDesc">案例描述</label>
            <textarea id="caseDesc" value={caseDesc} onChange={(e) => setCaseDesc(e.target.value)} placeholder="选填" rows={3} />
          </div>
          <button type="submit" disabled={submitting}>{submitting ? "提交中..." : "新增案例"}</button>
        </form>
      </section>

      <section className="card">
        <h2>案例与交付物</h2>
        {cases.length === 0 ? (
          <p className="placeholder-text">暂无案例。</p>
        ) : (
          <ul className="case-list">
            {cases.map((c) => (
              <li key={c.id} className="case-item">
                <h3>{c.title}</h3>
                {c.description && <p>{c.description}</p>}
                <p className="meta-text">创建时间：{c.created_at}</p>
                <div className="deliverable-section">
                  <h4>交付物</h4>
                  {(deliverablesMap[c.id] || []).length === 0 ? (
                    <p className="placeholder-text">暂无交付物。</p>
                  ) : (
                    <ul className="deliverable-list">
                      {(deliverablesMap[c.id] || []).map((d) => (
                        <li key={d.id}>{d.filename}</li>
                      ))}
                    </ul>
                  )}
                  <label className="upload-btn">
                    {uploadingCaseId === c.id ? "上传中..." : "上传交付物"}
                    <input type="file" hidden disabled={uploadingCaseId === c.id} onChange={(e) => { const f = e.target.files?.[0]; if (f) handleUploadDeliverable(c.id, f); e.target.value = ""; }} />
                  </label>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
