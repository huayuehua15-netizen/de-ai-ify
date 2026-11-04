import type { Metadata } from "next";

import { SettingsPage } from "@/components/settings-page";

export const metadata: Metadata = {
  title: "模型设置",
  description: "配置模型供应商：OpenAI 兼容端点、Anthropic、Ollama 本地。",
};

export default function Settings() {
  return <SettingsPage />;
}
