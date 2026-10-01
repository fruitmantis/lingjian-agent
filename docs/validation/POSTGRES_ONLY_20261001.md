# PostgreSQL-only 清理与验证（2026-10-01）

> 后续更正：独立复核确认原“迟到保护已覆盖”的结论遗漏了匹配完善阶段的派生保存，原实现存在 P1 迟到覆盖缺陷。下文 941 项等数字保留为当时批次，不能用于本轮修改后的代码。缺口、定点修复及新验证记录见 [迟到写入修复](MATCH_LATE_WRITES_20261001.md)，原失败见 [独立复核](POSTGRES_ONLY_INDEPENDENT_REVIEW_20261001.md)。

**本轮收口结果：** 最终完整后端 PG 941 项、浏览器去重 108 项、脚本 12 项及 15 个子测试通过；typecheck/build/diff-check 通过。3000 条资源候选检索最终 p95 0.622 秒（原门槛 <2 秒）。追加授权的 8 次真实模型请求及版本/重试断言通过。运行数据与 13 份保留备份摘要不变。本报告保留前面失败批次，最后结果见文末；原始证据存于 [现有验证目录](evidence/pg-only-20261001/final-results.json)。

工作目录 `/home/yuan/project/lingjian-agent-enablement`，分支 `main`，基线 `b63a903`。保留开始时已有 HTTP、伙伴匹配/画像、任务持久化等未提交改动；未切分支、stash、reset、commit、push 或部署远端。本轮不新增业务状态、接口、表或版本；schema 仍为 18。

## 实际改动

- `backend/app/config.py`、`database.py`、`postgres_storage.py`：只接受显式 PostgreSQL / psycopg URL。缺少配置、不支持的 URL、连接失败直接报错。删除文件数据库连接、建表、升级、路径选择和 SQL 方言转换。
- 现有 SQL 调用直接使用 PostgreSQL JSON、ILIKE 和事务锁；保留 Core / psycopg、参数绑定、只读事务、一致快照和写事务串行化。写锁按 database/schema 隔离，测试不会锁住运行库或其他临时 schema。
- `storage_defaults.py` 与 `scripts/initialize_postgres.py`：复用现有 schema 定义、初始标签/分类/场景/超时默认值；仅空 schema 可显式初始化到 18，已有表或视图直接拒绝。启动只验证，不自动升级、重建或 seed 运行库。原 PostgreSQL 增量升级及备份工具保留。
- `scripts/normalize_business_taxonomy.py` 保留 UPDATE-only 修复能力，改用 PostgreSQL 事务和 `pg_dump` 一致性快照，必须显式提供新的备份目录；本轮未对运行库执行该工具。`migrate_task_failure_details.py` 不再依赖已删除的文件库迁移器。
- pytest、浏览器及辅助夹具直接在 PostgreSQL 创建合成数据，移除先生成文件数据库再导入的步骤。URL 限定本机 `banfei_agent_test` / `banfei_validation`，禁止运行库、public 及覆盖 host/database 的 query 参数；缺少验证配置直接失败。
- pytest 每项测试 / Playwright 每轮使用 `validation_<随机UUID>`，只能清理本轮自己成功创建的 schema。测试后台执行器在 schema 清理前退出；上传、日志和身份夹具在独立 `/tmp` 目录，不写运行库。Playwright 的 fixture helpers 继承同一受保护 PG URL。
- `test_development_lifecycle.py` 的 8 项保留；版本/发布/伙伴/文件删除故障使用真正的 PG 服务端触发器异常。初始化故障在实际 DDL/DML 后注入 PG 除零错误，验证事务回滚、无残留及重试恢复，没有把全部数据库操作 mock 掉。
- `AGENTS.md`、`README.md`、`.env.example`、验证索引和历史报告适用范围说明已同步；不再允许 SQLite 兼容测试或默认排除旧测试。

## 删除文件

以下为本轮删除的项目源代码、旧工具专用测试、失效执行手册和空模板。三个 Pilot / 历史修复专用测试已获用户明确授权删除，不计入 PG 通过数量；没有删除当前业务测试以取得通过。

- `backend/app/enablement_schema.py`
- `backend/app/development_schema.py`
- `backend/app/feedback_schema.py`
- `backend/tests/test_pilot_import.py`
- `backend/tests/test_pilot_intake.py`
- `backend/tests/test_historical_repair.py`
- `backend/scripts/repair_historical_data.py`
- `backend/scripts/verify_enablement_snapshot.py`
- `backend/scripts/verify_phase_c_protection.py`
- `backend/scripts/verify_phase_d_protection.py`
- `backend/scripts/verify_rc_protection.py`
- `backend/scripts/seed_huawei_service_partners.py`
- `backend/tests/support/seed_v12_manual.py`
- `scripts/migrate_sqlite_to_postgres.py`
- `scripts/import_pilot_data.py`
- `scripts/validate_pilot_data.py`
- `scripts/pilot_import_contract.py`
- `scripts/collect_pilot_import_evidence.py`
- `scripts/collect_pilot_intake_evidence.py`
- `scripts/write_pilot_import_report.py`
- `scripts/write_pilot_intake_report.py`
- `backend/scripts/collect_rc_evidence.py`
- `docs/archive/v1.1/PILOT_IMPORT_EXECUTOR.md`
- `docs/archive/v1.1/REAL_MODEL_PRECHECK.md`
- `pilot-data/README.md`
- `pilot-data/course.template.json`
- `pilot-data/lab.template.json`
- `pilot-data/pilot-manifest.template.json`
- `pilot-data/shared-case.template.json`
- `docs/archive/v1.1/pilot-data/README.md`
- `docs/archive/v1.1/pilot-data/business-signoff.template.md`

另删除三份本机忽略目录中的废弃验证启动器：`.isolation/https-validation/run_browser.py`、`.isolation/https-ip-20260927/run_browser.py`、`.isolation/arm-deploy/20260927/browser-server.py`。它们依赖旧文件库配置、旧 schema 与已删除验证流程；未删除备份配置、资料或远端文件。

同步删除上述已删除模块的 20 个旧 `.pyc` 缓存，没有清理其他模块或第三方缓存。无 SQLite 专用第三方直接依赖需要卸载；保留 Python 标准库、系统公共组件、第三方和浏览器自己的数据库。

## 原 16 个固定 SQLite 模块

| 模块 | 本轮处理 |
|---|---|
| test_migration | 空 PG schema 直接初始化 18；重入校验、已有数据保护 |
| test_enablement_migration | PG DDL/DML 失败原子回滚及重试，现有数据摘要保护 |
| test_development_migration | PG 初始化 14 个真实失败点及成功路径 |
| test_process_recovery | PG 合成数据与继承同一 schema 的真实进程中断测试 |
| test_phase_d_process | PG 合成数据、HTTP 创建与中断/重试测试 |
| test_system_status | PG 只读检查及全表数据摘要保护 |
| test_business_taxonomy | PG UPDATE-only、事务回滚与一致性备份 |
| test_applications | 通过统一 PG fixture 运行原业务测试 |
| test_enablement | PG 发布并发、权限和真实故障回滚 |
| test_enablement_workspace | PG 目录/权限/性能测试；原文件库初始化测试迁为直接 PG |
| test_development_lifecycle | 原 8 项业务测试全部保留，触发器及异常断言迁为 PG |
| test_phase_d_reliability | PG 版本数据对账、触发器故障与恢复 |
| test_partner_delete | PG 外键/全表摘要、审计事务失败保护 |
| test_pilot_import / test_pilot_intake / test_historical_repair | 用户批准，随唯一对应旧工具删除 |

迁移表示现在直接使用 PG，不代表下面所有业务/性能断言已通过。

## 数据影响与剩余文件

运行库保持 schema 18。服务停止期间对 `banfei_agent` 进行了改动前/测试后的 REPEATABLE READ READ ONLY 对账：**35 表、2314 行，全部行数据 SHA-256 一致**，不输出真实内容或凭据。未清空、重建、重新 seed、导入旧快照或更新运行数据；用户/Key/历史/上传资料保留。

只删除两份确认无独有数据的旧文件：`.isolation/runtime/dev/app.db`、`.isolation/postgres-migration/20260908T154122Z/migration-source.db`。它们 32 张表 / 595 行均与仍保留的一致性迁移备份相同，删除前再次验证文件摘要及真实路径，没有 WAL/SHM 文件。

**13 份旧数据库/备份仍保留**，其中 `.isolation/runtime/app.db` 含 1 家伙伴、4 个用户，不能证明没有独有数据；其他文件含历史快照，未用当前 PG 覆盖对比来推断可删除。均脱离运行/测试路径。逐文件理由、历史配置、禁止项和负向测试命中见 [剩余命中清单](POSTGRES_ONLY_RESIDUES_20261001.md)。历史测试报告未改称 PG 通过。

## 首轮清理验证命令与结果（历史记录，收口复测见文末）

使用私有 `BANFEI_TEST_DATABASE_URL`，未打印连接串。构建、开发服务与 Playwright 串行使用 `.next`。

```bash
.venv/bin/python scripts/run_postgres_validation.py backend -q --tb=short
.venv/bin/python scripts/run_postgres_validation.py browser
PLAYWRIGHT_MODEL_MODE=replay .venv/bin/python scripts/run_postgres_validation.py browser <相关用例>
npm run typecheck --prefix frontend
npm run build --prefix frontend
```

- 完整后端复测：**855 passed / 72 failed / 0 skipped / 0 errors**，927 项均标记并实际使用 PostgreSQL 临时 schema；927 项唯一，不是重复累加。耗时 1001.85 秒。
- PG 隔离、配置拒绝、真实回滚与发展生命周期定向复测：**56 passed / 0 failed / 0 skipped**；只选该范围，未把 1 项无关模型消息布局断言计入通过。
- PG 初始化 CLI 缺配置/SQLite URL 拒绝补测：**2 passed**；分类维护工具 PG 备份/事务/保护补测：**21 passed**。
- 脚本测试：**12 passed，15 个 subtests passed**。
- `npm run typecheck`、`npm run build`、Python compileall、`git diff --check`：通过。
- 默认 Playwright：**92 passed / 2 failed / 1 skipped**（8.7 分钟）。两项失败为旧创建接口等待预算断言（1230000ms vs 30000ms）、旧普通 `/login` 页面仍寻找管理员用户名输入。实际 IP 专项因默认 localhost 未运行，随后单独补跑；没有新增 skip。
- 任务导航/统一入口 replay：**13 passed / 0 failed / 0 skipped**（1.7 分钟）；使用同一临时 PG schema 的本地回放供应商，不是真实供应商验收。实际 IP `http://172.21.208.223` 专项 **1 passed / 0 failed / 0 skipped**（22.4 秒），补跑默认组的跳过项；覆盖首次双标签页、Key 恢复/显示/复制回退/下载、退出/切换及错误 Origin 拒绝。浏览器最终按用例去重为 **106 passed / 2 failed / 0 尚未执行的跳过项**（108 项）。

首轮完整执行是 851 passed / 76 failed，另 1 个 teardown error；已修复 PG health-table 夹具、触发器语法/排序及后台执行器先结束再清理 schema，以上使用最后一次完整复测结果。首轮死锁留下的唯一 schema 已通过本轮 JUnit 的精确名称和合成身份只读核验，再仅删除该 schema；未清理其他进程或旧测试遗留 schema。

完整复测的 72 个失败仍保留，没有用 skip/xfail、删除业务测试或降低断言转绿。多项与当前未提交业务改动后的接口/回放桩不一致；本轮没有为使它们通过而修改业务流程，尚不能宣称全量业务验证通过。性能失败也单独保留为明确问题。

| 失败模块 | 数量 | 当前直接失败原因 |
|---|---:|---|
| `test_advisor_ux` | 10 | 追问返回 revise / 后台 Run，而旧断言要求立即返回 explain 或特定正文。 |
| `test_enablement` | 2 | 权限矩阵已逐请求校验，末尾固定路由数量断言仍为 10，实际为 14。 |
| `test_enablement_workspace` | 1 | 3000 条资源下候选检索 p95 为 2.370 秒，未达到原 <2 秒断言；保留阈值。 |
| `test_model_config` | 1 | 无模型匹配接口实际 502，断言期望 503。 |
| `test_model_test_boundary` | 1 | 断言只检查最后一条消息含 schema，实际最后一条为用户消息。 |
| `test_opportunity_extraction` | 1 | 机会重试期望 200/ready，实际 502。 |
| `test_p0_closure` | 1 | 旧匹配单测调用未提供当前函数必需的 snapshot。 |
| `test_partner_delete` | 2 | 迟到匹配用例期望 409，实际 502。 |
| `test_phase_d_model_and_samples` | 8 | 回放供应商首轮未产生 current Version，后续各故障模式未到达目标断言。 |
| `test_phase_d_process` | 1 | 重试 ready 后 current 仍为原版本，旧断言期望新增 Version。 |
| `test_phase_d_reliability` | 5 | PG 触发器及失败不覆盖检查已到达，但重试未产生预期新 Version（含 watchdog）。 |
| `test_recommendations` | 26 | 旧匹配单测未传 snapshot，或新任务断言依赖旧匹配桩。 |
| `test_task_failures` | 3 | 匹配配置/新调用链使超时等注入未到达预期，错误类别或成功状态不同。 |
| `test_user_cleanup` | 4 | 理解期间删除与先落库后台执行存在旧断言冲突：创建已返回 202，或实际错误码与 401 预期不同。 |
| `test_v12_agent` | 6 | 旧追问同步答复、无需 Run 的断言与当前接口/测试桩不一致。 |

浏览器原始记录为 `/tmp/banfei-pg-ui-final.xml`、`/tmp/banfei-pg-replay-final.xml`、`/tmp/banfei-pg-http-ip-final.xml`；默认组失败 trace/截图保留在 `/tmp/banfei-pg-ui-results`。

原始本机记录位于 `/tmp/banfei-pg-final-fixes.xml` / `.txt`、`/tmp/banfei-pg-safety-final.xml`、`/tmp/banfei-pg-taxonomy-final.xml`、`/tmp/banfei-pg-cli-final.xml`、`/tmp/banfei-pg-script-tests.xml`。构建与类型检查记录 `/tmp/banfei-pg-build.txt`、`/tmp/banfei-pg-typecheck.txt`。这些记录只属于本机本轮，不是远端验收证据。


## 首轮清理边界与状态（历史记录）

浏览器在 WSL Chromium，以及现有用例中的 Linux Chrome/Edge 执行；不是 Windows Edge 或 ARM 验收。未执行真实供应商业务模型验收、未部署 ARM。完整后端和浏览器仍存在上述失败，不能宣称“全部清理并验证通过”。

本机原有服务在测试结束后通过 `bash enablement-dev.sh start` 恢复，唯一对外入口为 HTTP 80。最终状态：Caddy、Next.js、FastAPI 均正常；仅对外监听 80，3000/8000 为 127.0.0.1 回环，没有 443/18180 测试监听。实际 IP `/api/health`、`/login`、`/icon.svg` 返回 200。服务恢复后再次对账 35 表 / 2314 行，全部数据摘要仍与开始时一致。

Git 保持 main / `b63a9035ebec63648ade23e89158072f2ecae384`；工作区仍有原先及本轮未提交改动，没有 commit、push 或远端部署。


## 剩余验证收口（2026-10-01，本机测试已完成）

本轮在原 main 工作区继续修改，没有切分支、提交、推送、部署或覆盖已有改动。原先 72 项失败及浏览器失败记录原样保留在上文；本节的最终数字只计最后一份代码的完整运行，不累加定向回归次数。

### 共同根因与修复

- **测试适配**：匹配桩改为当前需求理解 / 初选 / 详评协议，并提供真实保存的 snapshot、模型配置和资料指纹。旧返回字段的数值、身份和引用规范化测试直接调用仍被产品使用的验证边界；完整链路另由严格 envelope 和三阶段测试覆盖，未放宽产品 schema。
- **测试适配**：发展回放桩读取当前独立 message；解释等到后台 Run 完成后断言完整答复、历史和版本指针。修改失败、中断恢复的测试改用现有 retry API，检查复用失败输入与该 Run 实际生成的 Version，不把新发一句“重试”当作执行重试。供应商故障桩的连接配置保存于隔离 PG，使固定模型校验通过后才进入目标故障；八种模式均检查实际供应商请求。
- **测试适配**：在实际 HTTP 请求的全部消息中核对完整 schema；管理员走 `/admin/login`，普通身份测试保留；资源管理权限测试枚举并逐一校验 14 个 method/path（分类、导入、导出、批量、发布和权限），包含后续新增方法检查，不再只比较数量。删除保护按创建已提交的真实时点检查：运行中用户不可删除，首轮失败记录仍保留。
- **真实代码缺陷**：首轮模型配置异常被统一变成 502，已恢复 503；推荐伙伴已删除导致的保存冲突被统一变成 502，已恢复 409。真实原因继续进入原有脱敏错误日志，失败任务和已有结果保留。
- **真实代码缺陷**：明确只问原因、比较的追问若被模型误判为修改，原来缺少矛盾校验。统一理解增加有限的校验保护，拒绝该矛盾输出且不产生 Version；明确同时要求修改的问题仍允许修改。不合成答案、不额外调用模型。按本轮要求在“系统状态 → 最近错误”复用既有 RecentErrors 组件与管理员接口，任务报错入口保持同一日志来源。
- **真实界面缺陷**：管理员返回用户区后，普通身份首次创建成功但视图重挂载会先恢复会话，丢失仅由 `adopt()` 写入的 Key 保存提醒。创建成功即保存现有 pending 提醒标记；不更换用户、Key、Cookie 或登录方式。原失败浏览器用例保留并验证普通身份和提醒。
- **测试时序缺陷**：进程恢复测试用供应商延迟间接等待没有模型调用的完善阶段，50ms 轮询会漏掉已经完成的短暂状态。改为仅在隔离子进程的真实 `_run_task_enrichment` 入口阻塞，确认推荐已提交和进入标记后终止；恢复仍启动未注入的正常服务，断言原任务、原结果及重试完成。
- **真实性能缺陷**：候选读取原来逐条查询资源 head/version、正式标签与分类，网络往返随 3000 条资源增长。现改为同一只读快照内批量读取并复用单条引用的权限投影；所有候选参与原有过滤/打分/排序，仍返回原来的前 100 项，无外部缓存、模型调用或新检索平台。

### 验证约束与证据

- 运行库、入口及私有环境不参与 seed/故障注入；仅专用验证库各自的临时 schema。pytest 网络边界仅允许回环，模型响应使用合成桩或本机 HTTP 回放供应商。
- 创建请求仍采用 30 秒传输等待预算，实际 HTTP 验证要求小于 1 秒；后台模型执行独立沿用原配置预算，未把两者混为 1230000 毫秒。
- 首轮模型阻塞时的真实 HTTP 验证包括：两类任务返回 202 与 ID，独立 PG 连接可见、列表和详情可查；并发 3 次及丢失响应重发只有一个任务、一次调度；模型等待期间同 schema 写锁可取得。创建失败用真实 PG 触发器验证全事务回滚和零模型调度。另执行真实进程“提交后、执行前”终止/重启恢复。
- 解释/比较在 Run ready 后核对 answer、current/confirmed 与 Version 数量；初次失败重试核对保存版本关联 retry Run；修改失败重试核对修改后的条目、其余条目保持不变、current 前进、confirmed 保留，重复成功执行不新增版本。已有结果、用户停用/删除、伙伴删除、归属与旧执行迟到保护继续由全量回归覆盖。
- 性能独立复现为 p95 **2.151 秒**（原记录 2.370 秒），未放宽 `<2 秒` 门槛。最终性能记录同时保留 3000 条资源、30 次候选检索、60 次目录查询、SQL 次数/耗时与剩余处理耗时。SQL 耗时包含绑定和执行；剩余时间包括结果读取、投影、过滤、排序及上下文管理，不含造数、模型或浏览器。
- [被测输入清单](evidence/pg-only-20261001/workspace-manifest.json) 记录基线 commit **及未提交工作区的实际内容 SHA-256**；排除会随验证写入的 `docs/validation/`、`artifacts/` 和 Git 忽略的运行/私有/构建文件。测试结束再次核对输入指纹一致；最后结果、真实模型补测与运行数据保护核验见文末。


收口过程中的完整批次也保留：一次因补齐浏览器适配而主动中断（361 项已通过，不计最终结果）；随后一次 **940 passed / 1 failed**，唯一失败为完善阶段的进程测试错过短暂状态（实际已 `ready`，不是任务消失）。故障点阻塞修复后定向两项进程测试通过，随后重新启动最终完整批次；不以单独补跑替代最终全量结果。


### 自动导航测试修正前的完整批次（最终复跑见下节）

该批输入清单为 [workspace-before-auto-navigation.json](evidence/pg-only-20261001/workspace-before-auto-navigation.json)，SHA-256 为 `f6c8ca4294221553e051f5ceb9eb7dec94cfb0685a44ea90e8a5d5ba4d41ddf8`（416 个文件/删除标记）；不是只用基线 commit 代表未提交代码。最终后端结束后复核该指纹一致。

- 完整后端 PG：**941 passed / 0 failed / 0 errors / 0 skipped**，867.85 秒；原发展生命周期 8 项全部保留并通过。2 条依赖弃用 warning（PyPDF2、Starlette 422 常量），没有故障或跳过。
- 脚本：**12 passed，15 subtests passed**；typecheck、build、`git diff --check` 均通过。PG 隔离、直接初始化、配置拒绝、真实触发器/DDL 回滚及并发测试已包含在完整后端中，不额外累加。
- 真实 HTTP 阻塞模型验证：伙伴匹配 3 次并发创建返回耗时 **61.5–69.7ms**；能力发展 **71.2–76.5ms**。两类均返回 202，独立 PG 可见、列表/详情可查、同提交只有一个任务/一次调度；模型等待时同 schema 写事务锁可取得。丢失响应重发不重复调度，模型释放后真实 timeout 写回原任务。
- 3000 条资源：候选检索 30 次 p50 **0.196 秒**、p95 **0.474 秒**、最大 **0.518 秒**，每次 4 次 SQL；SQL 平均 **0.032 秒**，其余处理平均 **0.193 秒**。目录查询 60 次 p95 **0.064 秒**。原 `<2 秒` 门槛与计时范围保留，造数不进入计时，全部资源参与原筛选。

该批后端原始证据：[backend-before-auto-navigation.xml](evidence/pg-only-20261001/backend-before-auto-navigation.xml)。最终工程记录另见下表。941 条后端用例均附带 `database_backend=postgresql` 标记，逐项临时 schema 由受保护的 PG fixture 创建和清理；HTTP 创建时间和完整性能样本直接保存在 JUnit properties。


最后一轮浏览器默认组发现 **93 passed / 1 failed / 1 skipped**：`accepted matching timeout recovers original task after HTTP 502` 仍点击首页的临时“查看任务详情”链接，实际页面已自动进入原任务详情。失败轨迹显示 `/tasks/<原 requestId>`、失败提示和可用重试按钮；不是任务消失或需要扩大创建等待时间。三个状态用例统一改为直接等待自动导航，并在已选中侧栏条目核验“生成失败，可重试”，继续检查 pending 清理、原任务单次提交与单次重试；不降低业务断言。第一步适配还保留了首页 `.current-task-summary` 定位，三项因此明确失败；随后定位到实际选中的任务行，三项均通过。完整失败记录和中间记录均保留，未通过盲目重跑选取通过。

证据：[浏览器完整批次](evidence/pg-only-20261001/browser-before-auto-navigation.xml)、[失败页面](evidence/pg-only-20261001/browser-auto-navigation-failure.png)、[适配中间记录](evidence/pg-only-20261001/browser-navigation-adapter-intermediate.xml)、[适配后 3 项](evidence/pg-only-20261001/browser-navigation-adapter-final.xml)。此前 941 项全部通过的后端批次保留为 [backend-before-auto-navigation.xml](evidence/pg-only-20261001/backend-before-auto-navigation.xml)。因测试文件内容变化，重新冻结全部输入并重跑后端、浏览器、类型检查、构建及脚本，不将前一指纹的结果直接计作最后结果。

### 最终验证

最终被测输入 SHA-256：`c5e404f8b974bdddeaae4b8d5d59c05e74dc2fd1a58839faf344a91a5a75050b`，完整清单见 [workspace-manifest.json](evidence/pg-only-20261001/workspace-manifest.json)。

已完成最终指纹下的任务导航/统一入口 replay：13 passed，0 failed/skipped；实际 IP HTTP 专项：1 passed，0 failed/skipped。原始记录见 [browser-replay-final.xml](evidence/pg-only-20261001/browser-replay-final.xml)、[browser-ip-final.xml](evidence/pg-only-20261001/browser-ip-final.xml)。


| 最终范围 | 实际结果 | 原始记录 |
|---|---|---|
| 完整后端 PG | **941 passed / 0 failed / 0 errors / 0 skipped**，1037.30 秒 | [JUnit](evidence/pg-only-20261001/backend-final.xml)、[日志](evidence/pg-only-20261001/backend-final.txt) |
| 默认 Playwright | **94 passed / 0 failed / 1 skipped**，8.8 分钟；默认 localhost 跳过实际 IP 用例 | [JUnit](evidence/pg-only-20261001/browser-default-final.xml)、[日志](evidence/pg-only-20261001/browser-default-final.txt) |
| 任务导航 / 统一入口 replay | **13 passed / 0 failed / 0 skipped**，114.28 秒 | [JUnit](evidence/pg-only-20261001/browser-replay-final.xml) |
| 实际 HTTP IP | **1 passed / 0 failed / 0 skipped**，29.19 秒 | [JUnit](evidence/pg-only-20261001/browser-ip-final.xml) |
| 浏览器按 classname/name 去重 | **108 passed / 0 failed / 0 尚未执行项**；实际 IP 用例覆盖默认组的跳过项，只计一次 | [逐用例汇总](evidence/pg-only-20261001/final-results.json) |
| 脚本 | **12 passed / 0 failed / 0 skipped，15 subtests passed** | [JUnit](evidence/pg-only-20261001/scripts-final.xml)、[日志](evidence/pg-only-20261001/scripts-final.txt) |
| TypeScript / Next build / 差异格式 | **全部通过**，构建与开发/浏览器 `.next` 写入串行 | [typecheck](evidence/pg-only-20261001/typecheck-final.txt)、[build](evidence/pg-only-20261001/build-final.txt) |

该最终批次的 941 项全部记录 `database_backend=postgresql`；原发展生命周期 8 项、PG 配置拒绝/直接初始化/真实回滚和隔离保护全部包含其中。2 条依赖弃用 warning 为 PyPDF2 与 Starlette 422 常量，不是 skip/xfail。没有剩余失败用例。

最后一次完整批次性能：3000 条资源、30 次候选检索，p50 **0.269 秒**、p95 **0.622 秒**、最大 **1.055 秒**；每次 4 次 SQL，SQL 平均 **0.046 秒**、其余处理平均 **0.293 秒**。60 次目录查询 p95 **0.103 秒**。保留全部测试资源、有效候选和原 `<2 秒` 门槛；没有通过减少数据或改变计时范围达标。

最后一次真实 HTTP 阻塞验证：伙伴匹配的三次并发请求 **80.4–94.6ms**，能力发展 **85.1–94.5ms**，均为 202 且独立 PG 可见；两类分别只有一个任务和一次调度。固定端口进程测试另检查 50 次 HTTP 创建，p95 **23.3ms**（后台每次合成模型调用延迟 3 秒），保留原 `<1秒` 门槛。数据库创建故障不调度；提交后、执行前进程终止的任务能恢复为 interrupted；解释/比较等待终态后验证 answer 和版本不变；首次生成与修改失败重试均验证实际 Version/Run 关联、current/confirmed、重复执行及迟到结果保护。相关原始 properties 和断言均在最终 JUnit 中。

### 按追加授权执行的真实模型补测

用户在本轮回归期间追加授权“该调真实模型测试就调”。自动化全量测试继续使用合成桩/本机回放；额外一次有限范围检查单独使用当前启用场景的 **api.deepseek.com / deepseek-v4-flash**，不更改运行库模型配置、超时策略或场景绑定。只读取现有连接配置，在专用 PG 临时 schema 中创建合成伙伴、案例与 3 个实验，没有读取或发送真实伙伴业务资料。

预计 8 次请求，设上限 12 次（含自动重试）；实际 **8 次 HTTP 请求，全部 200，8 项业务断言通过**：

- 伙伴匹配 3 次：任务先提交，理解、初选和详评实际调用后推荐合成伙伴，结果正常保存。
- 首次能力发展 2 次：Plan/Run 先提交，生成顺序正确的两个实验，保存有效 Version。
- 解释 1 次：保存有效答复，Version 数量/current 不变。
- 修改理解 1 次：真实理解完成后，在 patch 供应商请求之前受控注入 TimeoutError；失败 Run 保留旧 Version。这个超时是故障注入，不称为真实供应商超时。
- 原任务重试 1 次：复用理解、真实生成局部修改，第二个实验替换成功、第一项原样保留，保存关联重试 Run 的新 Version/current，旧 confirmed 保留。重复成功请求不增加版本和模型调用。

供应商 usage 合计 **输入 20,340 / 输出 3,267 / 总计 23,607 Token**，单请求约 0.827–2.752 秒；未按字符数冒充 Token、未估算账单费用。临时 schema 删除后用 PG catalog 只读确认已不存在。证据：[真实请求与断言记录](evidence/pg-only-20261001/real-model-final.json)、[合成验证脚本](evidence/pg-only-20261001/real-model-check.py)。脚本只记录阶段、HTTP 状态、耗时和 usage，不保存完整 Prompt、资料或 Key。该有限样例不代表所有自然语言问题或全量业务效果验收。

### 运行保护与交付边界

本机服务已按 `bash enablement-dev.sh start` 恢复；唯一入口 **http://172.21.208.223**，Caddy 对外 80，Next/FastAPI 分别为 127.0.0.1:3000 / 127.0.0.1:8000，无 443/18180 监听。实际 IP `/api/health`、`/login`、`/icon.svg` 检查为 200。

最终在服务恢复后对运行库做 READ ONLY 对账：**35 表 / 2314 行全部行摘要不变**；包含私有配置、HTTP 入口配置、上传文件与 **13 份保留备份**在内的 **169 个文件摘要不变**。未清理这些备份，未重建、seed 或替换运行库。见 [数据/文件/端口核验](evidence/pg-only-20261001/runtime-protection-final.json)、[服务状态](evidence/pg-only-20261001/runtime-status-final.txt)。

分支仍为 main，HEAD 仍为 `b63a9035ebec63648ade23e89158072f2ecae384`；保留既有及本轮未提交改动，没有 commit、push、分支操作或远端部署。最终源文件指纹复核不变。Windows Edge 和 ARM 未执行本轮验证；浏览器结果为当前 WSL 环境，未宣称远端或人工业务验收通过。

## 证据归档说明

2026-10-01 提交收口仅整理重复/中间证据及文档引用；正文中的测试结果、源码指纹和当时 Git 状态均保留原口径。原被测清单和证据指纹不重写；已删除文件的原 SHA-256、用途及保留替代证据见[收口记录](GIT_CLOSEOUT_20261001.md)与[清理清单](evidence/cleanup-20261001.json)。
