import type { Metadata } from "next";

import { BatchPage } from "@/components/batch-page";

export const metadata: Metadata = {
  title: "批量改写",
  description: "一次改写多段文本，最多 50 段；单条失败不影响其他条目。",
};

export default function Batch() {
  return <BatchPage />;
}
