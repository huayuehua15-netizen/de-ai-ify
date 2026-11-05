import type { Metadata } from "next";

import { HistoryPage } from "@/components/history-page";

export const metadata: Metadata = {
  title: "改写历史",
  description: "查看改写记录与分数变化；隐私模式下不保存原文。",
};

export default function History() {
  return <HistoryPage />;
}
