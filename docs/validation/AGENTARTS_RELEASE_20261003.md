# AgentArts 部署与验证归档（2026-10-03）

## 结论与来源

独立复核确认当前配置域名的桌面演示可用，无必修阻断。已部署的 16 份 VM 文件与独立 QA 清单逐项 SHA-256 一致，AgentArts 后端重启和健康检查通过，HTTP 入口已恢复；本轮收尾检查没有运行中的任务。原版 ARM 应用及 WSL 主干保持原状态，未修改 sudo、网络安全配置或认证凭据。

代码来源为 main `0a463c8253ede2ab1eeb31908bf4c8781bd31610` 的适用修复，保留 AgentArts Runtime 适配。目标分支仍为 `agentarts`，本记录不表示已提交或推送。

Runtime 镜像 tag `agentarts-swr-20261003105539`，Docker V2 单 manifest、linux/arm64：

- manifest：`sha256:7f53e825f119ba3ed3834c882b1414d98950d12694777936d76e8133bcbc05b2`
- config：`sha256:2b280be75c601c0a9f60e2ac0aa2c1673948d2bc37bdd3d41d74941b07567f44`

构建、推送 digest 一致；用户确认云端更新并运行。新云 session 实测 runtime-info 200、模型路由匹配、非法 job 422，以及合成完整消息超预算在 provider 网络请求前拒绝。Runtime API 不暴露镜像 digest，因此未把运行接口探测表述为独立的云控制面 digest 回读。

## 当前变更概要

无状态 Runtime 提取共享 schema、提示词和输出防护，VM 继续负责授权、来源/模型固定、先落库、Run/current 和结果持久化。VM/cloud 共用 provider thinking 选项、发展根字段白名单与能力记录判断。六阶段按照完整消息和既有协议计算预算，保留初筛压缩、来源检查和仅超时经 VM 再授权的重试。诊断只返回固定枚举和受限数值，不泄漏原始响应或密钥。独立 ARM/systemd/Caddy/PG 配置模板与私有交互配置工具随源码保留；模板不是运行时私有配置，也不是自动部署授权。

## 真实云端证据

| 流程 | 实际范围 | 结果 |
| --- | --- | --- |
| 伙伴匹配 | 179 家初筛、12 家详评；合成验收需求 | ready，5 家推荐，约 87 秒 |
| 能力发展 | 173 资源 / 301 资源版本目录；合成验收需求 | ready，1 个 current Version，页面 6 条引用资源，约 66 秒 |

两流分别使用新 session；共 5 个成功模型阶段，每阶段 attempt=1，无自动重试。模型目的地为获授权的官方 DeepSeek，保持已保存参数。截图及阶段元数据保存在操作者本地证据中，不随源码提交。未发布任务/用户标识、伙伴名称/正文、截图、数据库内容、运行日志或私有环境信息。

本次真实墙钟等待只覆盖约 66 / 87 秒。没有用付费云模型制造百秒等待、取消或失败。百秒延迟/取消场景只能按其独立合成证据描述，不能由超时配置值推导。本次精确 19 项子集并未实际等待百秒，也未证明完整重试次数耗尽。

## 合成故障测试：19 项，范围逐项可查

原有选择条件已在专用验证 PostgreSQL 上重跑：19 passed / 1051 deselected，30.22 秒。合成模型、测试自有随机 schema/临时服务、外部真实模型网络阻断，未触碰运行中的产品服务。实际 node IDs、源文件哈希及每项断言见 [fault-tests.json](AGENTARTS_RELEASE_20261003.fault-tests.json)。

在仓库根目录、使用项目依赖环境并通过现有私有方式设置 `BANFEI_TEST_DATABASE_URL` 后，选择命令为：

```sh
python -B scripts/run_postgres_validation.py backend -vv -p no:cacheprovider -k 'timeout_needs_fresh or lost_retry_ack or runtime_waits_and_deduplicates or non_timeout_failure or runtime_cancels_orphaned or runtime_failure_preserves or actual_runtime_process_kill or actual_vm_process_kill or runtime_protocol_auth_dedup'
```

| 断言组 | 参数化用例数 | 实际断言 |
| --- | ---: | --- |
| 首次超时后模型停用/来源撤权/账号停用，两流 | 6 | 只调用一次，不授权重试；4001 秒 / 5 次配置透传，不实际等待 4001 秒 |
| 丢失重试 ACK，两流 | 2 | 只发一次授权，GET 对账，不重复调用 |
| 等待授权与重复授权 | 1 | 等待状态不自行重试，拒绝错误绑定/并行抢入，重复授权只再调用一次，取消后拒绝新授权 |
| 非超时失败，两流 | 2 | ConnectError 不重试 |
| 鉴权、去重、会话、重启、预算 | 1 | 非法请求拒绝，同一 operation 只执行一次，旧 incarnation 不重放 |
| 租约过期 / DELETE 取消 | 2 | 中止合成 30 秒 sleep，3 秒内结束，无成功结果；未等满 30 秒 |
| Runtime 重启 / VM 重启 / 错误 run | 3 | 原 current、历史 confirmed、已有版本与正文保留 |
| 真实临时 Runtime 进程重启 | 1 | 旧 operation 查询 404、重放 409，不再次调用 |
| 真实临时 VM worker 被终止 | 1 | 恢复标记 interrupted，晚到结果不生成版本，不再次调用 |

此前本地完整回归、74 项离线及独立 QA 的 84 预算边界、6 提示词、8 严格字段、909 能力判断另有历史记录，不与本次 19 项相加或声称全部重跑。

## 入口与验证边界

当前配置域名 HTTP 80 正常；裸 IP/未知 Host 404 是既有隔离配置，未在本次改路由。内部应用与 PostgreSQL 保持回环。原版应用仍保持停机，未为了验收启动。

浏览器两次创建后约 1.8 秒打开对应任务；原始需求、最终结果、进度和当前选中状态已查看。小视口侧栏点击曾受裁剪影响，最终通过直接任务路由取证；该项、逐帧闪屏及真实双击不计为本轮通过。独立复核的桌面域名可用结论不扩大为所有视口和所有交互通过。

## 仓库与本地证据边界

本归档只保留脱敏结论、源摘要和可复现测试标识。历史现场 Markdown、sources 快照、Caddy 运行核验 JSON/补丁、原始日志与截图保留在本地，提交候选使用精确白名单排除它们；不删除历史证据。实际测试解释器路径、完整 argv、JUnit 和 verbose 日志由本地收尾清单关联，避免将本机私有路径作为运行环境要求。
