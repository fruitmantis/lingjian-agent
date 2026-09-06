# 真实试点数据接收门

此目录只有空白模板，**不含正式业务数据**。唯一权威输入格式为 JSON；课程、实验与共享案例采用现有嵌套产品 schema，不另建 CSV/YAML 版本。Markdown 只记录说明和签审，不参与业务字段导入。

```text
pilot-data/
  README.md
  pilot-manifest.template.json
  course.template.json
  lab.template.json
  shared-case.template.json
  business-signoff.template.md
```

收到数据后，将这套模板复制到独立 worktree 的 `.isolation/pilot-intake/<package>/`，由业务方填写并保存原始签审材料；不在这个受版本控制的目录填真实材料。manifest 的 resources/shared_cases 引用同一包目录中的 JSON 文件，可增加多条同类资源，禁止绝对外部路径、软链接、硬链接及目录逃逸。模板中的空字符串、null、package_kind=template 必然不能通过正式数据预检；不得为了通过改标签或补造内容。

## 最小包

一个试点能力方向（request.targets 中现有正式标签）+ 一家真实启用伙伴（request.target_partner_id / target_partner_name / allowed_diagnostic_scope）+ 明确目标、参训对象/人数/个人基础、周期投入与硬约束 + 同一目标能力至少一门课程、一个实验、一个获授权的既有案例独立共享版本。三类资源必须经业务方认可组成路径。公司画像不能替代参训人员能力；允许诊断资料范围是本地审批说明，不是原附件发送授权。

缺课程/实验/案例时，在 resource_gaps.items 登记 capability_tag_id、source_type、detail；未找到资源不能扩写为市场上不存在。缺口记录可被接收，但没有任何一条完整路径时，机器门禁仍 FAIL。确无已知缺口时必须 reviewed=true 并填写 no_known_gaps_reason，不能把空数组理解为业务确认。

一条路径是接收最低要求；最终 A/B 固定业务验收还要为同一家伙伴准备不同目标、能力和资源集合，参见 `REAL_BUSINESS_ACCEPTANCE_TEMPLATE.md`。结构完整不等于业务适用，也不等于真实模型已授权。

## 字段与现有产品映射

| JSON 字段 | 现有模型/存储/API | 填写责任与含义 |
|---|---|---|
| request 全部字段 | DevelopmentRequest → development_requests 的现有结构 | 原始诉求 raw_demand 必须保留；request_source=partner/partner_manager/jointly_confirmed；目标、岗位、人数、基础、周数、每周投入、7 类 constraints、显式 accepted_assumptions、targets、来源关联及请求授权 |
| request.targets[].capability_tag_id | capability_tags.id，enabled=1 | 业务方选择正式标签，不创建 AI 建议标签 |
| target_partner_name | partners.name；request.target_partner_id 对应 partners.id | 名称、ID 必须一致；仅核对，不复制伙伴主数据 |
| allowed_diagnostic_scope | 本次接收签审附件，不增加产品字段 | 列明允许内部诊断范围；原附件默认禁止模型发送，禁止内嵌原附件内容 |
| metadata.resource_type/title/summary/target_capability | ResourceMetadata；enablement_resources.draft_json / enablement_resource_versions.payload_json | 类型、名称、简介、本次目标能力 |
| metadata.audience/product_direction/difficulty | 同上 | 岗位、产品/技术方向、unknown/beginner/intermediate/advanced |
| metadata.language/site/prerequisites/duration_minutes | 同上 | 语言、站点、先修条件、分钟数（未知为 null） |
| metadata.cost/account_requirement/environment_requirement | 同上 | 费用枚举 unknown/free/paid，账号及环境条件；金额/预算放 request.constraints.budget，产品暂无独立金额字段，不另造字段 |
| metadata.source_platform/source_url | ResourceMetadata / ShareMetadata | 真实来源平台和不含凭据的外部 HTTP(S) URL；只做格式检查，不访问源站、不声称已访问或学习 |
| metadata.capability_tag_ids | 正式标签；资源 capability map / 共享版本 payload | 至少一项有效启用标签 |
| case.source_id / contributor_id | cases.id / cases.partner_id → partners.id | 必须有效且贡献伙伴启用；可不同于目标伙伴；绝不复制案例主数据 |
| case.metadata.title/summary/methods/contributor_role/source_platform/source_url/capability_tag_ids | ShareMetadata → case_share_configs / case_share_versions | 只填脱敏共享标题、摘要、实践方法、贡献职责和来源；内部案例原文不能当共享正文 |
| source_version / status | published_version / versions.version / status | status=published 是拟验收发布状态，不代表导入前已发布；导入后必须逐项对应当前版本 |
| permissions.system_visible | Permissions.system_visible | 内部系统可见，必须显式布尔值 |
| permissions.model_allowed | Permissions.model_allowed | 对应业务用语 model_send_allowed；同一个权限，不创建同名新字段 |
| permissions.partner_allowed | Permissions.partner_allowed | 对应业务用语 partner_share_allowed；与模型授权无推导关系 |
| permissions.reason | 既有权限变更审计 reason | 内容授权范围与依据；不得放凭据 |
| review.link_status/content_checked/authorization_checked/note | Review → enablement_reviews | 来源可用、内容核验、授权核验须明确通过；note 仅内部审核，绝不进模型投影 |
| reviewer_id / reviewed_at | enablement_reviews.reviewer_id / reviewed_at | 有效管理员 ID、带时区 ISO 时间；原包保留来源核验；导入后实际管理员与系统时间通过 import-ledger 关联，不覆盖原 JSON |
| permissions.base_revision / review.base_revision | 既有乐观锁 revision / reviewed_revision | 包中两者对应同一来源核验修订，由接收管理员据审核记录填写；不能当作新目标库的锁版本，实际目标 revision 由保存返回并记入 ledger |
| resource_gaps、package_kind、文件引用、签审材料 | 接收清单/验收证据，不新增业务表 | 用于门禁与审计，不宣称已落为 Plan/Version；package_kind=real 不能代替真实性签审 |

JSON 内不增加 model_send_allowed/partner_share_allowed 别名，避免两个字段互相冲突。所有产品字段必须显式出现；权限 null/省略/字符串 "false" 均拒绝。不知道的条件显式填“未知”或枚举 unknown，duration_minutes=null；程序保留 unknown，不能当符合。来源 URL、名称、正式标签和人工核验不能用“未知”绕过必填。

case 的 source_id 从一开始就必须是既有案例 ID；新课程/实验导入前 source_id/source_version 可以为 null，成功导入后实际 ID/版本只写入 import-ledger.json，不回填签过字的原包。共享版本首次创建前 source_version 可为 null；导入后通过 --imported --import-ledger 校验真正发布版本，不能仅凭导入前检查通过模型门禁。

## 执行预检

所有命令从 `/home/yuan/project/lingjian-agent-enablement` 运行，使用本地 `.venv`；脚本不启动服务、不认证、不联网、不写任何数据库。输出仅错误代码/字段位置、统计和摘要哈希，不打印业务正文或原始异常。

```bash
.venv/bin/python scripts/validate_pilot_data.py \
  .isolation/pilot-intake/<package>/manifest.json \
  --database .isolation/runtime/app.db

# 完成原子导入后，原包不变，通过账本关联实际 ID/版本/核验审计：
.venv/bin/python scripts/validate_pilot_data.py \
  .isolation/pilot-intake/<package>/manifest.json \
  --database .isolation/pilot/<package>/app.db --imported \
  --import-ledger .isolation/pilot/<package>/imports/<package-id>/import-ledger.json \
  --real-model-precheck
```

成功退出 0，任何数据错误或模型门禁未满足退出 2。输出 `eligible_record_indexes` 对应 resources 后接 shared_cases 的零基序号。三类集合独立计算：模型无授权排除模型集合，外发无授权排除外发集合。模型集合还复用现有 constraint_state 排除 conflicts，unknown 明确警示。案例字段在系统 schema 没有独立难度/岗位等列，不新增字段；实际资源约束不足仍显示 unknown。

`DATA-01-MACHINE-CHECK=PASS` 仅表示所选模式的结构/引用检查通过。模型前检必须用 imported 模式。机器无法证明资源真实性、课程适合度、实验难度、案例学习价值、业务路径合理性、签署人身份；业务负责人必须签审。已知 synthetic/fixture/example.com/验证伙伴/A-ready/金丝雀会被拒绝，去掉标记并不能使合成资源变成真实数据。

## 原子导入流程

现在使用 `scripts/import_pilot_data.py` 的 prepare / dry-run / apply；详细命令、边界和恢复规则见根目录 `PILOT_IMPORT_EXECUTOR.md`。先从 runtime 用 SQLite backup 建独立 `.isolation/pilot/<pilot>/app.db`；禁止 apply 到 runtime。importer 在单连接事务中复用原服务规则，失败整包 rollback。当前仍未收到或导入真实包。

原始 JSON、业务签审和整个包哈希保持不变；不回填系统 ID/时间。实际 actor 使用 --actor-user-id 指定的当前有效管理员，来源 reviewer/time 仅留业务证据。事务内账本保存于既有 app_metadata，提交后生成私有 import-ledger.json；导入后校验加 --imported --import-ledger，不修改产品 schema。

现有后台 API 仍按操作提交；整包原子性只由本地导入执行器提供，不是把多次 API 调用冒充一个事务。首版仅创建，任何已有资源/共享配置更新都拒绝。

独立库 integrity/FK/计数在前后复核，既有异常保持、不产生新异常。来源包若标记 synthetic，公开工具始终拒绝；不会将 pytest fixture 作为正式数据。业务签审、真实模型授权、调用预算和批准测试配置仍是独立门禁。所有业务材料、ledger、snapshot 只在被忽略的 .isolation 保存，不进 Git。
