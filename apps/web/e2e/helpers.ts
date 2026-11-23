import type { APIRequestContext } from "@playwright/test";

/**
 * e2e 共享夹具：把「后端有一条指向假上游的供应商」这件事变幂等。
 *
 * 为什么要抽出来：`rewrite.spec.ts` 与 `privacy.spec.ts` 都需要模型，
 * 但 Playwright 按文件名字母序执行（editor → privacy → rewrite → smoke），
 * 靠"前面那个用例会建好"是不可靠的耦合。每个 spec 自己调一次，
 * 有就复用、没有就建，谁先跑都对。
 *
 * 用 `APIRequestContext`（`request` fixture）而不是 `page.evaluate`：
 * 不依赖页面已加载、不受前端 CSP/时序影响，失败信息也更干净。
 */

export const FAKE_BASE_URL =
  process.env.E2E_FAKE_UPSTREAM ?? "http://127.0.0.1:9100/v1";

export const FAKE_MODEL = "fake-deaiify-1";

/** 假上游是否真的在跑（起不来就别让用例白等 30 秒超时）。 */
export async function fakeUpstreamAlive(request: APIRequestContext): Promise<boolean> {
  try {
    // 浏览器/Node 侧都能直连宿主机，不经 Web 代理
    const res = await request.get(`${FAKE_BASE_URL}/models`, { timeout: 5_000 });
    return res.ok();
  } catch {
    return false;
  }
}

/**
 * 保证后端存在一条 base_url 指向假上游的**默认且启用**的供应商。
 * 返回 false 表示前置条件不具备（调用方应 skip 而不是 fail）。
 */
export async function ensureFakeProvider(request: APIRequestContext): Promise<boolean> {
  if (!(await fakeUpstreamAlive(request))) return false;

  const listRes = await request.get("/api/v1/providers");
  if (!listRes.ok()) return false;

  type Provider = {
    id: string;
    base_url: string;
    default_model: string | null;
    is_default: boolean;
    enabled: boolean;
  };
  const list = (await listRes.json()) as Provider[];

  const hit = list.find((c) => c.base_url === FAKE_BASE_URL && c.enabled);
  if (hit) {
    if (hit.is_default && hit.default_model === FAKE_MODEL) return true;
    // 补默认模型 / 抢默认位
    const patch = await request.patch(`/api/v1/providers/${hit.id}`, {
      data: { default_model: FAKE_MODEL, is_default: true, enabled: true },
    });
    if (!patch.ok()) return false;
    if (!hit.is_default) {
      const mark = await request.post(`/api/v1/providers/${hit.id}/default`);
      if (!mark.ok()) return false;
    }
    return true;
  }

  const create = await request.post("/api/v1/providers", {
    data: {
      name: "e2e-fake",
      kind: "openai",
      base_url: FAKE_BASE_URL,
      api_key: "sk-e2e-fake",
      default_model: FAKE_MODEL,
      is_default: true,
    },
  });
  return create.ok();
}
