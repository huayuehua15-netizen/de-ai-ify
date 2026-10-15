import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "de-ai-ify · 去 AI 味",
    template: "%s · de-ai-ify",
  },
  description:
    "可解释的 AI 文本评分与改写：检测套话、句长均匀、结构重复等 AI 味特征，一键改写成更自然的人写文本。Web / REST API / CLI，可完全自托管，默认不保存原文。",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="zh-CN" className="h-full antialiased">
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
