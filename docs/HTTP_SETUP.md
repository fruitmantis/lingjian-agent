# 伴飞 HTTP 80 运行说明

伴飞自有入口固定为 `http://实际服务器IP`，本机也可用 `http://localhost`。Caddy 只监听 80，转发到回环地址 127.0.0.1:3000；Next.js 的同源 `/api` 转发到回环地址 127.0.0.1:8000。没有证书初始化、443 监听或协议跳转。

在现有私有环境文件（WSL 为 `.isolation/runtime/dev/environment.json`；ARM 使用 `BANFEI_ENV_FILE` 指定的既有文件）填写 `BANFEI_IDENTITY_ORIGIN=http://实际IP,http://localhost`。不需本机访问时可省略 localhost。`init` 规范化默认端口 80，设置同值 `CORS_ORIGINS`，并更新同源 API 配置；不会重建数据库、用户或应用密钥。`BANFEI_CADDY_BIN` 继续指向已安装的 Caddy。前端 `.env.local` 及已存在的 `.env.production.local` 由初始化同步为 `/api` 和回环后端地址。

```bash
bash enablement-dev.sh status
bash enablement-dev.sh stop
# 修改既有私有配置中的 BANFEI_IDENTITY_ORIGIN，再执行：
bash enablement-dev.sh init
bash enablement-dev.sh start
bash enablement-dev.sh status
```

WSL 的实际 IP 从默认路由网卡核对；地址变更前先保存原身份 Key。旧站点的 Cookie/Token 不跨协议迁移，在新地址 `/login?method=key` 输入原 Key 即可回到原用户和历史；不清库、不重新 seed。实际 IP 与 localhost 是不同站点，会话不共享。浏览器身份 Cookie 为 HttpOnly/SameSite=Strict、非 Secure。身份和管理接口仍严格核对 Origin、Token、所有权和角色。

ARM 更新仅在获得部署授权后执行。本轮不连接 ARM：先保留并备份现有应用密钥、数据库、上传和字体目录，核对 80/443 端口及旧服务归属；停止旧 Caddy 入口。保留原 `banfei-backend.service`、`banfei-frontend.service`，确认两者仍只监听 127.0.0.1:8000/3000 且前端使用同源 `/api`。将 `deploy/banfei-http.service` 按既有 `/opt/banfei/app`、`/opt/banfei/tools/caddy` 路径安装为 `banfei-http.service`（路径不同时按实际位置调整），`systemctl daemon-reload`。在 ARM 原私有配置中设实际公网或内网 IP 的 HTTP 地址、`BANFEI_RUNTIME_MANAGER=systemd`，删除旧入口配置；以 root 和 `BANFEI_ENV_FILE` 调用同一 `init|start|stop|status` 命令。`start` 只启动这三个指定 systemd 单元，`stop` 只停止这三个；切换前确认旧 443 监听已退出。切换后从实际 IP 验证页面、`/api/health`、身份 Key 与管理登录，再单独清理确认只属于伴飞的旧证书和 CA 目录。不要清理数据库、上传、其他服务或系统通用证书库。

本机验证顺序：先 `ss -ltnp` 确认 80 对外、443 无监听且 3000/8000 仅回环；再用实际 IP 检查页面、静态文件和 `/api/health` 均直接返回、无旧协议跳转。构建、开发服务与 Playwright 不得同时写同一 `.next`；浏览器测试使用隔离数据，不调用付费业务模型。
