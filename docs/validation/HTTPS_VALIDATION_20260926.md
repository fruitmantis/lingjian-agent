# Caddy HTTPS 定向验证（2026-09-26）

> 后续状态（09-27）：应用改动已提交为 `ba14e03` 并推送；随后按用户授权部署公网 ARM，见 [ARM HTTPS 验证](ARM_HTTPS_VALIDATION_20260927.md)。以下“未部署”只描述此前 WSL 实施阶段，Windows 与内网 ARM 仍未实测。

实施基线 `6de96bd382c89e38ad09560cbe3c58ea735642a2`，正式工作区 `main`。实施时未 commit、push；09-27 用户随后授权更新文档并提交、推送，最终状态以实时 Git 为准，未部署远端。初始化与证书说明见 [HTTPS 运行说明](../HTTP_SETUP.md)。

## 2026-09-27 补充：WSL 改用实际 IP

- 按用户要求停用 localhost 浏览器入口，原私有配置仅变更 `BANFEI_HTTPS_ORIGIN`、`BANFEI_IDENTITY_ORIGIN`、`CORS_ORIGINS` 为默认路由网卡的实际 IP HTTPS 地址。复用原初始化、启停脚本，无登录或业务代码改动，保留全部既有未提交改动。
- 实际 IP 的 443 `/api/health` 与 `/login?method=key` 均通过原 CA 严格验证并返回 200，3000/8000 保持 loopback 内部服务，80 关闭。原根证书和根私钥摘要一致，运行库 35 张表及应用密钥前后摘要一致。
- 仅选 3 项 WSL Chromium 隔离验证，全部通过：实际 IP HTTPS 首次进入/复制/下载/刷新；原 localhost 身份 Key 在新 IP 登录并恢复同一用户、Key 和历史；管理员登录与会话隔离。补充检查安全上下文、Clipboard/Web Locks、Secure Cookie、错误 Origin 拒绝及转发协议。测试 CA 显式临时信任，未忽略证书错误；只使用专用 PostgreSQL 临时 schema 和独立前端目录，未调用模型。
- Windows curl 使用原导出根证书访问实际 IP 时，Schannel 返回 `the revocation status is unknown`（退出码 60）。未关闭证书或吊销校验；这项 Windows TLS 检查没有通过，不能作为 Windows 浏览器已受信任的证据。未导入 Windows 系统信任，也未实测 Windows 浏览器；导入步骤仍见运行说明。
- 配置备份、前后对账和隔离测试输出索引保存在私有 `.isolation/https-ip-20260927/`。ARM 本轮未连接/部署；无 commit 或 push。以下 09-26 结果保留为此前 localhost 阶段记录。

## 修改与数据范围

- 共用 `deploy/Caddyfile`，`tls internal`，浏览器 443，80 跳转可选且默认关闭。既有脚本增加 HTTPS 初始化和独立启停，保留前端 3000、后端 8000。
- 复用既有 `/api`，严格匹配 HTTPS Origin；仅信任 loopback 代理。原 Cookie 经服务端验证后复用并升级 Secure，未重构鉴权或业务模块。
- 原运行库 35 张表排序内容摘要、应用签名/加密密钥摘要前后相同。无清库、seed、账号重建、Key 轮换、业务写入或模型调用；schema 17 和伙伴整理不重跑。
- 测试仅用本机专用 PostgreSQL 的临时 schema；前后端 13000/18000、HTTPS 8443 和独立前端 `.next`，不占用正式 3000/8000。测试后停止自有进程、删除临时 schema、移除临时证书信任。

## 实际通过

| 项目 | 结果与边界 |
|---|---|
| HTTPS 配置定向单元测试 | 4 项：三类地址、端口冲突拒绝、dotenv 保留原配置、重复初始化保留应用密钥与 CA |
| 现有 PostgreSQL 身份定向测试 | 4 项：首次创建、Key 恢复、退出、HTTP Cookie 经 HTTPS 恢复原用户/原 Key；错误 Origin 拒绝 |
| 真实 HTTPS 浏览器 | WSL Chromium 7 项通过；临时根 CA 显式加入该测试环境信任，`ignoreHTTPSErrors=false`，无忽略证书错误参数；API 客户端也验证同一根 CA |
| 浏览器覆盖 | 首次进入、Key 实际复制和下载、刷新恢复、已有 Key 登录及历史归属、退出/重开恢复、双标签页只创建同一身份及退出同步、管理员登录和会话隔离、普通用户归属隔离 |
| HTTPS 专项浏览器覆盖 | 先在隔离 HTTP 后端创建旧身份和历史，切换 HTTPS 后复用原 Cookie、用户 ID、Key 和历史；Cookie Secure/HttpOnly/SameSite=Strict；安全上下文、Clipboard 和 Web Locks 可用；错误 Origin 403；伪造转发协议仍识别为 HTTPS |
| 实际 WSL 443 | 使用导出根证书严格验证 `https://localhost/api/health` 返回 200；3000/8000 保持运行，80 未启用 |
| CA 持久化 | 重复初始化、实际停止/启动 Caddy 后根 CA 指纹不变，前后端进程未因 Caddy 单独重启而更换 |
| IP / NAT 场景 | 在本机临时 9443 用示例公网/内网 IP 配置，按对应 IP 严格验证 SAN 和证书链，未发送 DNS SNI 也成功；切换地址后原 CA 保留。没有连接这些示例 IP，不是 ARM 实机验证 |
| 静态检查 | 前端 TypeScript 检查、Python 配置检查和 `git diff --check` |

配置测试入口：`.venv/bin/python -m unittest discover -s scripts/tests -p test_https_runtime.py -v`。身份用例复用 `backend/tests/test_local_identity.py` 和 `frontend/e2e/local-identity.spec.ts`，补充 `frontend/e2e/https-identity.spec.ts`。

HTTPS 浏览器用例须使用隔离 PostgreSQL、独立构建目录和测试服务；通过 `PLAYWRIGHT_HTTPS_ORIGIN` 指向隔离 HTTPS，`PLAYWRIGHT_HTTPS_FIXTURE` 指向私有旧身份夹具。该专项用例依赖仅测试服务中的协议探针，正式应用没有该探针。当前临时测试启动器、前后对账摘要和结果位置索引在私有 `.isolation/https-validation/`，用例输出在 `/tmp/banfei-https-validation-*`；其中包含合成凭据，不提交 Git，不指向正式运行库执行。

## 未确认事项

- Windows 未导入根证书，也未实测 Windows 浏览器安全上下文、Key 复制或 Web Locks；WSL Chromium 成功不代表 Windows 自动信任。
- 公网 ARM、内网 ARM 本轮未连接、未部署、未实机验证。只提供相同脚本和配置模板；此前 ARM 业务兼容结果不能代替 HTTPS 验证。
- 未实际等待证书到期；续期使用 Caddy 原生机制，已验证持久 CA 不因重复初始化/重启更换。
- 运行库只读对账，没有使用真实用户凭据登录；旧身份恢复通过隔离数据实测，不声称每个现有浏览器都能无感迁移。
