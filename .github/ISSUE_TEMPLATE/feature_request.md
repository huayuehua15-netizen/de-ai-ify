---
name: 功能建议
about: 提议新功能或改进
title: "[feat] "
labels: enhancement
---

## 想解决什么问题

<!-- 描述痛点，而不是直接说方案。例如："改写到一半想对比多个版本，现在只能一个个点开" -->

## 建议的方案

<!-- 你设想的实现方式 -->

## 有没有替代方案

<!-- 你考虑过的其他做法 -->

## 影响面

- [ ] 评分引擎（`engine/`）
- [ ] 改写管线（`providers/`、`services/rewrite.py`）
- [ ] API 契约（`api/schemas.py`）
- [ ] Web 界面（`apps/web/`）
- [ ] 部署/配置
- [ ] 文档

## 是否符合 v1 范围

请先看 [docs/DEVELOPMENT.md §17.3 非目标](../docs/DEVELOPMENT.md)。以下明确不在 v1 范围：
多租户 SaaS、浏览器扩展、LLM 版判别器、翻译纠错、平台 Skill 形态。
