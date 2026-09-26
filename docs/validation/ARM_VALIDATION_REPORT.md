# 2026-09-26 ARM 增量部署与兼容验证

本轮已获代码提交、普通推送和 ARM 部署授权。应用基线为 `e192810`，最小兼容适配为 `8113f89`、`6c938f4`；服务已切换到这批代码。**公网普通身份登录尚未验收完成：原入口为 HTTP，新身份登录要求 HTTPS；新增 HTTPS 基础设施被自动审批拦截，正在等待明确授权或已有域名/证书信息。** 不应把以下通过数字解读为完整上线验收。

主机地址、账号、凭据、业务清单、原始材料和私有运维证据不进入 Git。

## 修改与部署范围

- Ubuntu 24.04 ARM64、Node.js 22、Python 3.12、PostgreSQL 16；复用既有 Next.js / FastAPI / SQLAlchemy 架构。
- 七个已有升级/初始化 CLI 增加 `--database-name`，默认仍为本机 `banfei_agent`。显式目标必须匹配私有连接串，且只允许 localhost / 127.0.0.1 PostgreSQL；迁移内容和初始化逻辑未修改。
- Excel 页面测试夹具兼容既有 `/api` 同源代理；已有超时兼容用例补充能力发展 conversation。没有改业务接口、流程、权限、模型选择、有效性校验或重试逻辑。
- ARM 按既有迁移顺序从 schema 12 升至 17，先在专用验证库临时 schema 演练，再停远端服务完整备份、执行升级、核验后启动。分类仅在缺失时初始化；已有分类不重置。
- 保留旧部署目录、旧虚拟环境、数据库与上传备份。回退须在独立库核验备份后人工切换，禁止旧代码直接读取新 schema 或覆盖恢复当前业务库。
- 为当前资料转换安装 LibreOffice Writer/Impress 与中文字体；使用 ARM Python wheels 和 ARM GNU SWC。既有锁定依赖版本保留，新资料/身份相关依赖按已验证版本安装。没有全系统升级。
- 沿用 `/api` 同源代理及单 worker 构建。身份加密 Key 生成后仅存私有运行配置并备份；追加错误记录使用持久私有日志目录；原有七个模型场景配置可读取且保持原值，不调用供应商。
- 首轮实际页面检查发现两份不进入 Git 的字体文件缺失；按现有字体清单补齐并核对 SHA-256，仅重启 ARM 前端后复验。字体二进制仍不提交。

## 实际验证

| 检查 | 结果与边界 |
|---|---|
| 数据库目标防护 | 21 项 CLI 拒绝检查通过；错误目标在访问数据库前退出 |
| ARM 原生依赖 | psycopg、bcrypt、uvloop、lxml、Pillow、cryptography、openpyxl、Next SWC 加载通过 |
| ARM 前端 | typecheck、production build 通过；构建目录与本地开发服务独立 |
| ARM 后端定向回归 | **108 passed**；专用验证库临时 schema，上传和诊断夹具仅在 `/tmp` |
| 前端纯兼容用例 | **3 passed**，HTTP UUID fallback、代理/直连超时、可选配置 |
| ARM 页面合成接口回归 | **17 passed**，三类错误/重试与 Excel 维护；接口响应为合成夹具，无运行库写入 |
| 部署后接口 | **15 项只读检查通过**，其中含伙伴/课程实验的 4 个 Excel 导出与空模板；另 3 项无认证访问返回 401 |
| 部署后实际后台页面 | 字体补齐后 **14 项页面/分辨率检查通过**（7 页 × 1366×768、1920×1080），无 JS 错误、HTTP 错误或整页横向溢出；拦截写请求，实际 0 次写请求 |
| 数据与文件对账 | 迁移前原业务字段摘要与升级/页面验证后对账通过；原件哈希一致。新增字段、配置和既有迁移明确移除的旧案例共享表按原迁移规则处理 |
| 本地环境 | main 的 3000/8000 保持运行；没有重跑本地 schema 17 迁移、伙伴整理或官网能力补充 |

后端覆盖 Excel 导入导出/模板/批量发布权限、六类资料提取及实际 Office 预览转换、原文件归类、身份 Key 与退出/删除、Scope Gate、能力发展 current/幂等/失败保留旧结果、真实错误记录与脱敏。存在一条既有 PyPDF2 弃用警告，没有测试失败。不把这些定向验证描述为全量 E2E 或真实模型业务验收。

## 尚未完成

- ARM 原公网 HTTP 入口不能承载新版普通身份登录。未降低 `HTTPS 或 localhost` 校验，也未修改业务登录流程；运行配置暂恢复有效的 localhost Origin。
- 新增 Nginx、Certbot、IP 证书、自动续期和公网 80 端口配置未获自动审批通过，尚未安装。需要用户明确授权此项基础设施，或提供现有 HTTPS 域名和证书位置，再完成公网身份入口核验。
- 不复制本地伙伴、官网补充、课程实验或任务到远端，不重做任何已完成的数据整理。远端继续使用其自己的业务数据。
- 本轮没有真实模型请求；工程兼容通过不等于供应商生成效果通过。

---

> **已执行的 ARM 兼容性验证记录。** 以下结果对应 `acd15e0` 的适配范围，不等于当前 HEAD 全量回归或业务上线批准；当前运行规范见 [README](../../README.md)。

# ARM compatibility validation

This document contains technical compatibility results only. Host addresses, accounts,
credentials, business inventories, uploaded documents and private operational evidence
are deliberately excluded.

## Runtime

Ubuntu 24.04 ARM64, Node.js 22, Python 3.12 and PostgreSQL 16 were verified.
The existing Next.js / FastAPI / SQLAlchemy architecture and business schema are retained.

- Install only required OS packages, without recommendations or a full OS upgrade.
- Use signed Ubuntu ports repositories; compare small metadata downloads before choosing a mirror.
- Verify the official ARM64 Node archive checksum.
- Reuse the npm lockfile and existing `.npmrc`; install only the required ARM64 GNU SWC binary.
- Use ARM64 Python wheels and the already-tested dependency versions.
- Reuse a local browser for remote checks rather than downloading a browser onto the VM.

## Minimal code adaptations

- Optional `BANFEI_API_PROXY_TARGET` exposes the existing API through `/api` on the frontend origin.
  Set frontend `NEXT_PUBLIC_API_BASE_URL=/api` at build time when using this mode.
- Optional `BANFEI_BUILD_CPUS=1` limits Next build workers on small machines.
- Proxy timeout is 420 seconds, covering existing requests whose client budget reaches 390 seconds.
- The client recognizes `/api` when calculating existing request budgets; direct API behavior is unchanged.
- Capability-development submission IDs reuse the existing cryptographic random-ID fallback for HTTP
  origins that lack `crypto.randomUUID`. No ID contract, idempotency or version behavior changes.
- Unset optional proxy settings preserve the current direct-backend local configuration.

## Verification performed

- ARM native imports: psycopg, bcrypt, uvloop, lxml, Pillow and Next SWC passed.
- Backend targeted pytest: authentication, files, OpenAPI, development engine, model network policy
  and V1.2 agent tests: **60 passed**, using an isolated validation database.
- Frontend ARM typecheck and production build: **PASS**.
- Pure frontend compatibility tests: **3 passed**.
- Browser validation via encrypted SSH transport while simulating public HTTP browser semantics:
  login, first-password change, five API reads and nine page types at two resolutions.
- **18 page/viewport checks passed**, with no horizontal overflow or JavaScript errors.
- Resolutions: 1366×768 and 1920×1080.
- No real model requests were issued during this compatibility verification.
- This is targeted ARM verification, not a claim that the full product E2E suite or real-provider
  generation/business acceptance was completed.

## Boundaries

No business API, permissions, schema or model-selection logic was redesigned.
The original machine's database and services were preserved. Remote data-copy evidence and credentials
remain outside Git. Runtime processes remain available for manual testing.

This result is readiness for ARM manual testing, not production approval.
