# 变更日志

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。
`engine_version` 独立维护——评分规则变更才算 engine 的破坏性变更。

## [Unreleased]

### 计划中

- 批量任务 `/batch`（进度持久化、部分失败、刷新恢复）
- Web 端 `/lexicon` 词库管理页、`/history` 历史页
- CLI 完整命令集（`analyze` / `rewrite` / `batch` / `lex` / `models` / `serve`）
- 供应商密钥加密迁移到 `cryptography.Fernet`（见 SECURITY.md 已知限制）
- Docker 镜像（`docker/Dockerfile.api`、`docker/Dockerfile.web`）

## [0.1.0] - 2026-11-04

首个可用版本。核心链路完整：**评分 → 改写 → 重评分验证**。

### 新增

**评分引擎（engine 1.0.0）**
- 八维可解释评分：套话密度、句长均匀度、连接词密度、名词化倾向、结构重复、模板句式、空泛度、个性化信号
- 每条命中给出位置、原因、修改建议；保证 `text[start:end] == matched` 不变式
- 内置词库 961 条（中英双语，四层结构）
- corpus 回归：AI 样本均分 ≥65、人写 ≤35

**文体感知权重（v0.1.0 起）**
- 识别学术 / 公文 / 法律 / 技术文档 / 产品说明 / 新闻 / 口语七类文体
- 按文体重排维度权重，修正反向维度对正式文体的系统性误判
- 实测效果：学术 40.7→30.0、公文 24.5→10.5、法律 24→8.5、人写整体 25.0→19.4；AI 套话样本维持 87 分

**改写管线**
- 三 provider 适配层：OpenAI（含所有兼容端点）、Anthropic、Ollama 原生
- 五风格预设：自然口语 / 简洁直接 / 学术克制 / 商务简报 / 社交媒体
- 质量闸门：事实锚点 100% 召回 + 字数比约束 + Δscore 判定，失败自动重试一次
- SSE 流式输出（`start`/`delta`/`retry`/`version`/`score`/`error`/`done`）

**Web 界面**
- 主编辑器：textarea + 镜像 overlay 高亮（中文 IME 友好），防抖 600ms 自动评分
- 评分面板：总分环 + 八维条 + 命中列表双向联动
- 多版本 Tabs + 质量闸门徽章 + 采纳/撤销
- Diff 视图：双栏 / 内联，中文按字符级、英文按词级
- 字数上限提示（进度条 + 三档配色），上限由后端配置下发
- 模型设置页：9 个供应商预设、表单、连通性测试

**词库与隐私**
- 词库 CRUD、CSV/JSON 导入导出、内置词条停用
- 自定义词条参与评分（支持 exact / regex / contains 三种匹配）
- 隐私模式：默认不保存原文，`optin` 模式才落 `stored_text`，支持 TTL 与一键清除

**多供应商配置**
- 供应商 CRUD + 连通性实测 + 默认切换
- 密钥加密落库，响应只返回掩码
- 解析优先级：请求指定 > DB 默认 > `.env`

**基础设施**
- lite 模式（SQLite + 进程内队列）零配置可用；标准栈支持 PostgreSQL + Redis
- 统一错误体 `{"error": {code, message, request_id}}`
- 可选 API key 鉴权 + 进程内滑动窗口限流
- GitHub Actions CI：python / api-int / web 三个 job

### 修复

- `/models` 探测串行阻塞事件循环，导致首屏 `health`/`styles` 被代理掐断（改为并行 + 线程池 + 30s 缓存）
- Ollama 客户端未设 `trust_env=False`，系统代理把 127.0.0.1 请求误路由进代理
- provider 注册表全表 `clear()` 造成启动预热与请求的竞态（改为只淘汰同 provider 旧签名）
- 测试数据写入真实开发库（改为会话级 DB 隔离夹具）
- `health` 的 `providers` 判定误把 ollama 默认地址当已配置

### 已知问题

- 供应商密钥加密非审计实现，不防本机文件系统攻击者（详见 SECURITY.md）
- 英文文本不做文体细分
- 混合文体按优先级取第一个识别结果
- `corpus/` 语料未按文体分层

---

## 版本说明

- `0.x` 阶段：API 与数据表结构可能变动，升级前请备份数据
- `1.0.0` 起：API 契约遵循语义化版本，破坏性变更走 major
