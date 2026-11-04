import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "de-ai-ify · 去 AI 味",
    template: "%s · de-ai-ify",
  },
  description:
    "可解释的 AI 文本评分与改写：检测套话、句长均匀、结构重复等 AI 味特征，一键改写成更自然的人写文本。Web / REST API / CLI，可完全自托管，默认不保存原文。",
};

/**
 * 根布局。
 *
 * 注意：这里显式声明 `{ children: ReactNode }` 而不用 Next 16 自动生成的
 * 全局 `LayoutProps<"/">`——后者定义在 .next/types/（gitignore、仅 build 后存在），
 * 在干净克隆的仓库上直接跑 `tsc --noEmit` 会报 "Cannot find name 'LayoutProps'"。
 * 根布局本就不需要路由参数，显式类型更简单也更稳。
 */
export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="zh-CN" className="h-full antialiased">
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
