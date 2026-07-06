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
  healthScore: number;
  healthLevel: string;
  healthReason: string;
};

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

function authHeaders(): Record<string, string> {
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

function healthBadge(score: number, level: string) {
  const labels: Record<string, string> = { healthy: "健康", normal: "一般", risk: "风险", unknown: "未评分" };
  const colors: Record<string, { color: string; bg: string; border: string }> = {
    healthy: { color: "var(--success)", bg: "#f0fdf4", border: "#bbf7d0" },
    normal: { color: "#e8a317", bg: "#fffbeb", border: "#fde68a" },
    risk: { color: "var(--danger)", bg: "#fef2f2", border: "#fecaca" },
    unknown: { color: "var(--muted)", bg: "#f8f9fa", border: "var(--line)" },
  };
  const c = colors[level] || colors.unknown;
  return { label: labels[level] || "未评分", ...c };
}

export default function ProfilesPage() {
  const [searchKeyword, setSearchKeyword] = useState("");
  const [filterCap, setFilterCap] = useState("");
  const [filterIndustry, setFilterIndustry] = useState("");
  const [filterRegion, setFilterRegion] = useState("");
  const [sortBy, setSortBy] = useState("default");
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
      <input type="text" placeholder="搜索伙伴名称、能力标签..." value={searchKeyword} onChange={(e) => setSearchKeyword(e.target.value)} style={{ width: "100%", padding: "10px 16px", border: "1px solid var(--line)", borderRadius: "8px", fontSize: "14px", marginBottom: "16px" }} />
      <div style={{ display: "flex", gap: "12px", marginBottom: "20px", flexWrap: "wrap" }}>
        <input type="text" placeholder="能力标签筛选" value={filterCap} onChange={(e) => setFilterCap(e.target.value)} style={{ flex: "1 1 140px", padding: "8px 12px", border: "1px solid var(--line)", borderRadius: "8px", fontSize: "14px" }} />
        <input type="text" placeholder="行业筛选" value={filterIndustry} onChange={(e) => setFilterIndustry(e.target.value)} style={{ flex: "1 1 120px", padding: "8px 12px", border: "1px solid var(--line)", borderRadius: "8px", fontSize: "14px" }} />
        <input type="text" placeholder="区域筛选" value={filterRegion} onChange={(e) => setFilterRegion(e.target.value)} style={{ flex: "1 1 120px", padding: "8px 12px", border: "1px solid var(--line)", borderRadius: "8px", fontSize: "14px" }} />
        <select value={sortBy} onChange={(e) => setSortBy(e.target.value)} style={{ padding: "8px 12px", border: "1px solid var(--line)", borderRadius: "8px", fontSize: "14px" }}><option value="default">默认排序</option><option value="name-asc">名称 A-Z</option><option value="name-desc">名称 Z-A</option><option value="health-desc">健康度从高到低</option><option value="health-asc">健康度从低到高</option></select>
      </div>
      {profiles.length === 0 ? <p className="placeholder-text">暂无伙伴画像数据。</p> : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))", gap: "20px" }}>
          {(() => {
          let filtered = profiles.filter(p =>
            (!searchKeyword || p.name?.includes(searchKeyword) || (p.capabilities || "").includes(searchKeyword)) &&
            (!filterCap || (p.capabilities || "").includes(filterCap)) &&
            (!filterIndustry || (p.industries || "").includes(filterIndustry)) &&
            (!filterRegion || (p.service_areas || "").includes(filterRegion))
          );
          if (sortBy === "name-asc") filtered = [...filtered].sort((a, b) => (a.name || "").localeCompare(b.name || ""));
          else if (sortBy === "name-desc") filtered = [...filtered].sort((a, b) => (b.name || "").localeCompare(a.name || ""));
          else if (sortBy === "health-desc") filtered = [...filtered].sort((a, b) => (b.healthScore || 0) - (a.healthScore || 0));
          else if (sortBy === "health-asc") filtered = [...filtered].sort((a, b) => (a.healthScore || 0) - (b.healthScore || 0));
          return filtered;
        })().map((p) => (
            <div key={p.id} className="card" style={{ marginBottom: 0, padding: "24px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "16px", marginBottom: "12px" }}><h2 style={{ margin: 0, flex: 1, minWidth: 0, fontSize: "15px", lineHeight: 1.4, overflow: "hidden", textOverflow: "ellipsis", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical" }}><a href={`/partners/${p.id}`}>{p.name}</a></h2>{(() => { const hb = healthBadge(p.healthScore || 0, p.healthLevel || "unknown"); return <div title={`伙伴健康度：${p.healthScore || 0}分`} style={{ minWidth: "72px", height: "56px", display: "flex", alignItems: "center", justifyContent: "center", borderRadius: "14px", background: hb.bg, border: `1px solid ${hb.border}`, flexShrink: 0 }}><span style={{ fontSize: "30px", fontWeight: 800, color: hb.color, lineHeight: 1 }}>{p.healthScore > 0 ? p.healthScore : "--"}</span></div>; })()}</div>
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
