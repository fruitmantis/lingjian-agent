import type { Metadata } from "next";
import { Suspense } from "react";
import AppShell from "../components/app-shell";
import { AuthProvider } from "../components/auth-provider";
import "./globals.css";

export const metadata: Metadata = { title: "灵鉴助手", description: "伙伴能力发展与项目匹配智能助手" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>
        <Suspense fallback={null}><AuthProvider><AppShell>{children}</AppShell></AuthProvider></Suspense>
      </body>
    </html>
  );
}
