# PostgreSQL-only 剩余命中清单（2026-10-01）

搜索范围为项目自有源代码、脚本、配置和文档；排除第三方依赖、Python 标准库、浏览器数据、构建缓存和 Git 对象。搜索表达式为 `sqlite|app\.db|LINGJIAN_DATABASE_PATH`，另查旧方言 `PRAGMA / rowid / RAISE(ABORT) / json_extract / BEGIN IMMEDIATE`。应用/脚本/浏览器夹具无可执行兼容分支。负向测试只拦截 SQLite 调用，不创建或连接 SQLite。

下列历史报告及 artifacts 原样保留其数据库类型和结果，不作为当前操作步骤。只服务已删除旧工具的执行手册、模板和脚本已经删除；没有将旧工具移入归档继续保留。

| 文件 | 命中行（清理时） | 保留理由 |
|---|---|---|
| `.gitignore` | 22,23 | 阻止旧数据库/备份被误提交；不是运行配置。 |
| `AGENTS.md` | 99 | 禁止回退/兼容及数据保护说明。 |
| `README.md` | 136 | 禁止回退/兼容及数据保护说明。 |
| `artifacts/enablement-phase-c/http-creation-latency.json` | 5 | 既有历史机器证据/通过数字或文件摘要；保留原始结果，不冒称 PG 通过。 |
| `artifacts/enablement-phase-c/migration-verification.json` | 88 | 既有历史机器证据/通过数字或文件摘要；保留原始结果，不冒称 PG 通过。 |
| `artifacts/enablement-phase-c/protection-verification.json` | 7 | 既有历史机器证据/通过数字或文件摘要；保留原始结果，不冒称 PG 通过。 |
| `artifacts/enablement-phase-c/validation-results.json` | 43 | 既有历史机器证据/通过数字或文件摘要；保留原始结果，不冒称 PG 通过。 |
| `artifacts/enablement-phase-d/backend-test-results.json` | 3173 | 既有历史机器证据/通过数字或文件摘要；保留原始结果，不冒称 PG 通过。 |
| `artifacts/enablement-phase-d/http-creation-latency.json` | 6 | 既有历史机器证据/通过数字或文件摘要；保留原始结果，不冒称 PG 通过。 |
| `artifacts/enablement-phase-d/protection-verification.json` | 7 | 既有历史机器证据/通过数字或文件摘要；保留原始结果，不冒称 PG 通过。 |
| `artifacts/enablement-phase-d/schema-verification.json` | 47 | 既有历史机器证据/通过数字或文件摘要；保留原始结果，不冒称 PG 通过。 |
| `artifacts/enablement-phase-d/validation-results.json` | 122 | 既有历史机器证据/通过数字或文件摘要；保留原始结果，不冒称 PG 通过。 |
| `artifacts/enablement-rc/http-creation-latency.json` | 6 | 既有历史机器证据/通过数字或文件摘要；保留原始结果，不冒称 PG 通过。 |
| `artifacts/enablement-rc/protection-verification.json` | 7 | 既有历史机器证据/通过数字或文件摘要；保留原始结果，不冒称 PG 通过。 |
| `artifacts/enablement-rc/runtime-inventory.json` | 2 | 既有历史机器证据/通过数字或文件摘要；保留原始结果，不冒称 PG 通过。 |
| `artifacts/enablement-rc/validation-results.json` | 105 | 既有历史机器证据/通过数字或文件摘要；保留原始结果，不冒称 PG 通过。 |
| `artifacts/huawei-typography/protection-verification.json` | 31 | 既有历史机器证据/通过数字或文件摘要；保留原始结果，不冒称 PG 通过。 |
| `artifacts/huawei-visual/protection-verification.json` | 31 | 既有历史机器证据/通过数字或文件摘要；保留原始结果，不冒称 PG 通过。 |
| `artifacts/huawei-visual/validation-results.json` | 57 | 既有历史机器证据/通过数字或文件摘要；保留原始结果，不冒称 PG 通过。 |
| `artifacts/pilot-data-intake/protection-verification.json` | 6 | 既有历史机器证据/通过数字或文件摘要；保留原始结果，不冒称 PG 通过。 |
| `artifacts/pilot-data-intake/runtime-inventory.json` | 2 | 既有历史机器证据/通过数字或文件摘要；保留原始结果，不冒称 PG 通过。 |
| `artifacts/pilot-import/protection-verification.json` | 9,10 | 既有历史机器证据/通过数字或文件摘要；保留原始结果，不冒称 PG 通过。 |
| `artifacts/ui-unification/protection.json` | 29,36,43,48,51,54,57,60,63 | 既有历史机器证据/通过数字或文件摘要；保留原始结果，不冒称 PG 通过。 |
| `artifacts/v12/advisor-validation.json` | 226 | 既有历史机器证据/通过数字或文件摘要；保留原始结果，不冒称 PG 通过。 |
| `artifacts/v12/unified-entry-validation.json` | 78 | 既有历史机器证据/通过数字或文件摘要；保留原始结果，不冒称 PG 通过。 |
| `artifacts/v12/validation.json` | 171 | 既有历史机器证据/通过数字或文件摘要；保留原始结果，不冒称 PG 通过。 |
| `backend/tests/test_model_test_boundary.py` | 5 | 负向测试：拒绝 SQLite 与非验证库地址。 |
| `backend/tests/test_postgres_storage.py` | 5,25,26,27,36,160,161,164,194,199 | 负向测试：patch 标准库 connect 为立即失败，证明从不调用 SQLite、从不生成文件。 |
| `backend/tests/test_system_status.py` | 89 | 异常脱敏测试中的合成文件路径，不访问该文件。 |
| `docs/archive/v1.1/FINAL_PILOT_DATA_GAP.md` | 9 | 历史设计、过程或实测记录；已标识非当前执行规范，未改写旧测试数字。 |
| `docs/archive/v1.1/enablement/DELIVERY_REPORT.md` | 31,32,36 | 历史设计、过程或实测记录；已标识非当前执行规范，未改写旧测试数字。 |
| `docs/archive/v1.1/enablement/PHASE_B_STARTUP.md` | 17 | 历史设计、过程或实测记录；已标识非当前执行规范，未改写旧测试数字。 |
| `docs/archive/v1.1/enablement/PHASE_B_VALIDATION.md` | 22,24 | 历史设计、过程或实测记录；已标识非当前执行规范，未改写旧测试数字。 |
| `docs/archive/v1.1/enablement/PHASE_C_DESIGN.md` | 5,9 | 历史设计、过程或实测记录；已标识非当前执行规范，未改写旧测试数字。 |
| `docs/archive/v1.1/enablement/PHASE_C_VALIDATION.md` | 19,22,23,31,92,159 | 历史设计、过程或实测记录；已标识非当前执行规范，未改写旧测试数字。 |
| `docs/archive/v1.1/enablement/PHASE_D_SCOPE.md` | 7,14,25 | 历史设计、过程或实测记录；已标识非当前执行规范，未改写旧测试数字。 |
| `docs/archive/v1.1/enablement/PHASE_D_VALIDATION.md` | 25,35,51,150 | 历史设计、过程或实测记录；已标识非当前执行规范，未改写旧测试数字。 |
| `docs/archive/v1.1/enablement/PILOT_DATA_INTAKE.md` | 76,80,94 | 历史设计、过程或实测记录；已标识非当前执行规范，未改写旧测试数字。 |
| `docs/archive/v1.1/enablement/PILOT_IMPORT_READINESS.md` | 30,47,55,72,88 | 历史设计、过程或实测记录；已标识非当前执行规范，未改写旧测试数字。 |
| `docs/archive/v1.1/enablement/RC_VALIDATION.md` | 10,11,12,40 | 历史设计、过程或实测记录；已标识非当前执行规范，未改写旧测试数字。 |
| `docs/archive/v1.1/enablement/STARTUP_AND_DESIGN.md` | 11,17,21 | 历史设计、过程或实测记录；已标识非当前执行规范，未改写旧测试数字。 |
| `docs/archive/v1.1/legacy-validation/BATCH_4_REVIEW.md` | 22,132,134,159,161,167 | 历史设计、过程或实测记录；已标识非当前执行规范，未改写旧测试数字。 |
| `docs/archive/v1.1/legacy-validation/RELEASE_VALIDATION_REPORT.md` | 23,36,135,204,210 | 历史设计、过程或实测记录；已标识非当前执行规范，未改写旧测试数字。 |
| `docs/archive/v1.1/legacy-validation/VALIDATION_PLAN.md` | 7,13,14,30 | 历史设计、过程或实测记录；已标识非当前执行规范，未改写旧测试数字。 |
| `docs/archive/v1.2/INDUSTRY_REGION_STANDARDIZATION_REPORT.md` | 9,10,12,71,73,200,201 | 历史设计、过程或实测记录；已标识非当前执行规范，未改写旧测试数字。 |
| `docs/archive/v1.2/POSTGRES_MAIN_GIT_CLOSURE.md` | 28,48 | 历史设计、过程或实测记录；已标识非当前执行规范，未改写旧测试数字。 |
| `docs/archive/v1.2/V12_REFACTOR_DELIVERY_REPORT.md` | 21,44,46,67,91,92,104 | 历史设计、过程或实测记录；已标识非当前执行规范，未改写旧测试数字。 |
| `docs/design/HUAWEI_VISUAL_REFACTOR_REPORT.md` | 36 | 历史设计、过程或实测记录；已标识非当前执行规范，未改写旧测试数字。 |
| `docs/handoff/CURRENT_HANDOFF_20260926.md` | 166 | 历史设计、过程或实测记录；已标识非当前执行规范，未改写旧测试数字。 |
| `docs/validation/ACCOUNT_DELETION_VALIDATION.md` | 33 | 历史设计、过程或实测记录；已标识非当前执行规范，未改写旧测试数字。 |
| `docs/validation/DEVELOPMENT_CURRENT_VALIDATION.md` | 21 | 历史设计、过程或实测记录；已标识非当前执行规范，未改写旧测试数字。 |
| `docs/validation/ERROR_HANDLING_VALIDATION.md` | 33,34 | 历史设计、过程或实测记录；已标识非当前执行规范，未改写旧测试数字。 |
| `docs/validation/FEEDBACK_VALIDATION.md` | 23,28,36 | 历史设计、过程或实测记录；已标识非当前执行规范，未改写旧测试数字。 |
| `docs/validation/GIT_CLOSEOUT_20260925.md` | 25,35 | 历史设计、过程或实测记录；已标识非当前执行规范，未改写旧测试数字。 |
| `docs/validation/GIT_CLOSEOUT_20260926.md` | 20 | 历史设计、过程或实测记录；已标识非当前执行规范，未改写旧测试数字。 |
| `docs/validation/GIT_CLOSEOUT_20260929.md` | 19 | 历史设计、过程或实测记录；已标识非当前执行规范，未改写旧测试数字。 |
| `docs/validation/HUAWEI_RESOURCE_IMPORT.md` | 44 | 历史设计、过程或实测记录；已标识非当前执行规范，未改写旧测试数字。 |
| `docs/validation/IDENTITY_KEY_VALIDATION.md` | 46,49,115 | 历史设计、过程或实测记录；已标识非当前执行规范，未改写旧测试数字。 |
| `docs/validation/LOCAL_IDENTITY_VALIDATION.md` | 34 | 历史设计、过程或实测记录；已标识非当前执行规范，未改写旧测试数字。 |
| `docs/validation/MODEL_TIMEOUT_RETRIES_20260929.md` | 35,39 | 历史设计、过程或实测记录；已标识非当前执行规范，未改写旧测试数字。 |
| `docs/validation/PARTNER_MATERIALS_VALIDATION.md` | 25,47 | 历史设计、过程或实测记录；已标识非当前执行规范，未改写旧测试数字。 |
| `docs/validation/PILOT_ARCHIVE_20260925.md` | 36,46 | 历史设计、过程或实测记录；已标识非当前执行规范，未改写旧测试数字。 |
| `docs/validation/RESOURCE_CENTER_VALIDATION.md` | 20,24 | 历史设计、过程或实测记录；已标识非当前执行规范，未改写旧测试数字。 |
| `docs/validation/RESOURCE_TRANSFER_VALIDATION.md` | 20 | 历史设计、过程或实测记录；已标识非当前执行规范，未改写旧测试数字。 |
| `docs/validation/SCOPE_GATE_VALIDATION.md` | 42,48 | 历史设计、过程或实测记录；已标识非当前执行规范，未改写旧测试数字。 |
| `docs/validation/DURABLE_TASK_EXECUTION_20261001.md` | 22 | 前一批未提交改动的历史混合测试结果，保留数据库类型与数量；不改称全 PG。 |

本清单与 `POSTGRES_ONLY_20261001.md` 自身为清理说明，其命中不是兼容实现。

扩展搜索 `PRAGMA` 另命中 `backend/app/routers/local_identity.py:87,168,211`：这是 HTTP 响应头 `Pragma: no-cache`，用于身份响应禁止缓存，与数据库 PRAGMA 无关，必须保留。

## 本机私有文件

四份旧备份配置含历史 `LINGJIAN_DATABASE_PATH`：保留备份原貌，不是当前 environment.json，不被现有启动脚本加载：

- `.isolation/revoked-key-migration/20260924T130411Z/environment.json`
- `.isolation/partner-capabilities/20260926/backup-20260926T022537Z/environment.json`
- `.isolation/runtime/caddy/config-before-20260926T160718024658Z/environment.json`
- `.isolation/runtime/caddy/config-before-20260926T153957121848Z/environment.json`

旧日志和历史 JSON 证据中也可能记录旧地址/文件名；不加载执行、不批量改写或删除敏感日志。当前私有 `.env` 与 `.isolation/runtime/dev/environment.json` 仅移除废弃的文件数据库键，其他配置及密钥保留。三份仅用于旧文件库/历史 HTTPS 的本机浏览器验证启动器已删除；未操作远端文件。

## 保留的旧数据库与备份

通过只读 SQLite 文件核查（审计命令仅在本轮 /tmp 执行，未加入项目），核对真实路径、无符号链接、单一硬链接、无 WAL/SHM，比较全表行数据摘要。下面 13 份均脱离运行/测试路径；不能证明可丢弃的历史数据不盲删。

| 私有/备份文件 | 表数 / 行数 | 保留理由 |
|---|---|---|
| `data/app.db.bak-before-task-hardening-v9-20260904` | 17 / 242 | 历史备份/快照；没有用当前 PG 覆盖核实其全部历史独有内容。 |
| `.isolation/postgres-migration/20260908T161533Z-apply/sqlite-consistent-backup.db` | 32 / 595 | 保留迁移一致性证据；另两份删除文件已核对为其 32 表 / 595 行完全相同副本。 |
| `.isolation/postgres-migration/20260908T152706Z/source-backup.db` | 32 / 597 | 历史备份/快照；没有用当前 PG 覆盖核实其全部历史独有内容。 |
| `.isolation/postgres-migration/20260908T154122Z/before-approved-deletion.db` | 32 / 597 | 历史备份/快照；没有用当前 PG 覆盖核实其全部历史独有内容。 |
| `.isolation/backups/before-registration-fields-20260907-231009.db` | 32 / 592 | 历史备份/快照；没有用当前 PG 覆盖核实其全部历史独有内容。 |
| `.isolation/runtime/app.db` | 34 / 47 | 含 1 家伙伴和 4 个用户，未证明无独有内容；不被运行或测试引用。 |
| `.isolation/runtime/dev/pre-advisor-ux.db` | 32 / 515 | 历史备份/快照；没有用当前 PG 覆盖核实其全部历史独有内容。 |
| `.isolation/runtime/dev/pre-v12-20260907.db` | 32 / 341 | 历史备份/快照；没有用当前 PG 覆盖核实其全部历史独有内容。 |
| `.isolation/runtime/dev/taxonomy-backups/before-20260908T032945278330Z.db` | 32 / 594 | 历史备份/快照；没有用当前 PG 覆盖核实其全部历史独有内容。 |
| `.isolation/snapshots/baseline.db` | 17 / 269 | 历史备份/快照；没有用当前 PG 覆盖核实其全部历史独有内容。 |
| `.isolation/snapshots/phase-d-pre.db` | 32 / 270 | 历史备份/快照；没有用当前 PG 覆盖核实其全部历史独有内容。 |
| `.isolation/snapshots/phase-b-pre-v11.db` | 24 / 269 | 历史备份/快照；没有用当前 PG 覆盖核实其全部历史独有内容。 |
| `.isolation/snapshots/phase-c-pre-v12.db` | 25 / 269 | 历史备份/快照；没有用当前 PG 覆盖核实其全部历史独有内容。 |
