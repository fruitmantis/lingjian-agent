## 结论

**READY FOR REAL PILOT PACKAGE IMPORT**。

本轮补齐原子导入执行能力，未引入新产品功能、未导入真实资源、未向独立业务运行库填入测试记录。

| 维度 | 结论 |
|---|---|
| 本地导入工具 | dry-run / apply / 一致性 prepare 已实现并完成 synthetic 工程验证 |
| schema | 仍为 12，表/列/约束及迁移代码均未变化 |
| 真正 Pilot Package | NOT PROVIDED |
| DATA-01 | BLOCKED，机器导入不替代业务负责人签审 |
| BUSINESS ACCEPTANCE | NOT RUN |
| REAL MODEL PRECHECK | BLOCKED |
| REAL MODEL | NOT AUTHORIZED / NOT RUN / **0 CALLS** |

## 实现与范围

新增 `scripts/import_pilot_data.py` 和 `scripts/pilot_import_contract.py`；扩展既有 `scripts/validate_pilot_data.py` 的 `--import-ledger` 只读核验；新增 `backend/tests/test_pilot_import.py`。说明见 `PILOT_IMPORT_EXECUTOR.md`。只调整开发/验收工具及文档，没有修改 backend/app、frontend、Development Plan、模型输出、伙伴外发视图或后台页面。

复用现有 ResourceSave/ShareSave、Permissions、Review、Revision，以及 save/permissions/review/publish、标签/案例归属校验和 resolve_reference。单事务适配提供隔离命名空间，原产品函数及全局 get_db 保持原状；没有复制一套宽松导入规则，没有全局 monkeypatch 产品连接。

只在既有 app_metadata 中增加每次导入的 `pilot_import:<package_id>` 元数据行，和资源/版本/Review/审计同事务提交；没有新增表、迁移或第二套权限/业务数据模型。

## dry-run / apply

- dry-run 仅读取包和目标 Pilot DB，调用原 validator，检查 schema、partner/case/正式标签、核验、权限、路径、缺口、合成数据标记；返回 VALID/INVALID，原 DB 文件 hash、全表计数与输入文件 hash 不变。
- apply 只允许 worktree `.isolation/pilot/<pilot>/app.db` 或 `/tmp/.../pilot/<pilot>/app.db`。拒绝 runtime、稳定目录、v9、链接、已有资源覆盖和已有共享配置更新。
- 强制 --actor-user-id；校验当前 active admin 且未锁定。输入声明的原 reviewer/time 留作来源证据；真正 Review 和 audit 使用实际执行管理员及当前系统时间。测试明确使用不同的来源核验人和执行管理员，验证不会冒名或伪造历史时间。
- 外层一个 BEGIN IMMEDIATE；最小课程+实验+共享案例包涉及资源、正式版本、能力 map、权限、Review、发布状态和分项审计，全部使用同一 connection。trace 测试实际记录到 **1 次 BEGIN IMMEDIATE / 1 次 COMMIT**。

## 输入不可变、账本与幂等

原 manifest/JSON/signoff 保持原始 SHA，未回填 ID 或覆盖签审字段。完整 package SHA 覆盖目录内所有输入证据，另保存 manifest SHA 与逐文件 SHA。实际 ID/Version、case 共享版本、Review ID/实际人和时间、能力映射、revision/epoch、三维权限、原核验来源、before/after 计数/FK、DB 路径/inode/主文件/WAL hash 与快照 hash 均在私有 ledger 中。

事务内 app_metadata 账本为权威记录；提交后生成 import-ledger.json。外部 ledger 不能伪造绑定：validator 会逐项核对其 transaction 与当前数据库中的原子记录，然后对不可变原包重新校验。

- 相同 package_id/hash：already_imported，同 import_id，无重复资源/版本/审计。
- 同 id 不同内容或 signoff hash：拒绝 PACKAGE_ID_HASH_CONFLICT。
- 不同包指向现有 resource_id 或 case share config：首版仅创建，明确拒绝覆盖。
- machine_import_status 与 business_signoff_status 分离；后者始终 NOT RUN，表示导入器没有进行业务适配签审。

## 备份、回滚与恢复

实际使用 SQLite Connection.backup()，不是复制运行中的单个文件。apply 在取得写保留锁、尚未写入数据时，通过第二个只读连接生成一致性 before snapshot，避免备份基线和后续事务之间出现另一写事务。

备份前后核对 schema/integrity、全表计数和**精确 FK 异常行集合**。新增私有 snapshot 规范化为独立 DELETE journal 文件，不改变源库模式。WAL 测试证明：仅存在于已提交 WAL、尚未 checkpoint 的内容完整进入新副本，源主文件和 WAL hash 不变。

11 个事务内故障点：第一条课程、Resource Version、capability map、Review、资源发布、Lab、Case Config、Case Version、共享发布、最终 ledger 前、COMMIT 前。每处均断言所有表计数、完整 FK 异常集合与 DB 文件 hash 回到 before；无遗留 draft/版本/map/Review/共享配置/审计/导入元数据。私有 before snapshot 保留，不冒充成功 ledger。

额外注入：新增 FK、异常总数相同但具体行变化、丢失能力 map、提交前输入被外部改变，均拒绝并回滚。

SQLite 不能把外部文件写入与 DB COMMIT 组成一个事务：若 DB 已成功提交但 ledger 文件写出失败，明确返回“已提交，需要账本恢复/复核”，不声称已 rollback。相同 id/hash 重放从事务内记录恢复文件，不增加业务行；已完成该故障测试。文件内容冲突拒绝覆盖。

COMMIT 后另开只读连接运行 imported validator、integrity 与 FK 差异验证，通过后才在文件标 machine_import_status=PASS。若提交后外部撤权等导致复核失败，停止继续操作，不自动覆盖别人变更。恢复演练从一致性 snapshot 创建新的私有 Pilot DB，校验与原 before 相同，绝不覆盖正在运行的数据库。

## 测试与证据

实际执行：

```bash
.venv/bin/python -m pytest backend/tests/test_pilot_import.py backend/tests/test_pilot_intake.py backend/tests/test_enablement.py -q --junitxml=/tmp/pilot-import-regression.xml
.venv/bin/python -m py_compile scripts/import_pilot_data.py scripts/pilot_import_contract.py scripts/validate_pilot_data.py scripts/collect_pilot_import_evidence.py scripts/write_pilot_import_report.py backend/tests/test_pilot_import.py
.venv/bin/python scripts/collect_pilot_import_evidence.py /tmp/pilot-import-regression.xml
git diff --cached --check
```

最终 **131 passed / 0 failed / 0 errors / 0 skipped**：导入器 51、原 Intake 37、现有资源服务 43。脚本语法检查通过。未改 UI 或产品代码，本轮未运行无关全量后端/Playwright/typecheck/build，未启动浏览器、新端口或模型服务。

覆盖所有要求的入口拒绝、角色、资料引用、发布/Review、8 种三维权限组合、unknown 保留、原子成功、11 个失败点、幂等/不同 hash 冲突、ledger、immutable input、imported 验证、runtime/stable 保护。socket.connect 与 model completion 在测试中直接阻断，稳定/实际 runtime SQLite 连接也被测试保护钩子拒绝。

**synthetic 边界**：事务测试明确使用 package_kind=synthetic、/tmp 目录和 synthetic signoff。仅测试进程临时替换来源拒绝项来执行成功事务路径，其余校验保持真实执行；工具没有 synthetic 放行参数。公开 CLI 与原 validator 对同一包拒绝，不能用于通过真实数据真实性或模型门禁。即使 synthetic 结构事务成功，真实模型前检仍为 BLOCKED。

机器证据：

- `artifacts/pilot-import/validation-results.json`：实际计数、全部用例、JUnit hash、工具/测试源 SHA。
- `artifacts/pilot-import/readiness.json`：故障点、事务/备份/幂等/权限和阶段门禁。
- `artifacts/pilot-import/protection-verification.json`：Intake tag、main、进程、runtime/stable 保护。

没有提交数据库、快照、真实 Pilot Package、签审原件、私有 import ledger 或原始运行日志。测试数据只存在 /tmp fixture；脱敏机器证据不含实际业务材料或凭据。

## 稳定版与运行库保护

Intake ready 标签固定在 `dda1af4914aec68f96cd0ae481caae732eea655d`；RC accepted tag 仍指向 `1a0b4b4f081de63c617b366788e19d0090d19093`。main 保持 `f79cbb29ec7b3ad70c88e618e3161211f211c06a`，稳定工作区 clean。

167 个稳定保护文件 hash 未变；独立 `.isolation/runtime/app.db` 与本轮开始 hash 一致。本轮未打开这两处 SQLite，只做文件 hash；未认证、创建 session、更新 last_login/audit 或运行迁移。临时 fixture 的 runtime 副本同样逐测试核验未变。

原 3000/8000 进程/cwd 保持；新版 3100/8100/mock 未启动，保持停止。未 push、merge、rebase、deploy，不声称已核验 GitHub 远端同步。

## 尚待真实数据与后续授权

当前真实 Pilot Package 尚未提供，因此没有真实数据导入结果，DATA-01 与业务适配签审仍 BLOCKED/NOT RUN。课程适用性、实验难度、案例学习价值及路径业务逻辑必须由业务负责人确认。

真实模型仍未授权，本轮真实调用 **0**，未修改任何稳定或日常运行模型配置；批准测试模型绑定、预算审计运行器与数据用于模型测试的签审仍是独立门禁。收到真实包后只按本工具创建独立 Pilot DB 并受控导入，不据工程成功宣布业务上线。

本轮停止，等待真实 Pilot Package。
