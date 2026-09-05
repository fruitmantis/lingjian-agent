"use client";

import { SystemStatusTab } from "../../../components/admin-panels";

export default function AdminSystemPage() {
  return <main className="page"><p className="eyebrow">System Status</p><h1>系统状态</h1><p className="lead">查看数据库读取结果、模型配置和业务场景配置；未验证的运行状态会明确标注。</p><SystemStatusTab /></main>;
}
