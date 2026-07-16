#!/usr/bin/env bash

set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend"
RUN_DIR="${TMPDIR:-/tmp}/lingjian-agent-dev"
BACKEND_PID_FILE="$RUN_DIR/backend.pid"
FRONTEND_PID_FILE="$RUN_DIR/frontend.pid"
BACKEND_LOG="${TMPDIR:-/tmp}/lingjian-backend.log"
FRONTEND_LOG="${TMPDIR:-/tmp}/lingjian-frontend.log"
BACKEND_PORT=8000
FRONTEND_PORT=3000

usage() {
  cat <<'EOF'
用法: bash dev.sh [命令]

命令:
  start    启动前后端（默认）
  stop     停止本项目的前后端
  restart  重启前后端
  status   查看运行状态
  logs     查看最近日志
  help     显示帮助
EOF
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "缺少命令: $1" >&2
    return 1
  fi
}

port_pids() {
  fuser -n tcp "$1" 2>/dev/null || true
}

port_is_used() {
  fuser -s -n tcp "$1" 2>/dev/null
}

is_project_process() {
  local pid="$1"
  local cwd
  [[ "$pid" =~ ^[0-9]+$ ]] || return 1
  kill -0 "$pid" 2>/dev/null || return 1
  cwd="$(readlink -f "/proc/$pid/cwd" 2>/dev/null || true)"
  [[ "$cwd" == "$ROOT_DIR" || "$cwd" == "$ROOT_DIR/"* ]]
}

read_managed_pid() {
  local pid_file="$1"
  local pid
  [[ -f "$pid_file" ]] || return 1
  pid="$(tr -d '[:space:]' < "$pid_file")"
  if is_project_process "$pid"; then
    printf '%s\n' "$pid"
    return 0
  fi
  rm -f "$pid_file"
  return 1
}

check_existing_service() {
  local name="$1"
  local port="$2"
  local url="$3"
  local pid

  port_is_used "$port" || return 1
  for pid in $(port_pids "$port"); do
    if ! is_project_process "$pid"; then
      echo "$name 无法启动: 端口 $port 被非本项目进程 PID $pid 占用。" >&2
      return 2
    fi
  done

  if curl -fsS --max-time 3 "$url" >/dev/null 2>&1; then
    echo "$name 已在运行，复用端口 $port。"
    return 0
  fi

  echo "$name 端口 $port 已被本项目进程占用，但服务未就绪；请先执行 bash dev.sh stop。" >&2
  return 2
}

wait_for_url() {
  local url="$1"
  local attempts="$2"
  local i
  for ((i = 1; i <= attempts; i++)); do
    if curl -fsS --max-time 3 "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  return 1
}

stop_pid() {
  local pid="$1"
  local managed="$2"
  local pgid

  is_project_process "$pid" || return 0
  pgid="$(ps -o pgid= -p "$pid" 2>/dev/null | tr -d '[:space:]')"
  if [[ "$managed" == "true" && "$pgid" == "$pid" ]]; then
    kill -TERM -- "-$pid" 2>/dev/null || true
  else
    kill -TERM "$pid" 2>/dev/null || true
  fi
}

stop_service() {
  local name="$1"
  local port="$2"
  local pid_file="$3"
  local managed_pid=""
  local pid
  local pids=""
  local i

  managed_pid="$(read_managed_pid "$pid_file" 2>/dev/null || true)"
  [[ -n "$managed_pid" ]] && pids="$managed_pid"

  for pid in $(port_pids "$port"); do
    if ! is_project_process "$pid"; then
      echo "$name 未停止: 端口 $port 包含非本项目进程 PID $pid。" >&2
      return 1
    fi
    case " $pids " in
      *" $pid "*) ;;
      *) pids="$pids $pid" ;;
    esac
  done

  if [[ -z "${pids// /}" ]]; then
    rm -f "$pid_file"
    echo "$name 未运行。"
    return 0
  fi

  for pid in $pids; do
    if [[ "$pid" == "$managed_pid" ]]; then
      stop_pid "$pid" true
    else
      stop_pid "$pid" false
    fi
  done

  for ((i = 1; i <= 15; i++)); do
    if ! port_is_used "$port"; then
      rm -f "$pid_file"
      echo "$name 已停止。"
      return 0
    fi
    sleep 1
  done

  echo "$name 未能在 15 秒内停止，请检查端口 $port。" >&2
  return 1
}

start_backend() {
  local python_bin
  if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
    python_bin="$ROOT_DIR/.venv/bin/python"
  else
    python_bin="$(command -v python3 || true)"
  fi
  if [[ -z "$python_bin" ]]; then
    echo "后端无法启动: 未找到 .venv/bin/python 或 python3。" >&2
    return 1
  fi

  (
    cd "$ROOT_DIR"
    nohup setsid "$python_bin" -m uvicorn app.main:app --app-dir backend \
      --host 0.0.0.0 --port "$BACKEND_PORT" > "$BACKEND_LOG" 2>&1 < /dev/null &
    echo "$!" > "$BACKEND_PID_FILE"
  )

  if wait_for_url "http://127.0.0.1:$BACKEND_PORT/health" 20; then
    echo "后端启动成功: http://localhost:$BACKEND_PORT"
    return 0
  fi

  echo "后端启动失败，最近日志:" >&2
  tail -n 20 "$BACKEND_LOG" >&2 || true
  stop_service "后端" "$BACKEND_PORT" "$BACKEND_PID_FILE" >/dev/null 2>&1 || true
  return 1
}

start_frontend() {
  (
    cd "$FRONTEND_DIR"
    nohup setsid npm run dev -- -p "$FRONTEND_PORT" > "$FRONTEND_LOG" 2>&1 < /dev/null &
    echo "$!" > "$FRONTEND_PID_FILE"
  )

  if wait_for_url "http://127.0.0.1:$FRONTEND_PORT" 30; then
    echo "前端启动成功: http://localhost:$FRONTEND_PORT"
    return 0
  fi

  echo "前端启动失败，最近日志:" >&2
  tail -n 20 "$FRONTEND_LOG" >&2 || true
  stop_service "前端" "$FRONTEND_PORT" "$FRONTEND_PID_FILE" >/dev/null 2>&1 || true
  return 1
}

start_all() {
  local backend_started=false
  local state

  require_command curl || return 1
  require_command fuser || return 1
  require_command setsid || return 1
  require_command npm || return 1
  mkdir -p "$RUN_DIR"

  check_existing_service "后端" "$BACKEND_PORT" "http://127.0.0.1:$BACKEND_PORT/health"
  state=$?
  if [[ $state -eq 1 ]]; then
    start_backend || return 1
    backend_started=true
  elif [[ $state -eq 2 ]]; then
    return 1
  fi

  check_existing_service "前端" "$FRONTEND_PORT" "http://127.0.0.1:$FRONTEND_PORT"
  state=$?
  if [[ $state -eq 1 ]]; then
    if ! start_frontend; then
      if [[ "$backend_started" == "true" ]]; then
        stop_service "后端" "$BACKEND_PORT" "$BACKEND_PID_FILE" >/dev/null 2>&1 || true
      fi
      return 1
    fi
  elif [[ $state -eq 2 ]]; then
    if [[ "$backend_started" == "true" ]]; then
      stop_service "后端" "$BACKEND_PORT" "$BACKEND_PID_FILE" >/dev/null 2>&1 || true
    fi
    return 1
  fi

  echo "灵鉴 Agent 已就绪。"
  echo "后端日志: $BACKEND_LOG"
  echo "前端日志: $FRONTEND_LOG"
}

stop_all() {
  local failed=0
  require_command fuser || return 1
  stop_service "前端" "$FRONTEND_PORT" "$FRONTEND_PID_FILE" || failed=1
  stop_service "后端" "$BACKEND_PORT" "$BACKEND_PID_FILE" || failed=1
  return "$failed"
}

service_status() {
  local name="$1"
  local port="$2"
  local url="$3"
  local pid
  local pids

  pids="$(port_pids "$port")"
  if [[ -z "${pids// /}" ]]; then
    printf '%-6s 已停止（端口 %s）\n' "$name" "$port"
    return 1
  fi

  for pid in $pids; do
    if ! is_project_process "$pid"; then
      printf '%-6s 端口 %s 被其他进程占用（PID %s）\n' "$name" "$port" "$pid"
      return 1
    fi
  done

  if curl -fsS --max-time 3 "$url" >/dev/null 2>&1; then
    printf '%-6s 运行正常（端口 %s，PID %s）\n' "$name" "$port" "$pids"
    return 0
  fi
  printf '%-6s 进程存在但服务异常（端口 %s，PID %s）\n' "$name" "$port" "$pids"
  return 1
}

status_all() {
  local failed=0
  require_command curl || return 1
  require_command fuser || return 1
  service_status "后端" "$BACKEND_PORT" "http://127.0.0.1:$BACKEND_PORT/health" || failed=1
  service_status "前端" "$FRONTEND_PORT" "http://127.0.0.1:$FRONTEND_PORT" || failed=1
  return "$failed"
}

show_logs() {
  echo "===== 后端日志: $BACKEND_LOG ====="
  tail -n 40 "$BACKEND_LOG" 2>/dev/null || echo "暂无后端日志。"
  echo
  echo "===== 前端日志: $FRONTEND_LOG ====="
  tail -n 40 "$FRONTEND_LOG" 2>/dev/null || echo "暂无前端日志。"
}

case "${1:-start}" in
  start)
    start_all
    ;;
  stop)
    stop_all
    ;;
  restart)
    stop_all && start_all
    ;;
  status)
    status_all
    ;;
  logs)
    show_logs
    ;;
  help|-h|--help)
    usage
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
