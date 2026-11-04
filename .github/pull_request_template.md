## 动机

<!-- 解决了什么问题？关联 Issue：closes # -->

## 改动

<!-- 改了什么、为什么这么改 -->

## 验证

<!-- 贴命令输出或截图 -->

```powershell
pnpm lint
pnpm test
pnpm --filter web exec tsc --noEmit
pnpm --filter web test
```

- [ ] 以上四项全绿

## 影响面

- [ ] 评分结果有变化（**必须**附 corpus 回归结果）
- [ ] API 契约有变化
- [ ] 需要更新 `docs/DEVELOPMENT.md`
- [ ] 需要更新 `CHANGELOG.md`
- [ ] 纯文档/杂务，无功能影响

## 检查清单

- [ ] 提交信息符合 Conventional Commits
- [ ] 新增代码有对应测试
- [ ] 没有提交 `.env`、`.deaiify-secret` 等敏感文件
- [ ] 没有顺手夹带无关改动
