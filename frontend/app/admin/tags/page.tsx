"use client";

import { CapabilityTagsTab } from "../../../components/admin-panels";

export default function AdminTagsPage() {
  return <main className="page"><p className="eyebrow">Capability Tags</p><h1>能力标签</h1><p className="lead">维护标准能力标签、标签分类和 AI 标签建议。</p><CapabilityTagsTab /></main>;
}
