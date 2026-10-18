#!/usr/bin/env bash
# 紧急止血脚本 —— 平台预设（内置）模型不可用
#
# 背景：08fb2e5 把章节生成搬到了后台线程，标准库 ThreadPoolExecutor 不继承请求
# 上下文，工作线程里拿不到 request_identity（用户身份 + access_token），平台预设
# 模型这条带积分计量的链路在云端模式下会抛 PermissionError，最终对外表现为 500。
# 代码修复见 server/app.py 中 generate_section / create_section_job 的 job_context。
#
# 用法：
#   scripts/emergency_preset_hotfix.sh check              # 本地自检：语法 + 相关单测
#   scripts/emergency_preset_hotfix.sh verify [URL]       # 线上冒烟：预设模型是否已恢复
#   scripts/emergency_preset_hotfix.sh rollback [SHA]     # 回滚事故提交（默认 08fb2e5）
#
# 依赖：python3；verify 需要 curl；rollback 需要 git。

set -euo pipefail

PROD_URL="${PROD_URL:-https://agent.stardust.website}"
FIX_COMMIT="08fb2e5"

cd "$(dirname "$0")/.."

cmd_check() {
  echo "==> 语法检查 server/app.py"
  python3 -c "import ast; ast.parse(open('server/app.py').read()); print('  syntax OK')"
  echo "==> 跑相关单测"
  python3 -m pytest \
    tests/test_server_jobs_api.py \
    tests/test_generation_jobs.py \
    tests/test_workbench_metering.py \
    tests/test_server.py -q
  echo "==> 自检通过"
}

cmd_verify() {
  local url="${1:-$PROD_URL}"
  echo "==> 冒烟 $url"
  local cfg preset
  cfg="$(curl -fsS "$url/api/config" || true)"
  preset="$(curl -fsS "$url/api/models/preset" || true)"

  python3 - "$cfg" "$preset" <<'PY'
import json, sys
cfg_raw, preset_raw = sys.argv[1], sys.argv[2]
ok = True
try:
    cfg = json.loads(cfg_raw)
    enabled = cfg.get("preset_enabled")
    print(f"  /api/config  preset_enabled = {enabled}")
    ok = ok and enabled is True
except Exception as exc:
    print(f"  /api/config 解析失败: {exc}")
    ok = False
try:
    data = json.loads(preset_raw)
    models = data.get("models") or []
    print(f"  /api/models/preset  可用内置模型数 = {len(models)}")
    ok = ok and len(models) > 0
except Exception as exc:
    print(f"  /api/models/preset 解析失败: {exc}")
    ok = False
print("==> 结论:", "预设模型已恢复 ✅" if ok else "预设模型仍不可用 ❌")
sys.exit(0 if ok else 1)
PY
}

cmd_rollback() {
  local target="${1:-$FIX_COMMIT}"
  echo "==> 准备回滚 $target（会新建一个 revert 提交）"
  echo "    注意：如果后续提交动过同一批文件，revert 可能冲突，需要手动解决。"
  read -r -p "确认继续？输入 yes 继续：" ans
  [ "$ans" = "yes" ] || { echo "已取消"; exit 1; }
  git revert --no-edit "$target"
  echo "==> 已生成回滚提交。推送 main 会触发 Vercel 重新部署："
  echo "    git push origin HEAD:main"
}

case "${1:-}" in
  check)    cmd_check ;;
  verify)   cmd_verify "${2:-}" ;;
  rollback) cmd_rollback "${2:-}" ;;
  *) sed -n '2,20p' "$0"; exit 1 ;;
esac
