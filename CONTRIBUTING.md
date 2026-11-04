# 贡献指南

感谢你愿意为 de-ai-ify 出力。这份文档说明怎么搭环境、怎么提 PR、以及我们看重的质量标准。

## 先决条件

| 工具 | 版本 | 说明 |
|---|---|---|
| Node.js | ≥ 20.9 | 前端 |
| pnpm | ≥ 9 | 前端包管理（仓库锁定 12.x） |
| Python | 3.13 | 后端 |
| uv | 最新 | Python 环境与依赖管理 |
| Docker | 可选 | 标准栈（PostgreSQL + Redis）；不装可用 lite 模式 |

## 本地开发

```powershell
# 1) 依赖
pnpm install
cd apps/api; uv sync

# 2) 配置（lite 模式，无需 Docker）
Copy-Item ..\..\.env.example .env
# 编辑 .env：
#   DEAIIFY_DATABASE_URL=sqlite+aiosqlite:///./data/deaiify.db
#   DEAIIFY_REDIS_URL=

# 3) 起服务
pnpm dev          # API :8000 + Web :3000
```

**开箱即可评分**——评分引擎是纯本地的，不需要任何模型 key。改写才需要配置供应商（Web 的 `/settings` 页，或 `.env`）。

## 提交前必跑

```powershell
pnpm lint          # ruff + eslint
pnpm test          # pytest（含 corpus 回归）
pnpm --filter web exec tsc --noEmit
pnpm --filter web test    # vitest
```

**四项全绿才能提 PR。** CI 会跑同样的检查。

## 分支与提交约定

- 分支：trunk-based，从 `main` 切 `feat/*`、`fix/*`、`docs/*`
- 提交信息：[Conventional Commits](https://www.conventionalcommits.org/)
  ```
  feat(engine): 新增 XX 检测维度
  fix(api): 修复 XX 超时未归一化
  docs: 更新 §5.4 权重说明
  ```
- 一个 PR 只做一件事；大改动请先开 Issue 讨论

## PR 要求

PR 描述里请包含：

1. **动机**：解决什么问题，关联的 Issue 编号
2. **改动**：改了什么，为什么这么改
3. **验证**：贴测试结果截图或命令输出
4. **影响面**：是否影响评分结果、API 契约、文档

## 特别重要的两类改动

### 动评分规则（`apps/api/src/deaiify/engine/`）

评分引擎是这个项目的立身之本，规则改动**必须**满足：

- `corpus/` 回归全绿：AI 样本均分 ≥ 65、人写样本均分 ≤ 35
- 新增/修改检测器要带表驱动单测
- 变更 `weights.json` 或任何灵敏度系数，PR 里说明校准依据
- 保留 `text[start:end] == matched` 不变式（有断言兜底，别绕过）

**不要为了凑分改验收线**，要改规则。

### 动词库（`engine/lexicons/*.txt`）

- 内置词库为自撰，不接受来源不明的整段复制
- 新增词条请说明语料来源与许可
- 正则层（`templates.*.txt`）务必测试不会灾难性回溯

## 代码风格

- Python：`ruff check` + `ruff format`（配置见 `pyproject.toml`）
- TypeScript：Next.js 官方 ESLint 规则 + 严格模式
- 注释写「为什么」，不写「做了什么」——代码本身说明后者

## 报告问题

- Bug：用 [Bug 模板](.github/ISSUE_TEMPLATE/bug_report.md)，附环境自检输出（`pnpm check:env`）
- 功能建议：用 [Feature 模板](.github/ISSUE_TEMPLATE/feature_request.md)
- 规则/词库建议：用 [Rule 模板](.github/ISSUE_TEMPLATE/rule_suggestion.md)，**务必带样例文本**
- 安全漏洞：**不要开公开 Issue**，见 [SECURITY.md](SECURITY.md)

## 许可

贡献的代码按 [MIT](LICENSE) 授权。提交 PR 即表示你同意这一点，并确认你有权提交这些内容。
