# Caddy HTTPS 运行说明

浏览器 → Caddy 443 → 前端 127.0.0.1:3000 → 已有 `/api` 转发 → 后端 127.0.0.1:8000。仅增加 HTTPS 入口和必要配置，登录、用户归属、业务流程仍沿用现有实现。不申请域名或公网证书，不新增 Docker、证书页面或账号迁移。

## 切换前

先在原入口保存当前身份 Key（个人中心可复制或下载），并沿用已有数据库、上传目录和私有配置。不要运行 bootstrap、seed、schema 17 迁移或伙伴整理脚本。初始化不生成或替换 `JWT_SECRET_KEY`、`BANFEI_IDENTITY_ENCRYPTION_KEY`，不修改用户、凭据或历史。

核对端口归属：

```bash
bash enablement-dev.sh status
ss -ltnp '( sport = :80 or sport = :443 or sport = :3000 or sport = :8000 )'
```

443 必须空闲；仅启用跳转时才需要 80。脚本拒绝占用冲突，不停止其他服务。前后端继续用 3000/8000；正式入口切换为 443，前后端绑定 loopback。现有 ARM 服务若由 systemd 管理，保留原服务管理方式，检查原启动参数和配置，不同时再启动一套前后端。

## 一次性准备 Caddy

需要 Linux 对应 CPU 的 Caddy 2 可执行文件。WSL 与公网 ARM 均已实测 2.11.4；从 [Caddy 官方发行页](https://github.com/caddyserver/caddy/releases/tag/v2.11.4) 获取 `caddy_2.11.4_linux_amd64.tar.gz` 或 `caddy_2.11.4_linux_arm64.tar.gz`，按同版官方 checksums 文件校验 SHA-256 后提取 `caddy`。可放在已有 `.isolation/tools/caddy`，不覆盖其他服务使用的二进制。现有公网 ARM 使用 `/opt/banfei/tools/caddy`，由应用用户执行；二进制父目录也须允许该用户遍历。

由管理员仅给此二进制低端口监听权限，无须让应用以 root 运行：

```bash
sudo setcap cap_net_bind_service=+ep /绝对路径/caddy
getcap /绝对路径/caddy
```

更换二进制后须重新检查该能力。WSL 本轮已对本项目私有 Caddy 设置；不会自动安装或停止系统 Caddy 服务。内网可离线携带已校验的 ARM64 二进制；`tls internal` 首次签发和续期不需要公网证书服务。

## 共用配置与初始化

在**现有**私有 `.isolation/runtime/dev/environment.json` 增补以下字段，不替换整个文件。其他环境若已有独立私有 JSON 或 dotenv 文件，先设置 `export BANFEI_ENV_FILE=/现有配置的绝对路径`；该文件必须已存在且运行用户可读写。三种环境都调用同一个初始化脚本和 Caddy 模板。

| 配置项 | 值 |
|---|---|
| `BANFEI_HTTPS_ORIGIN` | WSL：`https://实际WSL_IP`；公网 ARM：`https://实际公网IP`；内网 ARM：`https://实际内网IP` |
| `BANFEI_CADDY_BIN` | 已校验 Caddy 可执行文件的绝对路径 |
| `BANFEI_HTTPS_REDIRECT` | `0` 默认关闭 80；`1` 才监听 80 并 308 跳转至配置的 HTTPS 入口 |

三类环境都应配置实际 IP，HTTPS 443，不带路径。IPv6 使用 `https://[实际IPv6]`。访问地址在环境配置中确定，模板不写死 WSL/公网/内网 IP；公网地址有 NAT 时，启动健康检查在本机连接并严格核验配置地址的证书。每次更换地址，应先停本项目 Caddy，再改配置并重新初始化；保留同一个 CA 数据目录。

WSL 使用默认路由网卡的 IPv4 地址，可用 `ip -4 route show default` 确认网卡，再用 `ip -4 addr show dev <网卡名> scope global` 查看实际地址。不要取 loopback 或其他虚拟网卡地址；不要把此处占位文字原样写入配置。若 WSL IP 变化，更新原配置中的 `BANFEI_HTTPS_ORIGIN`，再运行 `init-https` 并重启原前后端/Caddy，使证书和严格 Origin 一致；不自动更换 CA 或迁移账号。

```bash
bash enablement-dev.sh init-https
```

初始化检查端口和 Caddy 配置语法，私密备份有变化的原配置，然后设置：

```text
BANFEI_IDENTITY_ORIGIN=<BANFEI_HTTPS_ORIGIN>
CORS_ORIGINS=<BANFEI_HTTPS_ORIGIN>
NEXT_PUBLIC_API_BASE_URL=/api
BANFEI_API_PROXY_TARGET=http://127.0.0.1:8000
FORWARDED_ALLOW_IPS=127.0.0.1
```

同时更新前端 `.env.local` 和已存在的 `.env.production.local` 中两个 API 配置项，其余内容保留。业务配置、应用密钥、模型绑定不变。前端代理负责同源路径；Caddy 设置转发协议，Uvicorn 仅信任来自 127.0.0.1 的代理头，不接受公网客户端自报协议来放宽鉴权。Origin 仍必须精确匹配，不添加 `*`。

本地首次切换需要让前后端读取新配置（先保存 Key）：

```bash
bash enablement-dev.sh stop
bash enablement-dev.sh start
bash enablement-dev.sh status
```

`start` 启动前后端和已配置的 Caddy，`stop` 停止本项目核对过归属的三组进程。重复 `init-https` 不重置 CA；已运行服务须重启才应用配置变更。仅重启 Caddy 时使用：

```bash
bash enablement-dev.sh https-stop
bash enablement-dev.sh https-start
```

ARM 已有 systemd 前后端时：设置 `BANFEI_ENV_FILE` 后执行相同 `init-https`；让原后端加载更新后的环境（Uvicorn 启用代理头且仅信任 127.0.0.1），让原前端使用同源 `/api`。若原生产构建嵌入了旧 HTTP API 地址，按既有构建流程重新构建并重启原服务，再执行相同 `https-start`；不使用本地 `start` 另起一套进程。生产构建与运行前端不能同时写同一个 `.next`。

09-27 公网 ARM 已执行上述部署。现有路径与维护命令如下，仅用于该主机；新内网环境沿用相同模板，按实际路径配置：

```bash
cd /opt/banfei/app
# 原配置由 banfei 用户持有，权限 0600；仅首次或配置改变时初始化
sudo -u banfei env BANFEI_ENV_FILE=/etc/banfei/runtime.env bash enablement-dev.sh init-https
# 前后端仍由已有 systemd 服务管理
sudo systemctl status banfei-backend banfei-frontend
# Caddy 独立启停；停止使用同一命令末尾换成 https-stop
sudo -u banfei env BANFEI_ENV_FILE=/etc/banfei/runtime.env bash enablement-dev.sh https-start
sudo -u banfei env BANFEI_ENV_FILE=/etc/banfei/runtime.env bash enablement-dev.sh status
```

**尚未新增 Caddy 开机自启服务：主机重启后须在原前后端就绪时手动运行 `https-start`。** 不修改原 systemd 的 `NoNewPrivileges`。切换 release 前先停止本项目 Caddy，并让新 release 的 `.isolation/runtime/caddy` 指向现有 `/var/lib/banfei/caddy`；不要在每个 release 生成新 CA。字体不在 Git 中，须保留 `frontend/public/fonts/huawei-cloud/`，不能把 `fonts` 复制成 `public` 本身；启动后检查两份字体 HTTP 200。

## CA 持久化与 Windows 信任

首次 `https-start` 由 Caddy 生成根 CA、中间 CA 和站点证书；后续 Caddy 运行时自动续期站点证书。模板使用 `skip_install_trust`，不会自动修改客户端或服务器的系统信任。机制见 [Caddy 自动 HTTPS 文档](https://caddyserver.com/docs/automatic-https)。

| 路径（相对项目根目录） | 用途 |
|---|---|
| `.isolation/runtime/caddy/root.crt` | 公开根证书导出文件，可复制给客户端 |
| `.isolation/runtime/caddy/data` | 持久 Caddy 数据，含 CA 私钥，必须保留并私密备份 |
| `.isolation/runtime/caddy/Caddyfile` | 从共用模板生成的本机配置 |
| `.isolation/runtime/caddy/config-before-*` | 配置修改前私有快照，含应用密钥，禁止公开 |
| `.isolation/logs/caddy.log` | 本机 Caddy 日志 |

以上均在 Git 忽略目录中。不要删除数据目录来“修复”证书，也不要复制 `root.key` 给客户端。每个环境独立首次生成 CA，因此连接不同环境需要分别信任其根证书。备份应同时保留原应用配置和数据库，不能只备份证书。

现有公网 ARM 的上述目录通过符号链接持久化到 `/var/lib/banfei/caddy`；可导出的公开根证书是 `/var/lib/banfei/caddy/root.crt`。本轮经 SSH 导出的副本在本地 `.isolation/arm-deploy/20260927/arm-root.crt`，不含私钥；访问 ARM 时应导入此证书，而不是 WSL 根证书。

**没有导入可信根证书，浏览器会告警；能打开页面不代表已正确受信任。** 不通过浏览器“继续访问不安全网站”、`curl -k`、Playwright `ignoreHTTPSErrors` 或修改浏览器安全开关作为验收。

Windows 导入方法：

1. WSL 导出文件在 `\\wsl.localhost\Ubuntu-24.04\home\yuan\project\lingjian-agent-enablement\.isolation\runtime\caddy\root.crt`。也可在 WSL 执行 `wslpath -w "$PWD/.isolation/runtime/caddy/root.crt"` 查询实际路径。ARM 的根证书从对应服务器上述导出位置经可信渠道复制，**只复制 `.crt`**。
2. 把根证书复制到 Windows，例如 `C:\Users\你的用户名\Downloads\banfei-root.crt`。服务器上用 `sha256sum .isolation/runtime/caddy/root.crt`，Windows 用 `Get-FileHash -Algorithm SHA256 "证书路径"` 核对文件摘要一致。
3. 在当前 Windows 用户的 PowerShell 导入（企业策略可能限制此操作）：

   ```powershell
   Import-Certificate -FilePath "C:\Users\你的用户名\Downloads\banfei-root.crt" -CertStoreLocation Cert:\CurrentUser\Root
   ```

4. 重启 Edge/Chrome，访问配置的实际 IP 地址。WSL 也使用 `https://实际WSL_IP`，不再访问 localhost 或 127.0.0.1，证书地址必须与配置一致。确认无证书告警，再验证复制、刷新恢复、双标签页和管理员登录。Firefox 若使用独立证书库，须在其证书设置中导入同一根证书。仅更换站点地址且根 CA 保持不变时，已信任该 CA 的客户端无须重新导入。

本轮没有在 Windows 导入或实测浏览器信任、安全上下文、复制及 Web Locks。WSL 网络转发或企业浏览器策略也应以 Windows 实际访问为准。查看 [WSL 验证记录](validation/HTTPS_VALIDATION_20260926.md) 和 [ARM HTTPS 验证记录](validation/ARM_HTTPS_VALIDATION_20260927.md)。

## 旧身份与历史

同主机仍可发送且服务端验证有效的旧浏览器 Cookie，会复用原用户和凭据，并在 HTTPS 下加上 Secure；不换用户、不换长期 Key。HTTP 与 HTTPS 是不同 Origin，localStorage Token 不会自动迁移；IP/主机名变化也可能使旧 Cookie 无法发送。此时在 `/login?method=key` 输入或导入原 Key，即可恢复原 `users.id` 和历史。

从 localhost 改为 IP 时，原 Cookie 和 Token 不会自动跨主机继承；在新 IP 的 `/login?method=key` 使用原 Key。其他仅协议切换的情况可优先访问 `/login` 恢复已有身份；直接进入 `/` 且没有有效 Cookie 会按原流程创建新身份。已有 Key 可切回原身份，但不会合并用户。旧版不具备有效 Key 的身份不因此获得新 Key；失效/已删除/停用凭据仍按原校验返回错误。遇到无法保留登录态时保留原数据，不能通过清库、重建账号或换应用密钥处理。
