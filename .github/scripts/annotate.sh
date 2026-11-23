#!/usr/bin/env bash
# 把一条命令的失败输出转成 GitHub Actions annotation。
#
# 为什么需要这个：本仓库的 GITHUB_TOKEN 没有 admin 权限，
#   GET /repos/{owner}/{repo}/actions/jobs/{job_id}/logs 恒返回
#   403 "Must have admin rights to Repository."，
# 而 check-runs 的 output.title/summary/text 对这些 action 全是空的。
# 结果是 CI 红了却看不到任何报错文本，只能靠 job/step 粒度猜。
# annotation 是唯一一条对无 admin 权限也开放的通道（check-runs annotations API）。
#
# 用法：annotate.sh <描述> <命令...>
#   例：annotate.sh "uv sync --frozen" uv sync --frozen
#
# 只挑有诊断价值的行发出去：进度条/下载行会把 annotation 额度占满
# （单条 64KB、单个 check-run 有总量上限），所以先发 error/cause/hint 行，
# 再补末尾 30 行兜底，并附上环境指纹。
set -uo pipefail

label="${1:?用法: annotate.sh <描述> <命令...>}"
shift

log="$(mktemp)"
set +e
"$@" >"$log" 2>&1
code=$?
set -e

cat "$log"

if [ "$code" -ne 0 ]; then
  echo "::error::${label} 失败（exit ${code}）"
  echo "::error::--- env ---"
  echo "::error::uv=$(uv --version 2>&1) | python=$(python -V 2>&1) | cwd=$(pwd)"
  echo "::error::VIRTUAL_ENV=${VIRTUAL_ENV:-unset} UV_PROJECT_ENVIRONMENT=${UV_PROJECT_ENVIRONMENT:-unset}"
  echo "::error::--- 错误行 ---"
  grep -nE '(^|[[:space:]])(error|Error|ERROR|cause|hint|No solution|failed):' "$log" \
    | tail -40 | while IFS= read -r line; do echo "::error::${line}"; done
  echo "::error::--- 末 30 行 ---"
  tail -30 "$log" | while IFS= read -r line; do echo "::error::${line}"; done
fi

rm -f "$log"
exit "$code"
