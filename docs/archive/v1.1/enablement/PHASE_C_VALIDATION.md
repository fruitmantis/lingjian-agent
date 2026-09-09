> **历史归档，不是当前开发规范。** 保留当时的需求、环境、测试和结论；旧品牌、分支、端口、数据库及授权状态均不代表当前 main。历史命令不可直接用于现有运行库。当前入口：[README](../../../../README.md)。

## 交付结论与阶段边界

Phase C 的 Request → 诊断 → 结构化检索 → Plan / Run / Version → 调整、编辑、确认、归档 → 伙伴可传递视图已实现，处于工程验证阶段。本轮停止于 Phase C；没有 merge、push、替换旧版服务或进入 Phase D。

| 验证层次 | 结论 |
| --- | --- |
| 代码已实现 | 本报告的 DEV-01～12、MOD-01～02 及必要 SEC/NFR 范围已实现 |
| mock 自动化验证 | 以本报告自动化结果和提交的证据清单为准 |
| 真实模型验证 | **NOT RUN / 0 CALLS**，不计为通过 |
| 首批真实资源数据验收 | 未执行；隔离业务副本中课程/实验及共享目录仍为空，合成资源仅用于 `/tmp` 测试 |
| 真实业务试点验收 | 未执行；不以代码、mock 输出或截图替代业务验收 |

## 1. 基线、隔离与稳定环境保护

稳定目录 `/home/yuan/project/lingjian-agent` 的 `main` 保持 `f79cbb29ec7b3ad70c88e618e3161211f211c06a`。Phase C 从用户验收的 Phase B 提交派生继续开发，没有修改原分支指针。

- 旧版仅做 Git、文件 SHA-256、进程/cwd 检查和匿名 `8000/health`。**旧版登录次数为 0**；未创建会话、测试用户或写业务表。数据库只读取文件字节哈希，未建立旧库 SQLite 连接。
- 使用 Phase C 开始时重新采集的保护清单比较，避免混用 Phase 0/B 时期的快照。最终 167 个受保护文件哈希均未改变，结果见 `artifacts/enablement-phase-c/protection-verification.json`。
- 旧后端 PID 227786 / 8000，旧前端 PID 236033 / 3000；启动目录仍为原目录及其 `frontend`。
- 新数据库：`.isolation/runtime/app.db`；新上传目录：`.isolation/runtime/uploads`；独立配置 `.env` / `frontend/.env.local`，独立 `.venv`、`frontend/node_modules`、`frontend/.next`、`.isolation/logs`。
- 测试数据库：pytest 的 `/tmp/lingjian-pytest-*` / pytest 临时副本，Playwright 的 `/tmp/lingjian-enablement-e2e/app.db`。实际端口前端 3100、后端 8100、mock 18180。前端 API 和 CORS 均指向新版。
- 没有向稳定库或独立业务副本写入合成业务数据，也没有访问真实付费资源；外部跳转测试由浏览器拦截。
- 未进行远端核验，不声称与 GitHub 服务端同步。

## 2. Schema、迁移前后与恢复路径

schema **v11 → v12**，25 张表增加到 32 张表。新增 7 张 development 表、单 Plan 活动 Run 部分唯一索引、所有者索引及三个快照不可变更新触发器。模型场景仅新增 `partner_development` 的未绑定行；原模型配置、默认模型和已有场景绑定保持不变。

迁移前先用 SQLite `backup` 保存新环境的一致性快照 `.isolation/snapshots/phase-c-pre-v12.db`。未直接复制正在使用的单个数据库文件充当备份。

| 既有数据 | 迁移前 | 迁移后 |
| --- | ---: | ---: |
| 用户 | 1 | 1 |
| 伙伴 | 33 | 33 |
| 案例主数据 | 3 | 3 |
| 原匹配任务 | 48 | 48 |
| 课程/实验目录 | 0 | 0 |
| 案例共享配置 | 0 | 0 |
| 模型配置 | 2 | 2 |
| 场景绑定行 | 6 | 7（仅新增未绑定的发展场景） |

旧业务表逐表内容哈希不变，仅 `app_metadata` 和 `model_usage_configs` 按迁移设计变化。完整性检查 `ok`，重复执行结果一致。既有外键异常仍为 cases 的 rowid 3、4 引用不存在伙伴；新增异常 0，没有借机修复历史业务数据。结构与计数证据：`artifacts/enablement-phase-c/migration-verification.json`。

15 项迁移回放覆盖每条 DDL、场景插入、schema 更新的失败回滚及正常路径。失败时保持 v11，不留下 development 半表；恢复后重放成功。恢复路径是停止**新版**验证进程，在新临时目录从 v11 一致性快照创建副本并重新验证/迁移；不回写稳定库，不降级覆盖运行库，不切换或重置 main。历史数据回放依赖本机私有快照，快照不进入 Git。

## 3. 实际数据模型

| 表 | 关键字段 / 语义 |
| --- | --- |
| development_requests | owner、target partner、完整结构化 `payload_json`、原始诉求、创建人/时间；原始诉求不会被 AI 改写替代 |
| development_plans | 唯一 request、owner、partner、active/archived、current/confirmed 指针、active_run、归档/更新时间 |
| development_runs | generate/revise、owner+submission 唯一、请求指纹、编辑基线、输入快照、模型配置 ID、执行 token、pending/running/ready/partial/failed/interrupted、安全错误阶段与时间 |
| development_versions | Plan 内连续版本号、基线版本、可空 Run 引用、完整不可变 JSON、全部模型候选的授权依赖、创建人/时间 |
| development_version_items | 版本、序号、阶段及结构化资源引用快照；无模型提供 URL |
| development_diagnoses | 版本、正式能力标签、目标满足度、证据状态、判断来源、引用、待核实项、问题分类 |
| development_audit_events | 生成/调整、建版、业务纠正、具体版本确认、归档/恢复、复制事件；不记录密钥或异常堆栈 |

原案例主数据、伙伴、能力标签、用户和模型体系继续复用。确认审计独立于不可变快照；当前确认状态由 Plan 指针确定，过去的确认事件保留。结构化编辑创建 Version，不伪造一次模型 Run。

## 4. 需求编号映射

| 编号 | 实现与验证 |
| --- | --- |
| DEV-01 | 诉求原文、来源、目标、人员岗位/人数/基础、周期投入、7 类硬约束、来源任务/案例、显式假设正式落库 |
| DEV-02 / DEV-06 | 提交前澄清；缺少关键字段不建任务。接受假设需用户填写并显式选择；公司画像不作为个人能力；假设进入版本展示 |
| DEV-03 | 目标满足度和证据状态分别存储、校验和展示；部分证据不推导部分能力 |
| DEV-04 | 强判断仅由登录用户明确确认或业务纠正形成，保留 actor 和确认说明；模型强结论降级或拒绝，不能自授可信来源 |
| DEV-05 | trainable_gap / evidence_gap / non_training_constraint / needs_clarification；仅前者进入资源安排 |
| DEV-07 | 当前发布、system/model 授权、能力标签及约束三态筛选；冲突排除、未知显式提示；资源库无命中不扩展成市场不存在 |
| DEV-08 | 总览、诊断依据、分阶段安排、先修条件、投入、来源、限制和资源缺口结构化展示 |
| DEV-09 / NFR-06 | 一个 Plan 一个任务入口，独立幂等 Run，成功才创建版本；旧请求和并发操作不能覆盖新结果 |
| DEV-10 | 确认具体版本；V2 草稿保持 V1 确认；归档/恢复保留 Run、Version 和指针 |
| DEV-11 | 对话调整可提出目标、周期、投入、约束变化；结构化编辑阶段/资源/投入/备注，判断纠正记录 business_correction，不原地覆盖 |
| DEV-12 | 内部预览/复制已确认版本，复制时重新授权；不创建匿名链接，实际传递仍通过原业务渠道 |
| MOD-01 | 明确发展场景绑定，或明确默认绑定 / 唯一启用默认模型；配置异常失败，不回退到首个启用模型 |
| MOD-02 | Pydantic 严格 schema，候选 ID / 版本约束，保存前再次验证引用；URL 永远由后端当前权限解析 |
| SEC-02 / SEC-03 | 所有新 API Token 校验；用户 A/B 隔离，admin 全量，越权 404；原后台角色约束不降低 |
| SEC-04～SEC-06 | 系统可见、模型发送、伙伴外发互不推导；原附件/内部案例/画像不发送；其他伙伴案例仅来自共享学习版本 |
| SEC-07 / SEC-08 | 伙伴内容字段白名单、金丝雀拦截、安全错误、无密钥/堆栈输出；自由模型文字不进入外发视图 |
| SEC-09 | 普通下架保留名称快照并禁跳转；案例停止共享及敏感撤权重新过滤历史，包括说明文字 |
| NFR-01 | 先落库、快速返回 task/run ID，进程后台执行；20 次隔离接口与真实 HTTP 时延测量见证据 |
| NFR-03～NFR-05（基础） | 3 方案并发隔离验证；单调用 180 秒、Run 10 分钟，启动/访问恢复中断状态，迟到执行 token 失效 |
| NFR-07 | Version、Items、Diagnoses 和 current 指针同事务；四个保存环节故障注入，无半版本 |
| NAV-02 / NFR-08 | 任务列表在 SQL 分页前统一不同类型，原分页/游标/所有权保留；原功能全量回归 |

## 5. 状态机、并发与指针结果

已验证：首次成功 current=V1 / confirmed=NULL；确认 V1 后两个指针均为 V1；调整成功 current=V2 / confirmed=V1；调整失败两个指针不变；确认 V2 后均为 V2；归档和恢复不修改指针。

SQLite `BEGIN IMMEDIATE`、`owner+submission_id` 唯一约束、Plan 活动 Run 部分唯一索引和保存前基线/token 检查共同实现串行化。相同提交返回原 Run，内容不同的重复 key 返回 409；同 Plan 并发调整只允许一个执行；结构化编辑期间产生新版本时，原编辑返回版本冲突。运行中禁止归档、确认和编辑；独立方案可并发执行，不引入 Redis、MQ、Celery 或新服务架构。

资源缺口、证据不足、待评估和条件未知属于业务结果；完整结构通过校验可保存为 ready。非法模型输出、模型/事务技术失败不产生 Version。失败重试从方案内部发起新的调整 Run，旧版本继续保留。

## 6. 页面和 API 改动

- `/enablement` 在 Phase B 页面内升级正式表单，保留画像和来源上下文、资源中心与现有视觉。
- `/tasks/{id}` 按 task_type 分发主体，共用 App Shell；发展方案包含总览、诊断、资源安排、限制、Run 历史和版本操作。
- 原 `/agent/tasks`、`/admin/tasks` 同时返回真实两类任务；按类型筛选，统一分页，Plan 归档/恢复复用原任务路由。侧栏提交后立即出现真实方案任务。
- `/development/capabilities`、`/development/clarify`、`/development/plans`、`/development/plans/{id}`、`revise`、`edit`、`candidates`、`confirm`、`transferable`、`copy`：10 个新认证操作，均 `no-store`。
- 场景广场既有能力发展入口升级为实际方案入口；没有把课程、实验或案例创建成独立 Skill。原管理后台及模型管理继续复用。

## 7. 模型上下文和输出白名单

模型输入仅包括授权后的 target_partner_id、发展目标、岗位/人数/人员基础、周期/投入、约束、明确接受的假设、正式目标标签与目标要求、调整指令，以及结构化诊断和授权候选的最小字段。

不发送 raw_demand、伙伴 AI 画像、内部案例正文、原附件、内部核验备注、项目内部证据、模型密钥、目标来源 task/case 内部链接。人工确认的内部 actor/说明不进入第二次模型请求。候选仅含引用 ID/版本、允许的资源描述与能力元数据、约束三态；没有 URL。模型调整发展目标不会自动授权该新目标伙伴外发。

严格输出拒绝额外内部字段、非法枚举、编造 partner/resource/case/version、任何自编 URL、非候选资源及未获模型授权的来源。模型生成的强结论文字不能绕过结构化人工来源。实际适配器支持 OpenAI-compatible JSON schema 请求，但本轮默认仅允许 loopback；真实供应商兼容性未验证。

## 8. 金丝雀、外发和历史撤权

自动化保留 `INTERNAL_SECRET_PHASE_B_DO_NOT_SHARE`：授权内部上下文可以读取；模型 payload、成功版本、模型输出、伙伴文本及安全错误/应用日志边界直接断言不出现。所有相关合成内容位于测试数据库，未进入真实业务目录。

伙伴可传递视图只读取 `confirmed_version_id`，每次预览和复制重新检查当前权限；复制额外验证预览时的确认版本。白名单为明确获准的发展目标、受控阶段编号、当前允许外发的资源名称/摘要/共享方法/来源及链接、先修/账号/环境/语言/站点/费用条件、已校验投入。剔除模型自由阶段标题/推荐理由/备注、诊断和证据、系统 ID、内部任务链接及错误信息。页面焦点/定时刷新重新核验；不能从旧预览直接复制缓存。

所有模型看过的资源都记录授权版本依赖，防止被引用内容进入说明文字后逃过撤权。普通课程下架/更新保留历史名称、版本引用，当前入口不可用；不会静默替换。共享案例停止共享、版本失效或敏感/授权撤销会隐藏受影响的整体生成内容和来源相关文字，提示重新生成/联系管理员；数据库快照不改写。再次授权不自动复活旧 epoch 的敏感历史版本。

## 9. 自动化实际结果

完整命令、通过/失败/跳过数、P95 和构建结果由 `artifacts/enablement-phase-c/validation-results.json` 记录。主要命令均在新 worktree 中执行：

```text
.venv/bin/python -m pytest backend/tests/test_development_lifecycle.py backend/tests/test_development_migration.py -q
.venv/bin/python -m pytest backend/tests/test_development_engine.py -q
.venv/bin/python -m pytest backend/tests/test_development_api.py -q
.venv/bin/python -m pytest backend/tests -q --junitxml=.isolation/logs/phase-c-backend-final.xml -o junit_family=legacy
cd frontend
npm run typecheck
npm run build
npx playwright test
```

C1 定向 23 passed；C2 定向 21 passed；C3 最终 API 定向 16 passed。最终全量后端 **356 passed / 0 failed / 0 skipped**，2 条既有 Starlette 422 常量弃用警告。独立 ASGI 20 次创建 P95 为 **9.751 ms**，未等待模型执行。真实 HTTP 20 次创建 P95 为 **19.511 ms**，最大 **20.674 ms**，结果见 `http-creation-latency.json`。最终完整浏览器 **54 passed / 0 failed / 0 skipped**；`npm run typecheck` 与 `npm run build` 均通过。

迭代过程中的失败已区分：旧 schema/API 数量断言更新；新测试的导入/fixture 类型、Node UUID、重复 DOM 定位修正。完整浏览器首轮 48 passed / 2 failed / 3 未运行，两项失败是旧测试定位歧义；修正后重新完整运行。此前的失败不伪装为通过，以最终结果为准。

## 10. 浏览器截图与原功能回归

截图为合成数据，视口 **1366×768、1920×1080**，保存全页图；同时断言无横向溢出、导航在视口内，无未处理页面错误。

`artifacts/enablement-phase-c/` 每个视口各 15 张：01 完整表单、02 澄清/显式假设、03 生成中、04 V1 草稿、05 V1 确认、06 V2 草稿且确认仍为 V1、07 诊断、08 分阶段资源、09 资源缺口、10 结构化编辑、11 伙伴视图、12 统一任务列表、13 撤权历史、14 版本冲突、15 调整失败后旧版本。

原页面回归截图在 `artifacts/enablement-phase-c-regression/`，覆盖中心、资源、课程、共享案例、伙伴、原匹配、场景、全部任务和项目上下文。完整文件/尺寸/哈希清单见 `screenshot-manifest.json`。原伙伴匹配、任务归属/列表/详情/重试/归档、需求画像和项目机会、伙伴洞察、场景广场、管理员、用户生命周期、模型配置、系统状态均纳入原有回归测试。

## 11. 停止新版与继续使用旧版

交付前 Playwright 管理的新版 3100/8100/18180 进程全部退出，最终端口检查确认无监听；稳定 3000/8000 原 PID 继续运行，无需重新登录或重新启动旧服务。

以后如启动新版隔离环境，仅使用新 worktree 的 `bash enablement-dev.sh start|stop|status`；脚本核验进程归属。不执行原目录的 stop/restart，不使用宽泛 kill 命令。当前新运行库虽已迁移，但未填入合成资源，真实模型调用开关仍关闭。

## 12. 已知限制与 Phase D 事项

- **真实模型、首批真实资源和真实业务试点均未验收**。真实供应商的 schema 支持、时延、费用和业务判断质量须在获得新的明确授权后单独验证，本轮不执行。
- 既有两条案例外键异常保留；真实资源/共享目录为空，需要业务方人工授权、核验和发布。不能把本轮合成案例当正式内容。
- 为保护进入说明文字的敏感内容，撤权采用保守的整个受影响生成内容隐藏，可能连带隐藏同版本中无敏感内容的段落；历史数据库记录不改写。
- 受控外发使用通用阶段编号和允许资源元数据；不复制模型自由说明或内部备注。新目标外发权限需明确授予。
- 一期仍是 SQLite 单实例、进程内执行，重启后恢复为 interrupted；没有持久化任务队列。不承诺更高并发或生产级容量。
- 历史数据库迁移回放需要本地私有快照；这些文件不会随 Git 分发。更广泛的容量、可访问性、长时间运行和异常组合验收留给 Phase D。
- 既有 Starlette 弃用警告和 Next.js 开发跨源提示未作为本期无关依赖升级处理；生产构建通过。

**具备进入 Phase D 的工程条件**：核心生命周期、事务/并发约束、三维授权、撤权防泄漏、mock 非法输出拦截和原功能回归有可追溯证据。该结论只针对下一阶段工程验证准备，不代表真实模型或发展方案业务已可正式使用。等待用户明确启动 Phase D，本轮到此停止。
