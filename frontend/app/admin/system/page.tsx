"use client";

import { SystemStatusTab } from "../../../components/admin-panels";

export default function AdminSystemPage() {
  return <main className="page"><p className="eyebrow">System Status</p><h1>系统状态</h1><p className="lead">查看数据库、模型和业务能力运行状态。</p><SystemStatusTab /></main>;
}
