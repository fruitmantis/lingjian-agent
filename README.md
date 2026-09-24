# 伴飞 Agent

面向公司内部人员的伙伴智能助手，提供“项目找伙伴”和“能力发展”两条主线。正式工作目录为 `/home/yuan/project/lingjian-agent-enablement`，直接在 `main` 开发。工程名、模块名、API 和 `LINGJIAN_*` 环境变量保留技术标识。

## 主要功能与入口

| 入口 | 当前功能 |
|---|---|
| `/` 开启新任务 | 显式“项目找伙伴 / 能力发展”两个 Tab；不自动猜测业务模式 |
| 项目找伙伴 | 项目需求 → 使用现有标签、行业/区域、画像摘要、案例摘要及交付物名称匹配 → 推荐/理由/证据/风险 → 需求画像、项目机会 |
| `/?mode=development` 能力发展 | 伙伴 + 自然语言方向 → 顾问式建议、资源与缺口 → 解释、比较或自然语言调整 |
| `/scenes` 场景广场 | 发现并进入已有能力；能力短板分析进入能力发展，伙伴能力/画像/案例查询进入伙伴洞察 |
| `/partners`、`/partners/{id}` | 伙伴洞察、画像与资料；制定发展建议时带入伙伴上下文 |
| `/resources`、`/resources/{type}/{id}` | 独立课程/实验/共享案例目录，搜索、筛选、详情和发起来源跳转 |
| `/tasks`、`/tasks/{id}` | 两类任务共用历史；创建后即出现，真实状态更新，首批 10 条、独立滚动与加载更多 |
| `/feedback` | 问题描述与可选截图提交；支持 Ctrl+V 粘贴、多图预览和提交前删除 |
| `/admin/feedback` | 管理员查看全部反馈及截图，切换待处理／已处理 |
| `/login`、`/account` | 普通身份 Key 登录与个人中心 |
| `/admin/login`、`/admin/change-password`、`/admin/account` | 独立管理员密码登录、改密与个人中心 |
| `/admin/tasks/{id}` | 使用管理员会话查看任务，复用原详情组件 |
| `/admin/*` | 任务、伙伴/资料/案例共享、资源发布核验、需求画像、项目机会、运营报表、标签、用户、模型、系统状态 |

伙伴详情、匹配结果和共享案例中的发展入口都汇入统一新任务页，并带入允许的来源上下文。`/enablement` 仅保留兼容跳转，不提供另一套用户工作台。

- 匹配资料有多少用多少，不要求人工整理或补齐；交付物使用已有名称，不新增摘要字段。画像上下文最多 3000 字符，单案例摘要最多 500 字符。
- 能力发展解释/讨论不生成版本；修改成功产生新 Version。草稿可直接查看、打开资源和继续问伴飞。历史、采用版本、运行记录为二级操作，不展示普通用户高级编辑入口。
- 失败调整保留已有建议；普通失败提示简化为重试、联系管理员或刷新核实结果；必填项和登录问题保留具体提示。空匹配为正常结果。项目机会抽取兼容常见格式差异，无法提取的字段记“未知”，不把未知计为完整信息。机会库支持紧凑多选筛选、重置和展开详情。
- 伙伴启用/停用保留历史；管理员仅可删除无业务历史的误建伙伴，有关联时返回阻止原因及数量。
- 行业与区域使用 [唯一标准字典](shared/business-taxonomy.json)，支持多选及同时覆盖国内/海外；未知旧分类保留待确认。
- 统计同时包含两类任务，一份 Plan 只算一项；系统状态读取配置和最近执行记录，不主动调用模型。

## 技术与安全边界

Next.js 15 / React 19 / TypeScript；FastAPI / Python；**PostgreSQL 16 / SQLAlchemy Core / psycopg，schema version 16**；本地上传存储；OpenAI-compatible 模型接口。无 Alembic；未接入 Chroma、Embedding、向量库、RAG 检索、队列或微服务。

保留 `user/admin`、后端管理权限和任务 owner 隔离。普通用户首次访问自动建立身份，浏览器记住会话；长期身份 Key 可在其他浏览器恢复同一用户，不再注册、审批、使用密码或 Passkey。管理员通过独立入口保留密码登录和首次改密；没有固定默认凭据。系统可见、模型可发送、伙伴可外发分别校验；共享案例使用当前授权共享版本。伙伴可传递视图只取 confirmed 版本并实时重检权限，不输出内部诊断或备注。

Plan / Run / Version、current / confirmed、幂等、版本冲突、事务、超时、中断及撤权保护继续保留。资源跳转不等于学习完成；没有 LMS 或正式能力认证。健康度仍等待外部平台，不自行扩展评分。

视觉保持黑白灰 + 华为红 `#C7000B`、现有红色图标和伴飞 Agent 字标；Latin/数字 Web Font 从本地加载，中文按系统 fallback。字体二进制不进 Git，换机器按 [字体来源与复现说明](docs/design/HUAWEI_CLOUD_FONT_SOURCES.md) 获取；不要重新设计 Logo。

## 当前本地运行

| 项目 | 当前配置 |
|---|---|
| 系统 / 工作区 / 分支 | WSL Ubuntu 24.04 / `/home/yuan/project/lingjian-agent-enablement` / `main` |
| 前端 / 后端 | http://localhost:3000 / http://localhost:8000 |
| 后端健康检查 | `GET /health` |
| PostgreSQL 库 / 用户 | `banfei_agent` / `banfei_app`（PostgreSQL 16） |
| 私有配置 | `.isolation/runtime/dev/environment.json`，包含 `DATABASE_URL` |
| 上传 / 日志 | `.isolation/runtime/dev/uploads` / `.isolation/logs/` |
| 原 SQLite 与备份 | `.isolation/runtime/dev/app.db`、`.isolation/postgres-migration/`，保留、不参与正常运行 |

```bash
cd /home/yuan/project/lingjian-agent-enablement
bash enablement-dev.sh status
bash enablement-dev.sh start
# 需要停止当前服务时：
bash enablement-dev.sh stop
```

复用已有 `.venv`、`frontend/node_modules`、配置和运行数据，不重新初始化。legacy 目录、旧 feature 分支及历史 worktree 不得作为正式开发环境，legacy 服务保持停止。

同一代码已做 ARM64 兼容：可用 `NEXT_PUBLIC_API_BASE_URL=/api` 配合 `BANFEI_API_PROXY_TARGET` 使用同源代理，`BANFEI_BUILD_CPUS=1` 限制小机器构建并发；本地当前仍直连后端。见 [ARM 验证范围](docs/validation/ARM_VALIDATION_REPORT.md)。Git push 不自动更新 ARM 服务。

普通用户的失败提示与管理员诊断分离。后台 **系统状态 → 最近错误** 按时间倒序展示最近 50 条脱敏记录，可展开和复制详情。记录复用 `.isolation/logs/`：`errors.jsonl` 追加保存，已有后端日志同时记录；重试成功不删除历史。无需数据库 schema 变更，数据库故障也能记录。每条包含时间、任务或请求标识、失败环节、实际异常和堆栈；模型错误含可取得的模型名称、HTTP 状态码与必要返回片段。返回片段和超长字段有长度上限并标记截取，不采集请求正文或 Prompt；密钥、Token、身份 Key 和 Cookie 脱敏。完整诊断仅管理员接口可读，不进入普通任务响应。

记录从本次功能启用后开始；此前未保存的真实异常不能补录。私有日志应与现有服务器日志一并保管；本版无自动清理、告警或错误分析服务。验证环境用 `BANFEI_ERROR_LOG_PATH` 指向 `/tmp`，不会把合成错误写入运行日志。

## 普通身份 Key 与管理员会话

普通用户首次访问 `/`，自动创建 `users.id` 和一个长期身份 Key，直接进入业务页面。首次弹窗提供复制、下载 `.txt`、稍后保存及“已有 Key？登录原身份”。关闭弹窗后可随时在 `/account` 的“身份凭据”中查看同一个完整 Key。有效会话直接进入；浏览器会话失效后可通过记住的 Cookie 恢复，不重复建用户或换 Key。

`/login` 会优先恢复当前浏览器的有效身份，不自动创建用户；仅在没有有效凭据时显示 Key 表单。主动切换使用 `/login?method=key`，首次弹窗“已有 Key”也进入该显式入口。可粘贴 Key 或点击“导入凭据 .txt 登录”，选择之前下载的凭据文件（也支持只含一个完整 Key 的 .txt）。文件在浏览器本地读取，仅向现有登录接口提交 Key，文件不上传；空文件、格式错误、多 Key 或超过 16 KB 的文件直接提示错误，不创建用户。正确 Key 恢复原 `users.id` 和原有历史，并记住当前浏览器；错误 Key 只报错。换浏览器或清除站点数据后可直接访问此页。如果先访问自动创建入口 `/`，会按首次访问规则建立一个新身份；在首次弹窗选择已有 Key 后切换到原身份，不合并、不删除刚建立的空身份，也不会在 Key 登录时再创建用户。

每个普通用户只有一个由 32 字节随机数生成的 Key，数据库保存 SHA-256 查找摘要和经过 Fernet 认证加密的密文。`BANFEI_IDENTITY_ENCRYPTION_KEY` 与 JWT 签名密钥分开，只放 Git 忽略的私有运行配置。必须随数据库备份妥善保存此配置，否则不能重新展示已有 Key；程序不会自动生成替代密钥或轮换用户 Key。明文只由已认证的本人端点返回，响应禁止缓存，不进入普通用户资料、管理员列表、认证审计或模型上下文。

浏览器仅保存独立的随机会话 Cookie（HttpOnly/SameSite=Strict，HTTPS 下 Secure，最长 365 天）及当前普通 Token，不把长期 Key 写入浏览器存储。普通“退出”撤销旧 Token 和旧 Cookie 的绑定，保留一份新的浏览器凭据，不发放登录 Token，回到身份入口。刷新、重开浏览器仍停留退出页，点击“继续使用当前身份”即可恢复原用户和历史，不需输入 Key，也不创建用户。需要切换身份时可选择“使用其他 Key 登录”。站点凭据已清除或失效时才需要 Key；不能凭设备信息猜测用户。不同浏览器的会话及管理员会话不受影响。

管理员 `/admin/login`、改密、锁定、重置、停用和任务查看保持原实现；普通和管理请求分别使用对应身份，退出互不覆盖，不能相互转换角色。用户管理列表/详情显示鉴权方式及只读“Key 标识”：普通长期 Key 由后端校验现有凭据归属后返回 `bf_` + 随机部分前 2 位 + `…` + 末 5 位，详情同时显示用户 ID，便于辅助核对。管理员或无长期 Key 的旧身份显示“—”，无法校验或解密的凭据显示“暂不可用”。管理员接口不返回完整 Key、密文或摘要；旧凭据记录按原实际类型显示，仅用于历史数据查看。普通注册、审批、密码登录、首次改密和 Passkey 接口均关闭。

本地统一使用 **http://localhost:3000** 和 **http://localhost:8000**。`BANFEI_IDENTITY_ORIGIN` 默认前者；正式运行须配置稳定 HTTPS 内网域名、CORS 与精确匹配的 Origin。当前不部署，不改现有模型配置，也不将网络可访问身份解释为员工实名。

不迁移、合并或删除旧普通用户和历史；旧 Passkey/浏览器凭据不能用于新认证，也不会自动获配 Key。无 Key 找回、MFA、自动轮换或设备管理。

Key 文件格式错误在浏览器内提示；Key 格式错误、未知/旧版失效、身份已删除、身份停用由现有接口返回独立错误类型。删除用户时在同一事务保留 Key 不可逆摘要和删除时间，用于显示“原身份已删除”，不保留 Key 密文、用户关联或业务数据。此前已删除且未留摘要的凭据只能提示“凭据无效或已失效”。被删除身份可点击“创建新身份”，产生新的 user_id 和 Key；不会自动创建、恢复或合并旧身份。停用提示管理员启用，不显示新建快捷操作。尝试已删除/错误 Key 不影响当前浏览器的其他有效身份和管理员会话。

管理员仍可手工删除没有业务历史和公共引用的普通用户，操作前预览关联数量、二次确认、事务化删除并撤销凭据。长期 Key 用户有业务历史时只支持停用，不套用旧浏览器身份过期清理。保留原旧数据规则：纯旧 Browser Identity 的私有历史须连续 `BROWSER_IDENTITY_RETENTION_DAYS=90` 天未使用；旧 Passkey/混合用户有历史不可删。公共/共享/发布/跨用户引用及运行中任务始终阻止删除，管理员不开放删除。无自动清理、回收站或审批。

`users.last_active_at` 由有效普通身份请求刷新；管理员查看不刷新被查看用户。最新实施与验证记录见 [身份 Key 验证记录](docs/validation/IDENTITY_KEY_VALIDATION.md)，[原本机身份记录](docs/validation/LOCAL_IDENTITY_VALIDATION.md) 仅保留历史依据。

## 数据库与迁移

- `DATABASE_URL` 显式选择 PostgreSQL，缺失或连接失败直接报错；不自动回退 SQLite。不要用旧 SQLite 快照覆盖切换后的新增数据。
- v12 升级到 v13 使用 `scripts/migrate_local_identity.py --backup-dir <新的私有备份目录>`，由既有私有配置提供 DATABASE_URL。先 pg_dump，后事务新增凭据/challenge 表、放宽普通用户密码列并约束管理员密码；不重建库、不自动删除旧用户。失败回滚；回退须连同认证代码和备份一起评估，不能把 v12 程序直接指向新增无密码身份的数据。
- v13 升级到 v14 使用 `scripts/migrate_user_activity.py --backup-dir <新的私有备份目录>`，仅增加可空 `users.last_active_at`，不删除业务数据；先备份后事务执行，失败回滚。当前库已迁移，不重复执行。回退应停止服务并协调代码/schema 版本；新增时间列可保留，不需要重建数据库。
- v14 升级到 v15 使用 `scripts/migrate_identity_keys.py --backup-dir <新的私有备份目录>`，先备份后在单一事务新增 `user_identity_keys`（user_id 主键、唯一 Key 摘要、密文及创建时间），不修改既有用户/凭据/业务行；失败自动回滚。v15 迁移已执行，不重复执行。回退须先停止服务、保留 v15 数据和私有密钥备份，再协调代码/schema；已产生 Key 用户后不可直接回退旧认证或用旧库覆盖新增数据。
- v15 升级到 v16 使用 `scripts/migrate_revoked_identity_keys.py --backup-dir <新的私有备份目录>`，先 pg_dump，再事务新增 `revoked_identity_keys(key_hash PRIMARY KEY, revoked_at)`，不改既有用户/Key/业务行，不回填历史删除。运行库须显式迁移，不自动升级；失败回滚，重复执行保留已有失效记录。回退须停服并协调代码/schema，保留新增失效记录；不能恢复旧库覆盖后续数据，也不能用旧代码执行会漏记失效摘要的删除。
- 38 张表（包括保留的旧身份表及新增 Key 映射）的映射位于 [storage_models.py](backend/app/storage_models.py)。保留现有 UUID、外键、JSON 文本、时间和标志字段；当前 schema version 为 16。
- `match_records.last_error_details` 是 v12 内已落地的可空增量列；当前环境已完成迁移，不因阅读文档再次执行。
- [SQLite → PostgreSQL 工具](scripts/migrate_sqlite_to_postgres.py) 只用于经授权的一次性迁移：SQLite backup API、原库只读、空目标库、事务导入和逐表对账。
- [任务错误详情迁移工具](scripts/migrate_task_failure_details.py) 先 `pg_dump`，再事务加列和校验；不能替代业务数据备份策略。
- 禁止删除、清空、重建、重新 seed、随意替换任何现有数据库、上传目录或私有备份。必要变更须先核验实际目标，提供备份、事务与回退方案。
- 历史 Pilot 文件工具只兼容 SQLite，不能对当前 PostgreSQL 运行库使用；见 [兼容工具说明](pilot-data/README.md)。

## 问题反馈

普通用户在左侧个人区域进入“问题反馈”，只填写描述（1—5000 字）和可选截图，提交人由当前登录身份确定。支持 Ctrl+V 粘贴与点击上传、即时缩略图、多图及提交前删除；最多 5 张，每张 5 MB，支持 PNG/JPEG/WebP/GIF，后端校验真实格式及像素上限（2500 万像素）。成功仅提示“问题已提交”。

管理员在 `/admin/feedback` 查看分页清单、完整描述和截图，仅有“待处理／已处理”两个状态。普通用户没有反馈查询、状态更新或截图读取权限。截图通过管理员 Bearer 鉴权接口读取，不生成公开链接，不调用模型。

PostgreSQL 保存 `feedback_issue`、`feedback_attachment`，图片位于现有上传目录的 `feedback/` 子目录，数据库只存文件元数据。提交失败时回滚记录并清理本次新文件，保留已有文件。

历史 v12 环境若尚无反馈表，使用 [增量迁移](scripts/migrate_feedback.py)；当前环境已完成，无需再次执行。该工具不会在启动时自动运行。旧环境先使用现有私有配置提供 `DATABASE_URL`，然后执行：

```bash
.venv/bin/python scripts/migrate_feedback.py --backup-dir <新的私有备份目录>
```

工具仅允许本机 `banfei_agent`：先 `pg_dump`，再事务新增两张表和索引，不改既有业务表和当时的 schema version 12；本机身份迁移再将版本升至 13。失败时 DDL 自动回滚；代码回退可保留新增表及截图，不自动删除反馈数据。旧 v12 SQLite 快照缺少反馈表时仍可用于原有显式导入工具，目标反馈表初始化为空；日常运行继续使用 PostgreSQL。

相关验证：`run_postgres_validation.py backend -q -k feedback`；`run_postgres_validation.py browser feedback.spec.ts`。均须使用专用验证库及 `/tmp` 上传目录，不能对业务库执行测试。验证范围与结果见 [反馈验证记录](docs/validation/FEEDBACK_VALIDATION.md)。

## 模型配置

日常业务及人工体验使用已批准的 **`api.deepseek.com` / `deepseek-v4-flash`**。七个场景：`default`、`partner_profile`、`partner_match`、`demand_profile`、`tag_suggestion`、`recommendation_summary`、`partner_development`，均显式绑定现有启用配置。

用户已授权按现有权限发送所需伙伴资料/画像、案例说明、项目需求、对话及授权资源，伙伴画像生成包括上传文档提取文本。能力发展仍按最小上下文排除内部附件和案例原文。不擅自改模型、Key、默认绑定或供应商，不自动批量处理业务材料。

本地 mock 不参与日常运行；历史配置已停用但因历史 Run 引用保留。仅隔离单元故障注入和显式 replay 使用测试桩。

原匹配等场景保留既有 default/环境兼容回退；显式无效绑定报错。能力发展按场景绑定 → default 场景绑定 → 唯一启用默认模型选择，不取首个启用模型。DeepSeek 当前适配为 `json_object` + 完整 schema 提示，关闭该模型思考输出；最终仍做程序结构、ID/URL、权限及强结论来源校验。不展示 Prompt、原始响应或凭据。

真实模型已获授权并已有调用；不沿用早期零调用结论。每次新增验证须限定范围、记录次数；普通 UI/文档工作不调用模型。执行前检查和验证计划见 [模型前检](docs/validation/REAL_MODEL_PRECHECK.md)、[真实模型验证](docs/validation/REAL_MODEL_VALIDATION_PLAN.md)。

## 测试

私有 `BANFEI_TEST_DATABASE_URL` 必须指向本机专用 `banfei_agent_test` 或兼容的 `banfei_validation`，不能使用运行库连接串。当前本机验证配置保存于 Git 忽略的 `.isolation/runtime/dev/validation-environment.json`，运行前将其中的变量加载到当前测试进程，不输出连接串。PostgreSQL 用临时 schema；SQLite 兼容/迁移测试和上传夹具仅在 `/tmp`。全量或进程恢复/E2E 测试会占服务端口，先核对并停止当前服务，结束后只恢复 main，不启动 legacy 或遗留模型夹具。

```bash
# 私有 BANFEI_TEST_DATABASE_URL 已由环境提供后，在仓库根目录：
.venv/bin/python scripts/run_postgres_validation.py backend -q
npm --prefix frontend run typecheck
npm --prefix frontend run build

# 无模型的默认 UI 子集（不是完整浏览器套件）：
.venv/bin/python scripts/run_postgres_validation.py browser

# 完整隔离生命周期/故障回放：
PLAYWRIGHT_MODEL_MODE=replay .venv/bin/python scripts/run_postgres_validation.py browser
```

- 开发、build、Playwright 不得同时写同一 `.next`；可在独立构建目录验证。
- 默认 UI 子集以 [Playwright 配置](frontend/playwright.config.ts) 的 `testMatch` 为准，不在文档写固定数量。`opportunity-ui.spec.ts` 已单独验证，尚不在默认子集中；完整 replay 会包含它。
- 未配置 PostgreSQL 验证库的普通 pytest 可能仅验证 SQLite 兼容路径，不能据此宣布 PostgreSQL 全量通过。
- 真实接口 smoke 使用现有 `scripts/verify_real_model.py`，最多两次合成请求；不读伙伴附件，不建业务任务。故障回放与真实供应商测试分别记录。
- 版本化测试记录仅证明对应提交/范围；工程、真实模型兼容、真实资源与业务验收分别判断，不相互替代。业务样例填写 [现行业务验收模板](docs/validation/REAL_BUSINESS_ACCEPTANCE_TEMPLATE.md)，不由工具代填结论。

## 文档边界

[AGENTS.md](AGENTS.md) 是当前开发约束；`docs/validation/` 是当前验证方法/模板及明确标注基线的兼容记录，`docs/design/` 是设计与字体取证。`docs/archive/v1.1/` 保存早期 MVP、Phase A–D、RC/Pilot 历史；`docs/archive/v1.2/` 保存 V1.2 改版与归档记录。历史中的品牌、端口、分支、数据库、授权与测试数字不是当前状态，旧报告生成脚本也不是现行运行入口。

默认只在 main 做最小改动；未经明确要求不 commit、push、部署、创建分支或 worktree，不丢弃已有修改，不提交数据或凭据。
