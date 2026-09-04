"use client";

import Link from "next/link";

export default function ForbiddenPage() {
  return <main className="public-state"><div className="card public-state-card"><p className="eyebrow">403 Forbidden</p><h1>没有访问权限</h1><p className="lead">当前账号无权访问该页面，请返回灵鉴助手继续工作。</p><Link href="/" className="btn-primary-lg">返回灵鉴助手</Link></div></main>;
}
