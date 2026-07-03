import type { Metadata } from "next";
import AppShell from "../components/app-shell";
import "./globals.css";

export const metadata: Metadata = { title: "灵鉴 Agent", description: "交付伙伴智能匹配智能体" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
