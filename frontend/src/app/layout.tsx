import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "黔西南职院数据采集系统",
  description: "校内数据汇聚、审核、发布与共享平台",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
