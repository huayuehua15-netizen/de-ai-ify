# de-ai-ify

[![CI](https://github.com/huayuehua15-netizen/de-ai-ify/actions/workflows/ci.yml/badge.svg)](https://github.com/huayuehua15-netizen/de-ai-ify/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/)
[![Next.js 16](https://img.shields.io/badge/Next.js-16-black.svg)](https://nextjs.org/)

**中文** · [English](README.en.md)

> 把 AI 草稿，改成人写的。
> 可解释的 AI 文本评分与改写工具：检测并去除套话、空泛表达、结构重复与均匀句长——先评分解释，再一键改写，改完再验证。

**状态：M0 脚手架 ✅ · M1 评分引擎 ✅ · M2 API + 改写 ✅ · M3 Web 主流程 ✅ · M4 词库/隐私/供应商 ✅ · M5 CLI/Docker/文档 ✅**（完整设计见 [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)）

---

## 为什么做这个

大模型写出来的中文有一套很固定的毛病：什么都能夸一句"具有重要意义"，凡事都要"首先、其次、最后"，
句子长度整齐得像排版过的，正文里全是"进行/实现/提升"这类名词化表达，读完全篇却没记住任何一个具体事实。

这些特征**是可测量的**。de-ai-ify 把它们拆成八个维度逐条打分，指出具体位置和原因，再改写成更自然的表达，
最后重新评分验证改写是否真的有效——而不是让你凭感觉判断"看起来像不像 AI 写的"。

## 特性

- **AI 味评分**：八维度可解释评分（套话 / 句长均匀度 / 连接词 / 名词化 / 结构重复 / 模板句式 / 空泛度 / 个性化信号），逐条给出命中位置、原因与修改建议；
- **文体感知**：自动识别学术 / 公文 / 法律 / 技术文档 / 产品说明 / 新闻 / 口语七类文体，按文体重排维度权重——避免把公文的"一、二、三"、学术的"综上所述"误判为 AI 套话（实测：人写均分 19.4，AI 套话样本 87）；
- **多风格改写**：口语 / 简洁 / 学术 / 商务 / 社交五版本并行输出，改写后自动重评分展示 Δ；
- **质量闸门**：改写结果必须通过事实锚点召回、字数比区间、分数下降三重校验，不合格自动重试一次；
- **Diff 对比**：词级/字符级对比原稿与改写稿，双栏与内联两种视图；
- **自定义词库**：内置词库可逐条停用，支持增删改与 CSV / JSON 导入导出；
- **多供应商配置**：UI 内添加/测试/切换供应商（OpenAI / Anthropic / DeepSeek / 智谱 / Kimi / MiniMax / 百炼 / Ollama / 任意兼容端点），密钥加密存储、永不回显明文；
- **隐私模式**：评分纯本地完成，**默认不保存原文**，可一键清除；
- **多入口**：Web、REST API、CLI、Docker 自托管，同一引擎行为一致。

## 产品形态

本项目开源的是**可自托管的完整应用**（不是我们运营的在线服务，也不是桌面客户端）。拿到仓库后在自己的机器/服务器上运行，得到一个网页应用：

| 形态 | 说明 |
|---|---|
| 自托管 Web 应用 | `docker compose --profile full up -d` 或 `pnpm dev`，浏览器打开 `localhost:3000` |
| REST API | 部署后调用 `/api/v1/*`，接入自己的写作流水线 |
| CLI | `deaiify analyze ./文稿.md`、`deaiify batch ./目录/`，适合批量处理与 CI 集成 |
| Docker 镜像 | GHCR 发布（`ghcr.io/huayuehua15-netizen/de-ai-ify-api` / `-web`），拉取即部署 |

**开箱即可评分**：AI 味评分与特征高亮为纯本地规则引擎，不依赖任何模型、不配 key 可用。
**改写**功能需在 Web 的「模型设置」页添加一个供应商（或把 key 填进 `.env`），支持 OpenAI 兼容端点 / Anthropic / 本地 Ollama。

v1 不做：多租户 SaaS、桌面客户端、浏览器插件、平台 Skill（完整非目标见 [docs/DEVELOPMENT.md §17.3](docs/DEVELOPMENT.md)）。

## 快速开始

### 方式一：Docker（推荐，无需本地装 Python/Node）

```bash
git clone https://github.com/huayuehua15-netizen/de-ai-ify.git
cd de-ai-ify
docker compose --profile full up -d --build
```

打开 http://localhost:3000 即可评分；API 文档在 http://127.0.0.1:8000/docs。

镜像名与端口：`deaiify-api`（127.0.0.1:8000）、`deaiify-web`（127.0.0.1:3000）、
`deaiify-db`（PostgreSQL 15，127.0.0.1:5433）、`deaiify-redis`（127.0.0.1:6380）。

> 只想要存储（API/Web 在宿主机热重载）：`docker compose up -d db redis`。
> 暴露到公网前请设置 `DEAIIFY_API_KEY`，并把 `ports` 里的 `127.0.0.1` 改成实际监听地址。

### 方式二：本地开发

前置：Node ≥ 20.9、[pnpm](https://pnpm.io)、[uv](https://docs.astral.sh/uv/)；使用标准栈还需 Docker。

```bash
# 1) 安装前端依赖
pnpm install

# 2) 启动存储（标准栈：PostgreSQL + Redis；无 Docker 可跳过，用 lite 模式见 .env.example）
docker compose up -d db redis

# 3) 一条命令同时启动 API（:8000）与 Web（:3000）
pnpm dev
```

首次会自动用 uv 创建 Python 3.13 虚拟环境并安装后端依赖。

常用命令：

```powershell
pnpm check:env    # 环境自检
pnpm lint         # ruff + eslint
pnpm test         # pytest
pnpm build        # next build
uv run --project apps/api deaiify doctor   # 服务侧自检（存储连通性）
```

## CLI

```bash
# 评分（纯本地，不需要模型）
deaiify analyze 文稿.md              # 中文对齐的八维表格 + 命中详情
deaiify analyze 文稿.md --json       # 结构化输出，接管道
deaiify analyze 文稿.md --strict     # 有 high severity 命中时退出码 1（CI 用）

# 批量
deaiify batch ./文稿目录/ --style natural --out ./改写结果/

# 词库
deaiify lex list                     # 各层中英词条数
deaiify lex disable 综上所述 --layer cliches
deaiify lex export lex.json --layer cliches --lang zh

# 诊断
deaiify doctor                       # 存储连通性 + 引擎版本
deaiify models                       # 三个 provider 并行探测
```

退出码契约：`0` 成功 · `1` `analyze --strict` 有 high severity 或 `batch` 有失败 · `2` 配置错误。

## API

OpenAPI 文档在 `http://127.0.0.1:8000/docs`。

```bash
# AI 味评分——纯本地，不需要任何模型 key
curl -s http://127.0.0.1:8000/api/v1/analyze \
  -H "Content-Type: application/json" \
  -d '{"text":"综上所述，人工智能具有重要意义。首先，它提升效率；其次，它降低成本。"}'

# 一键改写——需先配置模型（Web「模型设置」页，或 .env 里的 DEAIIFY_OPENAI_BASE_URL / _API_KEY）
curl -s http://127.0.0.1:8000/api/v1/rewrite \
  -H "Content-Type: application/json" \
  -d '{"text":"……原文……","styles":["natural","concise"],"model":{"name":"你的模型名"}}'
```

> PowerShell 提示：内联 JSON 引号易被 curl 误解析，建议把 body 存成 UTF-8 文件后用 `--data-binary "@body.json"`。

## 架构

```
apps/web    Next.js 16 (App Router + Tailwind 4) — Web 入口
apps/api    FastAPI + SQLAlchemy 2.1 (Python 3.13, uv) — REST API / 评分引擎 / CLI
docker/     Dockerfile.api / Dockerfile.web — 多阶段构建，非 root 运行
corpus/     金标准语料（AI 样本 ≥65 分 / 人写样本 ≤35 分，回归门槛）
```

存储：**PostgreSQL 15 + Redis 7（Docker）为标准栈**；无 Docker 时可切 SQLite + 进程内队列的 lite 模式（见 [.env.example](.env.example)）。

## 隐私

默认隐私模式：评分在本地完成，原文不会被保存到数据库，也不会写入日志。
历史记录默认只保存**哈希、字数与分数**（不含原文），`stored_text` 恒为 NULL。
仅当你主动配置云端模型（如 OpenAI 兼容端点）时，原文才会随改写请求发送给该模型服务商；
即使开启「保存原文」开关，也需同时设置 `DEAIIFY_STORE=optin` 且单次请求显式指定。

供应商密钥以 Fernet（AES-128-CBC + HMAC-SHA256）加密存储，主密钥在 `DEAIIFY_SECRET_KEY`
或仓库根 `.deaiify-secret`（已 gitignore）。**主密钥保存在同机器上，能防数据库泄露，不防拿到文件系统的本机攻击者**；
多租户部署请改用 KMS/Vault。详见 [SECURITY.md](SECURITY.md)。

## 开发文档

完整设计（评分算法规格、API 契约、数据模型、里程碑）见 [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)。

## 参与贡献

欢迎 Issue 和 PR。开始之前请先读：

- [CONTRIBUTING.md](CONTRIBUTING.md) — 环境搭建、提交约定、PR 要求
- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) — 社区行为准则
- [CHANGELOG.md](CHANGELOG.md) — 变更记录
- [SECURITY.md](SECURITY.md) — 漏洞报告渠道（**请勿公开提 Issue**）

动评分规则前特别注意：`corpus/` 回归必须全绿（AI ≥65 / 人写 ≤35），且不接受为凑分修改验收线。

## License

[MIT](LICENSE)
