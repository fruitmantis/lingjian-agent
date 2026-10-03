# ARM 两环境独立 HTTP 入口（2026-10-03）

> 本文保存入口隔离切换时的历史状态。当前业务入口已恢复，最终结论见 [脱敏归档](../../../../docs/validation/AGENTARTS_RELEASE_20261003.md)；原 IP/未知 Host 的 404 仍为既有隔离行为。原始运行核验 JSON 与补丁只在本地留存，不随源码提交。

用户已确认两套 Caddy 共用 80、两环境不同时启动。本目录是本次 ARM 实际部署文件和非敏感验收证据；不是自动安装器。未修改模型、认证凭据、数据库或云安全组。

## 当前状态

- AgentArts：`banfei-agentarts-http.service` / `banfei-agentarts-frontend.service` / `banfei-agentarts-backend.service` 已启用自启并运行。
- 原版：`banfei-http.service` / `banfei-frontend.service` / `banfei-backend.service` 已停止并禁用自启；服务定义、原 Caddy 对原前端的 Requires/After 依赖保留。
- 新入口仅 `http://banfei-agentarts.test` 反代 127.0.0.1:3001；`/api` 和 `/api/*` 保持维护 503。原 IP/其他 Host 明确 404，不转发原版。
- 原版 Caddy 恢复原有 `:80 -> 127.0.0.1:3000` 配置，不含 AgentArts 路由。原版启动未实测，按授权保持停机。
- 两套 PostgreSQL（5432、55432）继续运行，SSH 27971 保留；本次不切换数据库服务。

## 文件和隔离

| 项目 | 原版 | AgentArts |
| --- | --- | --- |
| systemd | banfei-http.service | banfei-agentarts-http.service |
| 配置 | /opt/banfei/app/deploy/Caddyfile | /etc/banfei-agentarts-caddy/Caddyfile |
| 运行用户 | banfei | banfei-agentarts-caddy（独立锁定系统账号） |
| 二进制 | /opt/banfei/tools/caddy | /usr/local/lib/banfei-agentarts-caddy/caddy |
| 状态/存储 | /var/lib/banfei-caddy | /var/lib/banfei-agentarts-caddy |
| 缓存 | /var/cache/banfei-caddy | /var/cache/banfei-agentarts-caddy |
| 运行日志 | /var/log/banfei-caddy/runtime.log | /var/log/banfei-agentarts-caddy/runtime.log |
| admin | off，无 2019 监听 | off，无 2019 监听 |

新二进制是已安装可信 Caddy v2.11.4 的逐字节副本，SHA-256 `e1f904038fc11ca897ac5a12fdacfb2a7add02a8720c426d562a37f6fdad2afe`，未下载或升级；未放宽应用目录权限。

`/usr/local/libexec/banfei-environment-preflight` 是只读 ExecCondition，检查另一环境的 Caddy/前端/后端状态及应用端口；Caddy 另查 80 占用。各前后端 `40-environment-isolation.conf` 和原版 Caddy 同名 drop-in 加载此检查，新 Caddy unit 直接引用。检查不会启动/停止任何服务；被拒绝的启动应检查实际 ActiveState，不只看 systemctl 命令退出码。

原版 Caddy drop-in 另外指定独立 HOME/XDG、状态/缓存/日志目录。其目录由 systemd 下次真正启动时创建，本次未启动原版验证。新 Caddy 无 Requires/Wants 指向任一原版服务。双方均关闭 admin 和配置持久化；未开放 TLS 或新网络端口。

## 明确切换命令

在 ARM 的已授权 SSH 终端执行。每步成功并核对状态后再继续；不要使用旧的一键脚本绕过以下完整环境切换。切换不删除数据，也不启停 PostgreSQL。

切回原版：

```sh
sudo systemctl stop banfei-agentarts-http.service banfei-agentarts-frontend.service banfei-agentarts-backend.service
sudo systemctl disable banfei-agentarts-http.service banfei-agentarts-frontend.service banfei-agentarts-backend.service
sudo systemctl enable banfei-backend.service banfei-frontend.service banfei-http.service
sudo systemctl start banfei-backend.service banfei-frontend.service banfei-http.service
sudo systemctl is-active banfei-backend.service banfei-frontend.service banfei-http.service
```

切回 AgentArts：

```sh
sudo systemctl stop banfei-http.service banfei-frontend.service banfei-backend.service
sudo systemctl disable banfei-http.service banfei-frontend.service banfei-backend.service
sudo systemctl enable banfei-agentarts-backend.service banfei-agentarts-frontend.service banfei-agentarts-http.service
sudo systemctl start banfei-agentarts-backend.service banfei-agentarts-frontend.service banfei-agentarts-http.service
sudo systemctl is-active banfei-agentarts-backend.service banfei-agentarts-frontend.service banfei-agentarts-http.service
```

`disable/enable` 同步下次开机选择，不能仅切 80 而让另一环境应用继续运行。AgentArts 的维护 503 配置不会因切换解除，后续云端问题修复后由负责线程单独验证并放行。

## 实际验证与限制

2026-10-03 02:40:30 UTC：两套 Caddy validate、六个 service 的 systemd-analyze verify 通过。daemon-reload 后新入口启动成功；80 属于新 Caddy PID 121967；3000/8000 无监听；3001/8001/55432 仅 localhost；原 PG 5432、SSH 保留。两配置适配结果 admin.disabled=true，仅 HTTP :80；无 443/2019 监听。

新登录页 200，API 503，原 IP/未知 Host 404；本机前后端健康 200。新前端 PID 86759、新后端 113941、新 PG 84992、原 PG 1063、SSH 14117 与切换前一致。原版和重复占用 80 的预检实际拒绝；AgentArts 应用预检通过。未为验证启动原版，未发模型请求。

首次尝试因 Caddy 未匹配 Host 默认返回空白 200，而预期为 404，自动回退到原共享入口；添加明确的 404 兜底后完成第二次切换。未影响应用或数据库进程。

ARM 备份和审查证据：`/root/banfei-agentarts-deploy-20261002/caddy-isolation/`。`backup-0` 是拆分前共享 Caddyfile；`manifest.json`、`before.json`、`change.patch`、`preparation.json`、`cutover-verification.json`、`isolation-verification.json` 和首次 `rollback.json` 保存实际过程。本目录随源码保留配置模板；补丁和两份运行核验副本留在操作者本地，不随源码提交。

云业务两条流程仍在第二阶段失败，另一线程处理安全诊断；此次 Caddy 拆分通过不代表云业务验收通过。没有 commit/push。
