#!/usr/bin/env bash
# 灵鉴 Agent 一键启动（在终端运行：bash dev.sh）
set -u
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 清理可能残留的旧进程（按端口，避免误杀自身）
fuser -k 8000/tcp 3000/tcp 2>/dev/null || true
sleep 1

# 激活虚拟环境（若存在）
if [ -f .venv/bin/activate ]; then source .venv/bin/activate; fi

# 后端：后台运行
nohup python -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000 \
  > /tmp/lingjian-backend.log 2>&1 &
echo "后端已启动 (PID $!)，日志: /tmp/lingjian-backend.log"

# 等后端就绪
for i in $(seq 1 15); do
  if curl -s http://localhost:8000/health >/dev/null 2>&1; then
    echo "后端健康检查 OK"; break
  fi
  sleep 1
done
curl -s http://localhost:8000/health; echo

# 前端：前台运行（Ctrl+C 只停前端；停后端用 fuser -k 8000/tcp）
echo "启动前端... 浏览器打开 http://localhost:3000 ，登录 admin / admin123"
cd frontend
exec npm run dev
