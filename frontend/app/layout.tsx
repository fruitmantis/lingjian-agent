import type { Metadata } from "next";
import { Suspense } from "react";
import AppShell from "../components/app-shell";
import { AuthProvider } from "../components/auth-provider";
import { TaskNavigationProvider } from "../components/task-navigation";
import "./globals.css";
import "./ui-system.css";

export const metadata: Metadata = { title: "伴飞 Agent", description: "伙伴能力发展与项目匹配智能助手" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>
        <Suspense fallback={null}><AuthProvider><TaskNavigationProvider><AppShell>{children}</AppShell></TaskNavigationProvider></AuthProvider></Suspense>
      </body>
    </html>
  );
}
