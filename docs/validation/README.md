# 验证文档索引

更新日期：2026-10-17。当前正式工作区 main、本地 PostgreSQL schema 20；运行与安全约束以根目录 [README](../../README.md) 和 [AGENTS](../../AGENTS.md) 为准。

## 当前入口

| 目的 | 文档 |
|---|---|
| 2026-10-17 全仓只读代码审查（未改代码，P0/P1 无） | [独立审查](INDEPENDENT_CODE_REVIEW_20261017.md) |
| 限定整改结束、保留已知缺陷（2026-10-13） | [本轮收口](#bf-close-20261013-01) |
| 最新：基础纠正 P2 与百秒等待收口 | [DEVELOPMENT_P2_LONG_DELAY_20261002.md](DEVELOPMENT_P2_LONG_DELAY_20261002.md) |
| 首页六场景、三处边界修复及 76 项回归 | [最新修复验证](HOME_SCENES_FIXES_20261002.md)；[初次交付](HOME_SCENES_20261001.md) |
| 新任务连续转场、51 项相关浏览器回归及实际 IP 录屏 | [转场验证](TASK_TRANSITION_20261001.md) |
| PG-only 与匹配迟到写入提交范围、证据整理 | [2026-10-01 Git 收口](GIT_CLOSEOUT_20261001.md) |
| 匹配旧执行迟到写入：独立复核 P1、定点修复及新回归 | [迟到写入修复](MATCH_LATE_WRITES_20261001.md)；[原独立复核](POSTGRES_ONLY_INDEPENDENT_REVIEW_20261001.md) |
| PostgreSQL-only 清理、完整测试收口及 8 次真实模型补测 | [PostgreSQL-only 验证](POSTGRES_ONLY_20261001.md) |
| 任务先落库、后台执行、真实进度与渐进展示 | [任务执行与恢复验证](DURABLE_TASK_EXECUTION_20261001.md) |
| WSL 模型响应延迟代理（超时由系统自行配置） | [慢响应模拟使用说明](SLOW_MODEL_SIMULATION.md) |
| 本轮改动提交范围、最新回归及发布边界 | [2026-09-29 Git 收口](GIT_CLOSEOUT_20260929.md) |
| 伙伴选择搜索、500 家伙伴及三种视口验证 | [伙伴搜索选择验证](PARTNER_SELECT_SEARCH_20260929.md) |
| 模型超时失败、原任务重试与提交恢复 | [超时任务恢复验证](TASK_TIMEOUT_RECOVERY_20260929.md) |
| 模型超时配置归口、重试与 schema 18 清理 | [超时与重试验证](MODEL_TIMEOUT_RETRIES_20260929.md) |
| Coze UI 提交边界与合并验证 | [Coze UI 合并验证](COZE_UI_MERGE_20260929.md) |
| 当前统一理解、局部修改、固定模型及 11 次真实调用 | [统一任务流程验证](UNIFIED_TASK_FLOW_20260928.md) |
| 最新工程验证、提交范围、数据边界 | [2026-09-26 Git 收口](GIT_CLOSEOUT_20260926.md) |
| 新对话接续、已完成事项、不要重做的操作 | [项目交接](../handoff/CURRENT_HANDOFF_20260926.md) |
| 最新公网 ARM 部署、近三天兼容检查、数据保留 | [ARM HTTPS 验证](ARM_HTTPS_VALIDATION_20260927.md) |
| 当前 HTTP 80 入口、Origin 与身份回退 | [HTTP 运行说明](../HTTP_SETUP.md)；[此前 HTTPS 验证](HTTPS_VALIDATION_20260926.md) 仅作历史记录 |
| 六类资料、单一案例展示、手动画像、统一后台 | [伙伴资料验证](PARTNER_MATERIALS_VALIDATION.md) |
| 伙伴/课程/实验 Excel 导入导出、空白模板、资源批量上下架 | [导入导出验证](RESOURCE_TRANSFER_VALIDATION.md) |
| 官网能力逐家采集、30 家增量补充、备份及数据边界 | [官网能力补充](PARTNER_CAPABILITIES_20260926.md) |
| 真实供应商验证方法（不代表已执行） | [模型前检](REAL_MODEL_PRECHECK.md)、[验证计划](REAL_MODEL_VALIDATION_PLAN.md) |
| 人工效果验收空白模板 | [业务验收模板](REAL_BUSINESS_ACCEPTANCE_TEMPLATE.md) |

## 专项与历史证据

以下文档保留各阶段实现和结果；其中“未提交”、旧 HEAD、环境状态及通过数字只属于当时，不能作为当前 Git 状态或合计通过数。

| 范围 | 文档与适用边界 |
|---|---|
| 普通身份 | [身份 Key](IDENTITY_KEY_VALIDATION.md)；[本机身份旧记录](LOCAL_IDENTITY_VALIDATION.md) 中的 Passkey 方案已退出当前流程 |
| 账号删除 | [逻辑删除](ACCOUNT_DELETION_VALIDATION.md)，替代早期 90 天/凭据类型及历史清理规则 |
| 能力发展 | [current 与追问](DEVELOPMENT_CURRENT_VALIDATION.md)，confirmed 不参与业务 |
| 范围与错误 | [旧独立 Scope Gate](SCOPE_GATE_VALIDATION.md) 仅作历史；现为 [统一理解](UNIFIED_TASK_FLOW_20260928.md)，沿用 [错误处理](ERROR_HANDLING_VALIDATION.md) |
| 课程与实验 | [资源精简](RESOURCE_CENTER_VALIDATION.md)、[华为云导入](HUAWEI_RESOURCE_IMPORT.md)；案例后续规则以 schema 17 资料文档为准 |
| 公共交互 | [分页](PAGINATION_VALIDATION.md)、[反馈](FEEDBACK_VALIDATION.md) |
| 平台兼容 | [此前 ARM HTTPS 验证](ARM_HTTPS_VALIDATION_20260927.md) 仅为历史部署结果；[当前 HTTP 更新步骤](../HTTP_SETUP.md) 尚未在 ARM 执行；Windows 与内网 ARM 未实测 |
| 旧提交与 Pilot | [09-25 收口](GIT_CLOSEOUT_20260925.md)、[Pilot 归档](PILOT_ARCHIVE_20260925.md) |

<a id="bf-close-20261013-01"></a>

## 2026-10-13 限定整改收口

本轮限定整改结束，已达标成果保留；BQ22旧limitations继承、BQ03证据表述、BQ24条件理解仍未关闭。

- 保留受测模型交互精简、统一理解和合法引用/保存：新模型合同不再要求补问问卷或独立limitations，历史字段兼容读取，业务API、权限和保存校验不放宽。
- D1按用户澄清仅发送最近一组授权问答一次，原历史可读，界面/API不变。原BQ21完整12项和原历史正确定位当前第二实验，解释不建版，一对一替换保留ID和非目标内容/依赖。
- D2同一原锚点各一次replace＋add_after，先替换再后插；真实冲突、越界、非法资源、旧版本及事务保护保持。BQ22主答/资源纠正和组合保存成果保留。
- D3修剩余S5存档模板边界，不改原件/完整提取文本，不按业务否定词清洗；其他五源复用，合并后无变化整理零调用。

BQ22只读补证：实际0004/0005首答已纠正Python/API；旧V1的limitations[0]经后端继承到新V2，并被当前页面显示成使用提示，当前结果一致性仍未关闭。历史V1正常保留不计缺陷，不能归因模型未纠正或整项能力未工作，也不扩大判错到外发复制。

BQ03检测/加固及代码检测产品功能升级为修复证据的问题仍未关闭；BQ24各方承担服务记录与同时满足条件的理解问题仍未关闭，零推荐本身允许。未关闭问题不改判通过，不关闭或隔离功能、不宣布整个匹配不可用、不自动追加整改。

开发77个唯一相关离线用例通过；前端155文件与受测冻结一致，复用成功typecheck/build。独立QA本批真实7逻辑阶段，无质量重问；工程通过不等于全部业务缺陷关闭。本次Git收口不调用模型、不重跑测试、不操作站点、服务、ARM、AgentArts或Release。模型配置沿用，未提供第二个已接入且已核可用候选；不外推到其他环境或账号。

受测基线：本机main / `e2b6085ea48680a985d3ac7908be69ec4dcf1cb8`及已验证差异；BF-CLOSE七文件指纹 `247e675a30e8b1a350fcc130327aeab4aa6b9427b4aaee5dd4d784b90508498d`。已有本地证据保留，不随提交入仓：

- 开发：`task/bf-close-20261013-01/HANDOFF.md`、`FREEZE.json`、`TEST-RESULTS.json`及此前两轮收尾索引。
- QA：`task-2/close-baseline-20261013-01/deliverables/伴飞_BF-CLOSE_独立验收简报_20261013.txt`、唯一当前表`CURRENT_RESULT.csv`、字段链`evidence/BQ22_CHAIN_LOCATOR.json`；修订前材料和原始失败保留。
- 上述路径位于本机`C:/Users/juan/Documents/Codex/2026-10-13/`。不提交数据库、上传原件、私有配置、密钥或含业务原文的请求响应证据包。归档测试需按交接提供`BF_CLOSE_EVIDENCE_DIR`；缺原料的明确跳过不能冒称通过。

这是用户授权的限定整改开发基线；是否接受已知缺陷内部试用及后续模型/产品范围，由用户决定。

## 2026-10-15 限定修复、输入与上传反馈收口

见[本轮脱敏简报](CLOSEOUT_20261015.md)。BQ22旧字段投影/保存、BQ24分工口径、输入快捷键、画像自然分段和上传失败反馈完成对应定向工程验收。UF-QA-01目录状态问题经独立14项后端、4项浏览器复验关闭，WSL标准HTTP80站点已按单独授权更新并核对当前代码、健康及Windows实际IP入口。

BQ03同源标题已入模型输入，但实际首答仍存在产品能力归属措辞问题，继续开放，不声明全部业务通过。本次收口不再修它或重做付费测试。真实Windows IME和正常登录会话中的正式数据页面观察范围见简报；本地原样业务证据与无关未跟踪资料保留、不入库。

## 统一口径

- 自动化只用专用 `banfei_agent_test` / `banfei_validation` 的独立临时 schema，上传夹具只用本轮 `/tmp` 目录；禁止使用正式库或 public 执行测试。
- 正式后端入口为 `.venv/bin/python scripts/run_postgres_validation.py backend -q`；先在当前进程私密加载 `BANFEI_TEST_DATABASE_URL`，不能打印连接串。
- pytest、浏览器与夹具均直接使用本轮专用 PG 临时 schema，不使用中转数据库。缺少配置直接报错；临时 schema 只由创建它的本轮进程删除。
- 经用户确认，旧 Pilot 和历史修复工具及其专用测试已删除，不计入当前通过数；历史报告中的混合验证数字保留原口径，不改写成 PG 通过。
- UI / replay / 真实模型请求分别记录，最新真实调用次数与结果见对应专项记录。测试通过不等于人工业务验收或部署授权。
- 当前库已完成 schema 17 迁移和授权的伙伴名单整理；文档中的迁移命令是其他旧环境升级说明，不是重复执行要求。

- [2026-10-02 能力发展可选伙伴关联](OPTIONAL_DEVELOPMENT_PARTNER_20261002.md)：空关联、自述基础及多轮纠正、模板与隔离验证；原运行库已保留数据与外键升级至 schema 19，服务已恢复；196项后端及83项浏览器验证通过。
