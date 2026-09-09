> **历史归档，不是当前开发规范。** 保留当时的需求、环境、测试和结论；旧品牌、分支、端口、数据库及授权状态均不代表当前 main。历史命令不可直接用于现有运行库。当前入口：[README](../../../README.md)。

# Pilot Package 原子导入工具

本工具只用于独立环境的开发与验收。产品页面、API、业务服务、权限和 schema 不变。**当前真实包 NOT PROVIDED；DATA-01 BLOCKED；真实模型 NOT AUTHORIZED / 0 CALLS。**

## 操作顺序

以下是收到真实包且获准导入后的命令契约，本轮只用 `/tmp` synthetic fixture 测试，没有对独立业务 runtime 库执行导入。占位参数由实际批准的数据包与管理员替换，不能用模板值凑正式数据。

```bash
# 1. SQLite 官方一致性备份：仅创建全新的 Pilot DB，不覆盖已有目标。
.venv/bin/python scripts/import_pilot_data.py prepare \
  --source-db .isolation/runtime/app.db \
  --database '.isolation/pilot/<pilot>/app.db'

# 2. 只读检查；VALID 是机器结构结论。
.venv/bin/python scripts/import_pilot_data.py dry-run \
  '.isolation/pilot-intake/<package>/manifest.json' \
  --database '.isolation/pilot/<pilot>/app.db' \
  --package-id '<approved-package-id>'

# 3. 单事务导入；明确批准执行导入的 active admin。
.venv/bin/python scripts/import_pilot_data.py apply \
  '.isolation/pilot-intake/<package>/manifest.json' \
  --database '.isolation/pilot/<pilot>/app.db' \
  --package-id '<approved-package-id>' --actor-user-id '<approved-admin-id>'

# 4. 原包保持不变，用账本解析实际 ID/版本与系统审计。
.venv/bin/python scripts/validate_pilot_data.py \
  '.isolation/pilot-intake/<package>/manifest.json' \
  --database '.isolation/pilot/<pilot>/app.db' --imported \
  --import-ledger '.isolation/pilot/<pilot>/imports/<approved-package-id>/import-ledger.json' \
  --real-model-precheck
```

模型前检当前必然 BLOCKED。上述任一命令都不会调用模型，也不会创建模型绑定。业务原件留在 `.isolation/pilot-intake/`，账本/快照留在 `.isolation/pilot/`，均不进 Git。先停止目标 Pilot 环境其他写入；不停止稳定 3000/8000。工具使用文件锁串行化同类执行器，并用 SQLite 写事务排除其他写事务，不假定产品服务会遵守工具文件锁。

package_id 是本地导入标识，通过参数提供，不向原 manifest 添加字段、不增加第二套业务模型。仅允许 1–80 个 ASCII 字母/数字/点/下划线/连字符，首字符必须为字母或数字。输入目录不能包含输出数据库；业务签审原件及包内其他证据一并纳入 SHA。

## 安全边界

- apply/dry-run 只接受 worktree `.isolation/pilot/<pilot>/app.db`，测试另允许 `/tmp/.../pilot/<pilot>/app.db`。稳定目录、runtime、schema 非 12、symlink/hardlink 均拒绝。
- prepare 只读独立源库，调用 `Connection.backup()`，绝不 `cp app.db`。仅新生成的副本/快照转换为独立 DELETE journal 文件；源库 WAL 数据纳入一致性复制且源库 journal 模式不变。
- apply 要求明确 actor_user_id，校验当前库中 role=admin、status=active 且未处于登录锁定期。CLI 是受信任内部管理员离线工具，不增加对外身份认证入口。
- 原包 reviewer_id/reviewed_at/review note 是业务来源证据。真正 Review 与 audit 使用执行管理员和系统时间。后台实际 Review 的 note 标明 Pilot import，原核验信息单独存入账本，不能假冒历史后台审计。
- 使用现有 schema、check_tags/check_case、save/permissions/review/publish/resolve_reference 和完整 validator。只读 imported 核验允许管理员检查已发布但系统隐藏的资源，仍校验当前版本、epoch、归属、全部权限与快照；不会放开产品资源访问。
- 原始 signed JSON 一字不改，新 resource_id、version、实际 review 等只写账本。未知条件保持原值，不补充猜测。

## 单事务与既有规则复用

现有 service 函数各自请求 BEGIN IMMEDIATE。工具创建隔离的函数命名空间，复用相同函数字节码和 Pydantic 类，只向该命名空间提供连接适配：其 BEGIN 请求加入外层已存在的事务。既有产品模块全局 get_db/函数不被 monkeypatch，不对业务规则做宽松复制。

apply 的唯一事务：BEGIN IMMEDIATE → actor/来源校验 → baseline/integrity/FK/count → 一致性 snapshot → 逐条 save、permissions、实际 review、publish → ledger → imported 复核 → COMMIT。

备份使用第二个只读连接读取同一已提交基线；外层事务此时尚未修改数据但已取得写保留锁，避免备份到校验之间出现另一写事务。不能在已写入事务的同一个连接上调用 backup 导致等待。

所有资源、版本、能力映射、共享配置、Review、分项操作审计记录（最小三资源包为 12 条，每条资源 4 个事件）与事务账本均在一个连接中。任一步失败 rollback；不存在“前两条成功留下、第三条失败”的结果。

## 幂等与账本

不新增表，不升级 schema。在既有 app_metadata 中，以 `pilot_import:<package_id>` 保存事务账本。该元数据行和业务记录一同提交，是原子性与幂等的权威依据；文件不是判定“是否导入”的唯一依据。

- 相同 id + 相同包 SHA：重新只读验证后返回 already_imported，沿用 import_id；不创建新资源/版本/Review。
- 相同 id + 不同包 SHA（包括 signoff 改变）：PACKAGE_ID_HASH_CONFLICT，需新的包 revision/id。
- 首版仅创建：新课程/实验 source_id/source_version 必须 null；case_id 必须既有且有效，但尚不存在共享配置，source_version=null。任何现有资源更新或共享配置覆盖均拒绝。dry-run 按首次创建规则检查；已成功包的幂等重放使用 apply，不将重复创建冲突改为更新。

文件位置：`<pilot>/imports/<package_id>/import-ledger.json`，仅私有留存。包括 package_id/hash、manifest hash、全部输入文件哈希、import_id、时间、actor、目标 DB 路径/inode/device、主文件及 WAL 哈希、快照哈希、实际资源/共享版本、Review ID/实际 actor/time、能力映射、revision/authorization_epoch、三维权限、原始核验来源、before/after 全表计数与精确 FK 异常行、事务和机器验证结果。business_signoff_status 固定 NOT RUN，表示导入器未作业务适配判断，即使包中存在签审原件也不自动改为 PASS。

数据库自包含账本不能保存包含自身的最终 DB hash（会形成自引用）；事务内保存前态与 snapshot 哈希，提交后文件另记录 postcommit 主文件/WAL 哈希。SHM 是连接协调数据，不作为业务快照哈希。仅导入后带 ledger 的 validator 才将含签审文件的完整 package hash 用于下一轮门禁；原 JSON 清单摘要另保留 input_manifest_files_sha256。

## 验证与失败恢复

提交前检查：当前 ID/版本、能力标签及 map、Review/实际 actor/time、权限与 published snapshot、case 归属/epoch、完整路径、资源缺口、integrity 和精确 FK 异常集合。既有异常按具体表/行/引用键保留；即使异常数量相同但具体行变化也失败，不借导入修复旧异常。

COMMIT 后重新打开只读连接，调用 `validate_pilot_data(imported=True)`，并核对 integrity 与 FK 差异。只有这一检查通过才写 machine_import_status=PASS 的外部账本。

数据库事务和文件系统 rename 不能组成同一个 SQLite 事务，因此：

- 提交前失败：整包回滚，业务表/审计/事务账本均回到 before；保留私有一致性 snapshot 供检查，不生成成功 ledger。
- DB 已提交、文件写出失败/进程在写出前退出：明确返回 COMMITTED_REQUIRES_LEDGER_RECOVERY_OR_POSTCHECK_REVIEW；不能声称 DB 已 rollback。再次相同 id/hash apply 从事务内账本恢复文件，先复核、无重复资源。
- 已提交后的只读验证失败（例如外部管理员已撤权）：不报告成功、不自动覆盖数据库或其他管理员变更。停止此 Pilot 环境继续写入，审查事务账本和 snapshot；恢复演练使用 snapshot 经 backup 创建**新的**独立 Pilot DB并复核，绝不直接覆盖运行中的库。
- 现有 ledger 文件与 DB 账本冲突或已篡改：拒绝覆盖，保留证据供审查。新输出目录与文件均检查链接，避免把账本/快照写到旧目录。

## synthetic 验证不等于真实数据验收

生产脚本没有 --allow-synthetic。公开 dry-run/apply 始终拒绝标记为 synthetic 的同一测试包。自动化事务测试仅在 pytest 中暂时替换这两条来源拒绝结果，以运行实际保存/发布/权限/事务检查；所有其他校验继续执行，测试库只能在 /tmp，socket 与模型 completion 被阻断。该测试替换不会进入 CLI、模型授权或业务签审链路。

最小真实路径、数据适配、实验难度、案例价值、业务逻辑仍由业务负责人确认。当前能接收并安全导入未来获准的真实包，不代表已有真实数据、已调用真实模型或真实业务验收通过。
