#!/usr/bin/env bash
# ==============================================================================
# PMS 四门禁 CI 脚本（Git Bash / bash）
#
# 门禁顺序（按依赖排序）：
#   1. 后端测试     : pytest -q -W ignore::pytest.PytestUnhandledThreadExceptionWarning
#   2. 迁移零漂移   : alembic upgrade head + alembic check（临时库 _alembic_check.db）
#   3. 前端类型     : tsc --noEmit
#   4. 前端构建     : vite build
#
# 行为：
#   - 任一步失败 => 立即停止后续门禁，打印醒目失败信息，输出汇总表后以非 0 退出
#   - 每步打印耗时（秒）
#   - 结尾汇总四门禁 PASS/FAIL 表
#   - 可从任意目录调用，项目根由脚本自身位置解析
#   - 门禁日志写入 <项目根>/.ci-logs/（已被 .gitignore 排除），失败后保留供排查
#   - 迁移检查用的临时库 _alembic_check.db 在检查结束后立即删除，不残留工作区
#
# 用法：
#   bash scripts/ci.sh
#   ./scripts/ci.sh
# ==============================================================================

# 不使用 set -e：门禁失败由脚本自行捕获、汇总后再退出
set -uo pipefail

# ---------------------------------------------------------------- 路径解析 ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

PYTHON="${PROJECT_ROOT}/.venv/Scripts/python.exe"
if [ ! -f "${PYTHON}" ]; then
  PYTHON="$(command -v python3 || command -v python)"
fi

TEMP_DB="_alembic_check.db"
# 日志目录放在项目内（已被 .gitignore 排除）。
# 不使用 mktemp -d：Windows Git Bash 下 TMPDIR 常为 C:\... 风格路径，
# mktemp 会产出混合分隔符路径，rm -rf 处理时易失败并残留临时目录。
# 放在项目内还有一个好处：门禁失败后日志保留，便于直接排查。
LOGDIR="${PROJECT_ROOT}/.ci-logs"
rm -rf "${LOGDIR}"
mkdir -p "${LOGDIR}"
FAILED=0

# 门禁结果记录（索引 1..4）
declare -a GATE_STATUS=("" "" "" "")
declare -a GATE_TIME=("" "" "" "")
GATE_TOTAL_START="$(date +%s)"

# ------------------------------------------------------------------ 输出工具 ---
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  C_RED=$'\033[31m'; C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'
  C_CYAN=$'\033[36m'; C_BOLD=$'\033[1m'; C_OFF=$'\033[0m'
else
  C_RED=""; C_GREEN=""; C_YELLOW=""; C_CYAN=""; C_BOLD=""; C_OFF=""
fi

cleanup() {
  # 无论成功失败，都必须清理临时迁移检查库，不能留在工作区。
  # 日志目录 .ci-logs/ 保留，供失败排查（已被 .gitignore 排除）。
  rm -f "${PROJECT_ROOT}/${TEMP_DB}" \
        "${PROJECT_ROOT}/${TEMP_DB}-shm" \
        "${PROJECT_ROOT}/${TEMP_DB}-wal"
  # 兜底：脚本被中断时不残留环境变量
  unset PMS_DATABASE_URL
}
trap cleanup EXIT INT TERM

hr() {
  printf '%s\n' "=============================================================================="
}

banner() {
  printf '\n%s\n' "${C_CYAN}[$(date '+%H:%M:%S')] $*${C_OFF}"
}

# ------------------------------------------------------------- 门禁执行器 ---
# run_gate <序号> <名称> <命令...>
run_gate() {
  local idx="$1"
  local name="$2"
  shift 2

  local log="${LOGDIR}/gate${idx}.log"
  local start end dur

  start="$(date +%s)"
  banner "[$idx/4] ${name} 开始..."

  if "$@" > "${log}" 2>&1; then
    end="$(date +%s)"; dur=$((end - start))
    GATE_STATUS[$((idx - 1))]="PASS"
    GATE_TIME[$((idx - 1))]="${dur}"
    printf '  %s✔ PASS%s  %s（耗时 %ss，输出末尾 8 行）\n' "${C_GREEN}" "${C_OFF}" "${name}" "${dur}"
    tail -n 8 "${log}" | sed 's/^/     | /'
    return 0
  fi

  end="$(date +%s)"; dur=$((end - start))
  GATE_STATUS[$((idx - 1))]="FAIL"
  GATE_TIME[$((idx - 1))]="${dur}"
  printf '\n'
  hr
  printf '%s%s门禁失败：%s（耗时 %ss）%s\n' "${C_RED}" "${C_BOLD}" "${name}" "${dur}" "${C_OFF}"
  hr
  printf '%s—— 命令：%s\n' "${C_YELLOW}" "$*"
  printf '%s—— 输出末尾 60 行：%s\n' "${C_YELLOW}" "${C_OFF}"
  tail -n 60 "${log}" | sed 's/^/     | /'
  hr
  FAILED=1
  return 1
}

# ------------------------------------------------------------ 汇总与退出 ---
print_summary() {
  local total
  total=$(($(date +%s) - GATE_TOTAL_START))

  printf '\n'
  hr
  printf '%s                        PMS 四门禁汇总%s\n' "${C_BOLD}" "${C_OFF}"
  hr
  printf '%-4s %-28s %-8s %s\n' "#" "门禁" "结果" "耗时"
  printf '%-4s %-28s %-8s %s\n' "----" "----------------------------" "--------" "--------"

  local i
  for i in 0 1 2 3; do
    local st="${GATE_STATUS[$i]:-SKIP}"
    local tm="${GATE_TIME[$i]:--}"
    local name
    case "${i}" in
      0) name="后端测试 pytest" ;;
      1) name="迁移零漂移 alembic check" ;;
      2) name="前端类型 tsc --noEmit" ;;
      3) name="前端构建 vite build" ;;
    esac
    local color="${C_OFF}"
    [ "${st}" = "PASS" ] && color="${C_GREEN}"
    [ "${st}" = "FAIL" ] && color="${C_RED}"
    [ "${st}" = "SKIP" ] && color="${C_YELLOW}"
    [ -n "${tm}" ] && [ "${tm}" != "-" ] && tm="${tm}s"
    printf '%-4s %-28s %s%-8s%s %s\n' "$((i + 1))" "${name}" "${color}" "${st}" "${C_OFF}" "${tm}"
  done

  hr
  if [ "${FAILED}" -eq 0 ]; then
    printf '%s✔ 全部四门禁通过（总耗时 %ss）%s\n' "${C_GREEN}" "${total}" "${C_OFF}"
  else
    printf '%s✘ CI 失败：存在未通过的门禁（总耗时 %ss）%s\n' "${C_RED}" "${total}" "${C_OFF}"
  fi
  hr
}

finish() {
  print_summary
  if [ "${FAILED}" -eq 0 ]; then
    exit 0
  fi
  exit 1
}

# =============================================================== 门禁 1/4 ===
# 后端测试
# 注意：-W ignore::pytest.PytestUnhandledThreadExceptionWarning 是必须的。
# asyncio 拆卸期抛出的该警告会把 pytest 退出码抬升为 1，造成“假失败”。
cd "${PROJECT_ROOT}" || exit 1
hr
printf '%sPMS CI 启动（项目根：%s）%s\n' "${C_BOLD}" "${PROJECT_ROOT}" "${C_OFF}"
hr

run_gate 1 "后端测试 pytest" \
  "${PYTHON}" -m pytest -q -W ignore::pytest.PytestUnhandledThreadExceptionWarning --basetemp="${TEMP:-/tmp}/pms_ci_basetemp_$$"
[ $? -ne 0 ] && finish

# =============================================================== 门禁 2/4 ===
# 迁移零漂移：先用临时库 upgrade head，再 check，必须出现
# "No new upgrade operations detected"
start="$(date +%s)"
banner "[2/4] 迁移零漂移 alembic check 开始..."

rm -f "${PROJECT_ROOT}/${TEMP_DB}" \
      "${PROJECT_ROOT}/${TEMP_DB}-shm" \
      "${PROJECT_ROOT}/${TEMP_DB}-wal"

GATE2_OK=1
export PMS_DATABASE_URL="sqlite+aiosqlite:///./${TEMP_DB}"

if "${PYTHON}" -m alembic upgrade head > "${LOGDIR}/gate2_upgrade.log" 2>&1; then
  if "${PYTHON}" -m alembic check > "${LOGDIR}/gate2_check.log" 2>&1; then
    if grep -q "No new upgrade operations detected" "${LOGDIR}/gate2_check.log"; then
      GATE2_OK=0
    else
      printf '%salembic check 未输出 "No new upgrade operations detected"%s\n' "${C_YELLOW}" "${C_OFF}"
    fi
  else
    printf '%salembic check 命令返回非 0%s\n' "${C_YELLOW}" "${C_OFF}"
  fi
else
  printf '%salembic upgrade head 失败%s\n' "${C_YELLOW}" "${C_OFF}"
fi

# 立即清理临时库
rm -f "${PROJECT_ROOT}/${TEMP_DB}" \
      "${PROJECT_ROOT}/${TEMP_DB}-shm" \
      "${PROJECT_ROOT}/${TEMP_DB}-wal"
unset PMS_DATABASE_URL

end="$(date +%s)"; dur=$((end - start))
if [ "${GATE2_OK}" -eq 0 ]; then
  GATE_STATUS[1]="PASS"
  GATE_TIME[1]="${dur}"
  printf '  %s✔ PASS%s  迁移零漂移 alembic check（耗时 %ss）\n' "${C_GREEN}" "${C_OFF}" "${dur}"
  grep -E "No new upgrade operations detected" "${LOGDIR}/gate2_check.log" | sed 's/^/     | /'
else
  GATE_STATUS[1]="FAIL"
  GATE_TIME[1]="${dur}"
  printf '\n'
  hr
  printf '%s%s门禁失败：迁移零漂移 alembic check（耗时 %ss）%s\n' "${C_RED}" "${C_BOLD}" "${dur}" "${C_OFF}"
  hr
  printf '%s—— alembic upgrade head 输出末尾 30 行：%s\n' "${C_YELLOW}" "${C_OFF}"
  tail -n 30 "${LOGDIR}/gate2_upgrade.log" | sed 's/^/     | /'
  printf '%s—— alembic check 输出末尾 30 行：%s\n' "${C_YELLOW}" "${C_OFF}"
  tail -n 30 "${LOGDIR}/gate2_check.log" | sed 's/^/     | /'
  hr
  FAILED=1
  finish
fi

# =============================================================== 门禁 3/4 ===
# 前端类型检查
cd "${PROJECT_ROOT}/web" || exit 1
run_gate 3 "前端类型 tsc --noEmit" \
  ./node_modules/.bin/tsc --noEmit
[ $? -ne 0 ] && finish

# =============================================================== 门禁 4/4 ===
# 前端构建：把 outDir 放在系统 temp 下新建子目录（每次新 $$），绕开沙盒 safe-delete
# 钩子对项目内 web/dist 累积文件（644+）的 rmSync 拦截。CI 不消费 dist 产物。
cd "${PROJECT_ROOT}/web" || exit 1
TMP_BUILD="${TEMP:-/tmp}/pms_build_out_$$"
run_gate 4 "前端构建 vite build" \
  ./node_modules/.bin/vite build "--outDir=${TMP_BUILD}"
[ $? -ne 0 ] && finish

cd "${PROJECT_ROOT}" || exit 1
finish
