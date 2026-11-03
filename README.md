# de-ai-ify

> 把 AI 草稿，改成人写的。
> 可解释的 AI 文本评分与改写工具：检测并去除套话、空泛表达、结构重复与均匀句长——先评分解释，再一键改写，改完再验证。

**状态：M0 脚手架 ✅ · M1 评分引擎 ✅ · M2 API + 改写 ✅ · M3 Web 主流程（开发中）**（开发文档见 [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)）

## 特性（规划）

- **AI 味评分**：八维度可解释评分（套话 / 句长均匀度 / 连接词 / 名词化 / 结构重复 / 模板句式 / 空泛度 / 个性化信号），逐条给出命中位置、原因与修改建议；
- **多风格改写**：口语 / 简洁 / 学术 / 商务等多版本并行输出，改写后自动重评分展示 Δ；
- **Diff 对比**：词级对比原稿与改写稿；
- **自定义词库**：内置词库可停用，支持增删改与 CSV / JSON 导入导出；
- **多模型接入**：OpenAI（含一切兼容端点）/ Anthropic / Ollama 统一适配层；
- **隐私模式**：评分纯本地完成，**默认不保存原文**，可一键清除；
- **多入口**：Web、REST API、CLI、Docker 自托管，同一引擎行为一致。

## 产品形态

本项目开源的是**可自托管的完整应用**（不是我们运营的在线服务，也不是桌面客户端）。拿到仓库后在自己的机器/服务器上运行，得到一个网页应用：

| 形态 | 说明 |
|---|---|
| 自托管 Web 应用 | `docker compose up -d` 或 `pnpm dev`，浏览器打开 `localhost:3000` |
| REST API | 部署后调用 `/api/v1/*`，接入自己的写作流水线 |
| CLI | `deaiify rewrite ./文稿/ --style natural`，批量处理 |
| Docker 镜像 | GHCR 发布，拉取即部署 |

**开箱即可评分**：AI 味评分与特征高亮为纯本地规则引擎，不依赖任何模型、不配 key 可用；**改写**功能需自备 OpenAI 兼容端点（key 填入环境变量）。
v1 不做：多租户 SaaS、桌面客户端、浏览器插件、平台 Skill（完整非目标见 [docs/DEVELOPMENT.md §17.3](docs/DEVELOPMENT.md)）。

## 快速开始

前置：Node ≥ 20.9、[pnpm](https://pnpm.io)、[uv](https://docs.astral.sh/uv/)；使用标准栈还需 Docker。

```bash
# 1) 安装前端依赖
pnpm install

# 2) 启动存储（标准栈：PostgreSQL + Redis；无 Docker 可跳过，用 lite 模式见 .env.example）
docker compose up -d

# 3) 一条命令同时启动 API（:8000）与 Web（:3000）
pnpm dev
```

打开 http://localhost:3000；API 文档在 http://127.0.0.1:8000/docs。
首次会自动用 uv 创建 Python 3.13 虚拟环境并安装后端依赖。

常用命令：

```powershell
pnpm check:env    # 环境自检
pnpm lint         # ruff + eslint
pnpm test         # pytest
pnpm build        # next build
uv run --project apps/api deaiify doctor   # 服务侧自检（存储连通性）
```

API 示例（OpenAPI 文档在 `http://127.0.0.1:8000/docs`）：

```bash
# AI 味评分——纯本地，不需要任何模型 key
curl -s http://127.0.0.1:8000/api/v1/analyze \
  -H "Content-Type: application/json" \
  -d '{"text":"综上所述，人工智能具有重要意义。首先，它提升效率；其次，它降低成本。"}'

# 一键改写——需先在 .env 配置模型（DEAIIFY_OPENAI_BASE_URL / _API_KEY）
curl -s http://127.0.0.1:8000/api/v1/rewrite \
  -H "Content-Type: application/json" \
  -d '{"text":"……原文……","styles":["natural","concise"],"model":{"name":"你的模型名"}}'
```

> PowerShell 提示：内联 JSON 引号易被 curl 误解析，建议把 body 存成 UTF-8 文件后用 `--data-binary "@body.json"`。

## 架构

```
apps/web    Next.js 16 (App Router + Tailwind 4) — Web 入口
apps/api    FastAPI + SQLAlchemy 2.1 (Python 3.13, uv) — REST API / 评分引擎 / CLI
```

存储：**PostgreSQL 15 + Redis 7（Docker）为标准栈**；无 Docker 时可切 SQLite + 进程内队列的 lite 模式（见 [.env.example](.env.example)）。
端口约定：PG `127.0.0.1:5433`、Redis `127.0.0.1:6380`（避开常见冲突）。

## 隐私

默认隐私模式：评分在本地完成，原文不会被保存到数据库，也不会写入日志。仅当你主动配置云端模型（如 OpenAI 兼容端点）时，原文才会随改写请求发送给该模型服务商。

## 开发文档

完整设计（评分算法规格、API、数据模型、里程碑）见 [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)。

## License

[MIT](LICENSE)
