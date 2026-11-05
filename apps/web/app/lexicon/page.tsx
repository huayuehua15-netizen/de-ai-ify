import type { Metadata } from "next";

import { LexiconPage } from "@/components/lexicon-page";

export const metadata: Metadata = {
  title: "词库管理",
  description: "管理自定义词库、导入导出词条、停用内置词库条目。",
};

export default function Lexicon() {
  return <LexiconPage />;
}
