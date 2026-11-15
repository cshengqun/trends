import type { Metadata } from "next";
import type { ReactNode } from "react";
import { Shell } from "@/components/shell";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Trends · 趋势发现", template: "%s · Trends" },
  description: "探索 A 股与港股公司财务趋势。当前为明确标识的 Mock 数据演示环境。",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return <html lang="zh-CN"><body><Shell>{children}</Shell></body></html>;
}
