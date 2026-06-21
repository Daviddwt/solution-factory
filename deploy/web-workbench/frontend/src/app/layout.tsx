import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "解决方案部 PPT 脚本生产台",
  description: "Company knowledge-base grounded PPT script workbench",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <body>{children}</body>
    </html>
  );
}
