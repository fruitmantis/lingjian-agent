import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = { title: "灵鉴 Agent", description: "交付伙伴智能匹配智能体" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>
        <div className="app-shell">
          <header className="topbar">
            <Link className="brand" href="/">
              <span aria-hidden="true" className="brand-mark" />
              灵鉴 Agent
            </Link>
            <nav aria-label="主导航" className="nav">
              <Link href="/">Agent 工作台</Link>
              <Link href="/profiles">伙伴画像</Link>
              <Link href="/partners">伙伴资料管理</Link>
              <Link href="/demands">需求运营</Link>
              <Link href="/admin">系统管理</Link>
            </nav>
          </header>
          {children}
        </div>
      </body>
    </html>
  );
}
