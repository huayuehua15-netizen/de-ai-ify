#!/usr/bin/env node
// 环境自检（docs/DEVELOPMENT.md §2.4）：必检项失败则退出码 1
import { execSync } from "node:child_process";

const checks = [
  { name: "node", cmd: "node --version", required: true },
  { name: "pnpm", cmd: "pnpm --version", required: true },
  { name: "uv", cmd: "uv --version", required: true },
  { name: "git", cmd: "git --version", required: true },
  { name: "docker", cmd: 'docker info --format "{{.ServerVersion}}"', required: false },
];

console.log("== de-ai-ify 环境自检 ==");

let failed = false;

// Node 最低版本要求（Next.js 16 需要 >= 20.9）
const [major, minor] = process.versions.node.split(".").map(Number);
if (major < 20 || (major === 20 && minor < 9)) {
  console.log(`[FAIL] ${"node".padEnd(12)} 需要 >= 20.9，当前 ${process.versions.node}`);
  failed = true;
} else {
  console.log(`[OK]   ${"node".padEnd(12)} v${process.versions.node}`);
}

for (const { name, cmd, required } of checks) {
  if (name === "node") continue;
  try {
    const out = execSync(cmd, {
      stdio: ["ignore", "pipe", "ignore"],
      timeout: 30_000,
    })
      .toString()
      .trim()
      .split("\n")[0]
      .trim();
    console.log(`[OK]   ${name.padEnd(12)} ${out}`);
  } catch {
    if (required) {
      console.log(`[FAIL] ${name.padEnd(12)} 未安装或不可用`);
      failed = true;
    } else {
      console.log(`[SKIP] ${name.padEnd(12)} 可选项，未安装/未运行（可改用 lite 模式，见 .env.example）`);
    }
  }
}

console.log(failed ? "== 有必检项未通过，请先安装后重试 ==" : "== 自检通过 ==");
process.exit(failed ? 1 : 0);
