"use client";

import { useState, useEffect } from "react";

type ProfileCard = {
  id: string;
  name: string;
  capabilities: string | null;
  service_areas: string | null;
  industries: string | null;
  ai_profile: string | null;
  case_count: number;
  deliverable_count: number;
};

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

function authHeaders() {
  const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function TagGroup({ label, value }: { label: string; value: string | null }) {
  const tags = value ? value.split(/[,，]/).map(t => t.trim()).filter(Boolean) : [];
  return (
    <div style={{ marginBottom: "10px" }}>
      <span style={{ fontSize: "12px", color: "var(--muted)", fontWeight: 600, marginRight: "8px" }}>{label}</span>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "6px", marginTop: "4px" }}>
        {tags.length === 0 ? (
          <span style={{ fontSize: "13px", color: "var(--muted)" }}>未分析</span>
        ) : (
          tags.map((tag, i) => (
            <span key={i} style={{ display: "inline-block", padding: "4px 10px", fontSize: "13px", borderRadius: "6px", background: "#fff1f2", color: "var(--brand-dark)", border: "1px solid #ffd0d4", fontWeight: 500 }}>{tag}</span>
          ))
        )}
      </div>
    </div>
  );
}

export default function ProfilesPage() {
  const [profiles, setProfiles] = useState<ProfileCard[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${apiBaseUrl}/partners/profiles`, { cache: "no-store", headers: authHeaders() })
      .then(res => { if (!res.ok) throw new Error(`HTTP ${res.status}`); return res.json(); })
      .then(data => { setProfiles(data); setLoading(false); })
      .catch(e => { setError(e instanceof Error ? e.message : "加载失败"); setLoading(false); });
  }, []);

  if (loading) return <main className="page"><p>加载中...</p></main>;

  return (
    <main className="page">
      <p className="eyebrow">Partner Profiles</p>
      <h1>伙伴画像</h1>
      <p className="lead">以卡片形式展示所有伙伴的能力画像、覆盖区域、行业经验及案例交付物统计。</p>
      {error && <p className="error-text">{error}</p>}
      {profiles.length === 0 ? <p className="placeholder-text">暂无伙伴画像数据。</p> : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))", gap: "20px", marginTop: "24px" }}>
          {profiles.map((p) => (
            <div key={p.id} className="card" style={{ marginBottom: 0, padding: "24px" }}>
              <h2 style={{ marginBottom: "12px" }}><a href={`/partners/${p.id}`}>{p.name}</a></h2>
              <TagGroup label="能力" value={p.capabilities} />
              <TagGroup label="覆盖区域" value={p.service_areas} />
              <TagGroup label="行业经验" value={p.industries} />
              <div style={{ display: "flex", gap: "12px", marginTop: "16px", padding: "12px 16px", background: "#f8f9fa", borderRadius: "8px", border: "1px solid var(--line)" }}>
                <div style={{ textAlign: "center", flex: 1 }}>
                  <div style={{ fontSize: "24px", fontWeight: 700, color: "var(--brand)" }}>{p.case_count}</div>
                  <div style={{ fontSize: "12px", color: "var(--muted)" }}>案例数</div>
                </div>
                <div style={{ width: "1px", background: "var(--line)" }}></div>
                <div style={{ textAlign: "center", flex: 1 }}>
                  <div style={{ fontSize: "24px", fontWeight: 700, color: "var(--brand)" }}>{p.deliverable_count}</div>
                  <div style={{ fontSize: "12px", color: "var(--muted)" }}>交付物数</div>
                </div>
              </div>
              {p.ai_profile ? <p style={{ marginTop: "12px", fontSize: "13px", color: "var(--success)" }}>✓ AI 画像已生成</p> : <p style={{ marginTop: "12px", fontSize: "13px", color: "var(--muted)" }}>暂无 AI 画像</p>}
            </div>
          ))}
        </div>
      )}
    </main>
  );
}
