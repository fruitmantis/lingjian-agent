"use client";

import { ModelConfigTab } from "../../../components/admin-panels";

export default function AdminModelsPage() {
  return <main className="page"><p className="eyebrow">Model Configuration</p><h1>模型配置</h1><p className="lead">维护大模型连接参数和业务场景模型策略。</p><ModelConfigTab /></main>;
}
