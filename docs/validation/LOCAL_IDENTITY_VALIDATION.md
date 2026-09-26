> **阶段验证记录。** 本文的提交状态、HEAD 和测试数字属于当时基线；当前状态见 [2026-09-26 收口记录](GIT_CLOSEOUT_20260926.md)，现行规则见 [README](../../README.md)。

> 删除规则更新：账号统一逻辑删除并保留业务数据；本文旧删除限制仅为历史记录，当前行为见 [账号逻辑删除验证](ACCOUNT_DELETION_VALIDATION.md)。

> 历史记录：普通用户认证已改为浏览器自动登录 + 长期身份 Key；当前规则与验证以 [IDENTITY_KEY_VALIDATION.md](IDENTITY_KEY_VALIDATION.md) 为准。本文 Passkey/旧 Browser Identity 流程不再运行。

# 本机身份与管理员独立认证验证

日期：2026-09-23。工作区：`/home/yuan/project/lingjian-agent-enablement`，分支 `main`，实施基线 `1c9aaeb`。本次未 commit、push 或 deploy，保留本地服务供人工验收。

## 已实施

- 普通用户不再注册、等待审批、输入密码或首次改密。平台验证可用时显示“启用本机身份”，可选择已有本机身份恢复或仅使用当前浏览器；不可用时自动建立浏览器身份并提示清除数据的影响。
- 本机凭据映射到既有 `users.id`。有效 Session 不重复触发系统验证；凭据重新验证可恢复原用户。浏览器凭据使用 HttpOnly、SameSite Cookie，数据库只存随机秘密的摘要；凭据丢失后新建用户，不提供旧账号绑定或找回。
- 管理员使用 `/admin/login`、`/admin/account`、`/admin/change-password`，沿用密码、锁定、停用、重置、Token 失效和最后有效管理员保护。普通身份与管理员不能互相转换。
- 两套 Token 独立存储，401、改密和退出只影响对应身份。`/admin/tasks/[id]` 与普通任务页复用同一详情组件，保留管理路由和身份。普通任务恢复在身份就绪后才执行，管理员页面不恢复普通业务任务。
- schema 13 仅增加凭据和短期 challenge 两张表，并允许普通用户密码为空、约束管理员密码非空。challenge 保存于现有 PostgreSQL，绑定浏览器、5 分钟过期、事务内一次性消费，失败验证也不能重放。使用成熟公钥验证库校验签名、Origin、RP ID、用户验证标志、用户句柄和计数器。

## 实际验证

| 验证 | 结果 |
| --- | --- |
| Frontend typecheck | 通过 |
| Frontend production build | 通过 |
| 后端 671 项回归 | 全量 670 项通过；剩余历史快照测试修复后定向通过，相关 Pilot 另 87 项复验通过 |
| 迁移故障回滚、重复执行、管理员密码约束 | 专用 PostgreSQL 验证通过，现有行保持不变 |
| 相关 Playwright | 最终一轮 34 项全部通过 |
| diff 空白检查、配置忽略检查 | 通过；私有连接信息和备份不纳入 Git |

Playwright 范围：`local-identity.spec.ts`、`first-login.spec.ts`、`release-validation.spec.ts`、`task-navigation.spec.ts`、`feedback.spec.ts`。覆盖创建、会话保持、清除站点状态后恢复同一用户、无平台验证及主动放弃时的浏览器身份、Cookie 丢失后新身份、多标签页避免重复创建、普通用户 owner 隔离、双身份 401/退出互不影响、管理员任务详情、残留任务恢复、E2E-001～009、反馈及任务导航。

后端使用真实生成的公私钥和签名材料验证伪造签名、未知凭据、错误 Origin、错误用户句柄、异常计数器、过期/错误绑定/重放 challenge、停用身份及越权访问。身份接口和 schema 迁移用例运行于 `banfei_agent_test` 临时 schema；历史 SQLite 兼容及进程测试只使用 `/tmp`。浏览器业务回放显式使用隔离 replay，没有调用真实模型供应商。

验证入口（先按既有方式私下加载 `BANFEI_TEST_DATABASE_URL`；浏览器/进程用例须与正式服务错开）：

```bash
.venv/bin/python scripts/run_postgres_validation.py backend -q
PLAYWRIGHT_MODEL_MODE=replay .venv/bin/python scripts/run_postgres_validation.py browser local-identity.spec.ts first-login.spec.ts release-validation.spec.ts task-navigation.spec.ts feedback.spec.ts
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

本次发现历史 Pilot 测试引用旧工作区并触发了只读文件哈希检查，未启动或修改旧工作区服务。已向用户说明，并把该测试及相关保护路径改为 `/tmp` 隔离夹具，后续验证不再读取旧工作区。

## 正式库迁移与清理

迁移前已停止本项目服务、核对实际 PostgreSQL 目标并完成私有 `pg_dump`。备份及清理记录位于 Git 忽略的 `.isolation/local-identity-migration/`；数据库备份已通过 `pg_restore --list` 检查，反馈附件也已备份。

清理仅针对核实的 1 个普通测试用户：删除该用户、1 条注册申请、1 条反馈、1 条附件记录及对应文件、3 条关联测试审计记录。该用户没有匹配任务或发展方案，不迁移旧账号凭据。

逐表指纹核对：28 张未涉及清理的既有表内容不变；2 个管理员账号完整行不变；49 条匹配任务、13 份发展方案、36 家伙伴及案例、资料、资源、模型配置等保留。数据库/应用用户权限和序列不变。没有重建、重新 seed 或替换正式库。

新凭据及 challenge 表初始为空，保留给人工首次进入使用。迁移后不能将旧认证代码直接指向新的无密码身份数据；任何回退应先保存当前新增数据，再在明确的数据范围下协调代码与备份恢复。

## 人工验收边界

结束核验：本项目 3000/8000 服务运行，前端、管理员登录页及后端 `/health` 均返回 HTTP 200；隔离 replay 的 18180 端口已停止。Git 仍在 `main`，HEAD 与本地 `origin/main` 均为 `1c9aaeb`，本批改动未提交。

本地统一使用 `http://localhost:3000`，API 为 `http://localhost:8000`；管理员入口为 `http://localhost:3000/admin/login`。不要混用 `127.0.0.1` 作为浏览器入口。正式环境启用前仍须固定 HTTPS 内网域名及 Origin/RP ID。

已用实际 Linux Chrome 和 Edge 二进制搭配虚拟平台认证器验证：Chrome 创建凭据，Edge 在可访问同一凭据时恢复同一 `user_id`，并可再次清除站点状态后恢复。这不等于已验证 Windows 原生 Hello 的 PIN/指纹弹窗或操作系统凭据共享；这些仍需在 Windows Chrome/Edge 人工验收。不承诺不同浏览器配置一定共享凭据。

建议人工依次检查：启用本机身份 → 正常刷新不重复弹窗 → 清除站点数据后使用已有身份恢复 → 管理员独立登录/退出 → 返回普通业务仍为原身份。另用新浏览器配置检查降级提示及清除后新身份。

## 补充：用户管理鉴权方式

用户列表和详情新增只读“鉴权方式”。现有管理员列表/详情 API 返回派生的 `auth_methods` 数组：管理员有密码时显示“账号密码”，普通用户按当前凭据映射显示“本机身份”“浏览器身份”；同类去重、多种并列，无映射显示“未配置”。字段不依赖最后登录方式，不返回凭据内容，不提供编辑或绑定入口。账号停用仍由原“状态”列表示。

本项复用 schema 13，不增加数据库列或凭据状态，不修改正式库数据；不显示或推断具体系统、PIN、指纹或人脸验证手段。

补充项验证：专用 PostgreSQL 下 50 项相关后端测试通过（含新增 5 项）；`local-identity.spec.ts` 最后一轮 12 项 Playwright 全部通过（含新增 5 项列表/详情展示用例）。多凭据后端测试使用隔离库中的实际凭据映射，展示边界使用仅拦截后端 API 的浏览器夹具。正式库前后 36 张表、schema、权限、序列和私有配置指纹完全一致。

补充项最终 typecheck、production build 均通过；已恢复本项目 3000/8000，前端、用户管理路由和后端健康检查均为 HTTP 200。改动继续保持未提交、未 push、未 deploy。

## 补充：手工清理与退出当前身份

本次在 main 增加手工清理纯 Browser Identity 和普通用户退出，未 commit/push/deploy。

- `GET /admin/users/{id}/deletion-preview`：仅管理员可读，返回私有数据/公共引用数量、最后使用时间、保留期及是否允许删除。允许时提供绑定管理员、目标用户、当前数据摘要的短期确认凭据。
- `DELETE /admin/users/{id}`：仅管理员可用，在现有数据库写锁和单事务内重新检查身份类型、活动时间、运行状态、公共引用和预览摘要。变化后要求重新预览；不会沿用过期检查结果。
- 空浏览器身份可删；仅私有历史须连续 `BROWSER_IDENTITY_RETENTION_DAYS=90` 天未使用。发展方案、Run、Version、版本条目/诊断及个人跳转记录按外键关系一并清理，保留认证审计和删除记录。
- 需求画像、项目机会、公共标签建议、反馈/附件、共享/发布/核验记录、对外复制记录及跨用户来源引用阻止删除。读取共享资源本身不等于发布了本人历史；源伙伴、案例、资源和模型配置不跟随用户删除。
- Passkey、同时具备 Passkey 与浏览器凭据的用户、管理员均不开放删除。当前没有自动清理、回收站、审批或定时任务。
- 新增唯一字段 `users.last_active_at`，schema 13 → 14；普通用户有效鉴权请求及身份恢复更新该字段，管理员查看不刷新目标用户。未记录活动的有历史身份不判为过期；迁移给现有普通用户完整保留期。清理还保守检查本人历史的最近变更时间及运行状态。
- 普通用户侧栏增加“退出当前身份”，只清除当前浏览器普通会话存储，不撤销其他设备会话，不删除 HttpOnly 浏览器身份 Cookie 或 Passkey。退出页暂停自动进入，可显式继续；再次打开普通入口时 Browser Identity 仍自动恢复。Passkey 退出页通过“使用本机身份继续”重新验证。管理员与普通会话互不清除。此机制沿用现有客户端退出语义，未引入单 Token 黑名单/新会话表。

正式库迁移备份：Git 忽略的 `.isolation/user-cleanup-validation/migration/before.pgdump`，已验证备份目录可读取。迁移只增加时间列和 schema 版本；34 张其他表指纹不变，所有原用户字段、数据库权限和序列不变，没有删除正式用户或业务记录。私有运行配置仅补 `BROWSER_IDENTITY_RETENTION_DAYS=90`，其余配置保持原值。回退需停止服务、协调旧代码与 schema 版本；新增时间列可保留，不需要重建或覆盖业务数据。

验证结果：

- 后端全量首轮 694 passed、2 failed（旧测试把鉴权后的最后活动时间变化视为整库意外修改）；调整为保留全部业务/其他用户字段检查并单独验证活动时间后，这两项复测 2 passed。
- 清理与活动迁移专项最终 23 passed（含后加的 3 个边界），与全量/复测合计覆盖当前 699 项用例。覆盖空身份、90 天限制/配置、公共发布/反馈/跨用户引用、Passkey/混合/管理员拒绝、预览过期与数据变化、权限、整套私有方案清理、故障回滚、未知活动时间、迁移原子性/幂等。
- Playwright：`local-identity.spec.ts`、`first-login.spec.ts`、`release-validation.spec.ts`、`task-navigation.spec.ts`，39 passed，独立 PostgreSQL 验证库和显式 replay。Browser Identity/Passkey 退出后均实际恢复原 user_id 和测试任务；普通退出保留管理员、管理员退出保留普通会话；实际验证删除预览、取消和确认。没有向真实模型发送测试请求。
- frontend typecheck、production build、`git diff --check` 通过。
- 测试服务器结束后已使用 `enablement-dev.sh start` 恢复本项目 3000/8000。全部改动保留在 main 未提交，未 push/deploy。

## 补充：删除用户后的浏览器重新进入

- 原用户被管理员删除后，浏览器仍持有 HttpOnly 凭据时，后端返回明确的 `browser_credential_invalid`，入口提供“重新建立身份”。用户确认后复用 `POST /auth/identity/browser`，显式传入 `create=true, replace_invalid=true`；不新增接口、表或 schema 版本。
- 每次操作重新检查实际 Cookie 与凭据映射。有效凭据恢复其原用户，停用用户返回 `identity_disabled` 及可在后台搜索的用户名；不会将已存在的用户替换成新身份。无效凭据必须显式确认；Origin、频率限制及事务继续生效，失败不覆盖 Cookie、不残留新用户。
- 只写入新的普通浏览器身份 Cookie 与普通会话，不清空站点数据、管理员存储或 Passkey。新身份不恢复原用户历史。前端沿用跨标签页身份建立锁；取消确认不发起替换请求。
- 错误页将失效与停用分开。停用页显示可选中复制的“用户编号”，管理员可在现有用户列表搜索并启用；不新增联系人配置、工单或恢复机制。

验证：专用 PostgreSQL 中相关后端首轮 47 passed，补充创建失败回滚与停用 Passkey 用例 2 passed，共 49 项；`local-identity.spec.ts` 与 `first-login.spec.ts` 共 19 passed（1.5 分钟），包含真实删除后的重新进入、取消确认、旧任务不恢复、管理员双会话保留及停用后重新启用。frontend typecheck、production build、`git diff --check` 通过。测试未写入正式库，未调用真实模型。

## 修正：浏览器身份删除后重新选择本机身份

根因：初始化收到失效 Cookie 的 401 后直接进入错误分支，未执行本机验证能力检测；错误页又将本机身份按钮排除在外，导致后续启用系统验证仍只能重建浏览器身份。

- 已失效的浏览器身份进入恢复页后，检测平台验证能力；页面重新获得焦点、从后台切回以及刷新时重新检查。检测不创建凭据、不弹验证窗口；点击“启用本机身份”或“使用已有本机身份”才执行系统验证，有效 Session 的日常进入逻辑不变。
- 可用时显示本机身份创建、已有身份恢复和浏览器选项；不可用时保留浏览器重建。取消系统验证保留恢复状态及全部可用选项，浏览器重建继续要求确认。停用用户不开放这些身份切换入口。
- Passkey 创建或认证验证成功、数据库事务提交后，只过期删除服务端已无映射的旧 Browser Identity Cookie。验证失败不清 Cookie，有效 Browser Identity Cookie、管理员会话及 Passkey 不受影响。无新接口、schema 或账号绑定/迁移；新建本机身份使用新的 users.id，已有本机凭据恢复自己的原 users.id。
- 本机验证可用与已经为本站建立凭据是两件事。首次使用仍需点击创建；已有凭据才可验证恢复。参考 [W3C Web Authentication](https://www.w3.org/TR/webauthn/#sctn-isUserVerifyingPlatformAuthenticatorAvailable)。

验证结果：专用 PostgreSQL 相关后端 55 passed（49.03 秒）；`local-identity.spec.ts` 与 `first-login.spec.ts` 共 22 passed（2.0 分钟）。新增覆盖失效页面返回焦点后发现平台能力、刷新后仍提供选项、不自动发起系统验证、取消后继续创建或降级浏览器、旧浏览器凭据不阻止已有 Passkey 恢复、仅成功验证清无映射 Cookie、有效 Cookie 与管理员会话保留、停用身份不开放切换。frontend typecheck、build 与 `git diff --check` 通过。浏览器使用虚拟平台验证器，Windows 原生 Hello 弹窗仍需用户本机人工验收；未调用真实模型、未对正式库执行测试写入。

## 补充：本机身份手工删除（当前规则）

此前前端入口和后端规则均仅允许纯浏览器身份，本机身份即使没有业务历史也不能删除。本次按用户要求调整：

| 身份与关联情况 | 当前管理员操作 |
| --- | --- |
| 浏览器、本机或混合凭据普通用户，无业务历史/公共引用 | 查看关联数量，二次确认后删除 |
| 纯浏览器身份，仅个人私有历史 | 连续 `BROWSER_IDENTITY_RETENTION_DAYS`（默认 90）天未使用后可连带删除 |
| 本机身份或混合凭据，有个人业务历史 | 仅停用，不参与 90 天过期清理，不展示可清理日期 |
| 任意普通身份，有公共/共享/发布/跨用户引用 | 拒绝删除，保留停用 |
| 任意普通身份，有运行中的任务 | 拒绝删除 |
| 管理员、没有可识别普通凭据的用户 | 不开放删除 |

用户管理列表和详情复用同一个删除预览组件及现有接口。后端在确认时重新检查权限、关联数据、身份凭据和状态摘要，再在单事务中删除用户及本站凭据映射；保留认证审计和管理员会话。设备上保存的本机凭据不会由服务端移除，但已不能恢复被删除的用户；用户仍可通过“启用本机身份”建立新身份。复用当前 schema 14，不新增接口、数据库字段、设备管理或恢复机制。

### 关联数据梳理

以下为当前代码规则，不是正式库逐用户数量盘点。删除弹窗提供所选用户的实时数量。

| 业务数据 | 关联依据 | 对删除的影响 |
| --- | --- | --- |
| 匹配任务 | `match_records.owner_user_id` | 个人历史；归档后仍计数 |
| 发展需求、方案、运行、版本、版本条目、诊断、方案操作记录 | `development_requests`、`development_plans` 的 owner，以及对应 Plan/Version 关系 | 个人历史；本人范围内可按浏览器保留期连带清理；本机身份有这些数据不能删除 |
| 个人资源跳转记录 | `resource_redirect_events.actor_user_id` | 个人历史；只清理跳转记录，不删除被访问的公共资源 |
| 需求画像、项目机会、能力标签建议 | `demand_profiles`、`project_opportunities`、`capability_tag_suggestions` 引用本人的匹配任务 | 阻止删除；匹配流程会生成这些记录，不要求用户手动发布；标签建议待审或已驳回仍计数 |
| 问题反馈及附件 | `feedback_issue.submitter_id` 及所属 `feedback_attachment` | 阻止删除；已处理反馈也计数，虽然反馈本身并不对其他普通用户公开 |
| 历史注册申请/审批、由本人创建的其他账号 | `user_applications.user_id/reviewed_by`、`users.created_by` | 阻止删除；主要是历史兼容关联 |
| 案例共享配置、共享发布版本 | `case_share_configs.created_by`、`case_share_versions.published_by` | 阻止删除；不只检查当前已发布版本 |
| 公共资源、资源版本、发布核验及操作记录 | `enablement_resources.created_by`、`enablement_resource_versions.published_by`、`enablement_reviews.reviewer_id`、`enablement_audit_events.actor_id` | 阻止删除；草稿、撤回等状态也计数 |
| 方案对外内容复制记录 | 本人方案中 `development_audit_events.action=transfer_copy` | 阻止删除；表示发生过复制操作，不能据此断言已向外部发送 |
| 跨用户参与或引用 | 其他用户参与的 Request/Run/Version/方案审计，其他方案指向本人的 Request/Version，其他用户任务 JSON 中的 `source_task_id` | 阻止删除；来源 JSON 无法解析时也保守阻止，需先核查数据 |
| 身份凭据与 challenge | `identity_credentials.user_id`、`identity_challenges.user_id` | 不属于业务历史，允许删除时一并清理 |
| 认证审计 | `user_audit_logs.actor_user_id/target_user_id` | 不阻止删除；保留记录，已删除用户名显示为“已删除用户” |

仅浏览伙伴、案例、课程或实验不建立其所有权，不会导致这些共享数据随用户删除。匹配任务处于 `matching/enriching`，或发展运行处于 `pending/running` 时，独立于保留期阻止删除。本人历史最近创建/更新时间参与最后使用时间判断；预览后发生使用、关联数据或凭据变化会使确认失效，需要重新查看。

本项验证结果（2026-09-24）：

- 专用 PostgreSQL 下 `local_identity or user_cleanup or admin_auth_methods`：62 passed、658 deselected。覆盖空 Passkey/混合凭据删除、所有凭据与旧 Session 失效、管理员会话及认证审计保留、1 天/120 天个人历史均不允许清理、仅反馈引用也阻止删除、预览后新增历史拒绝，以及既有浏览器保留期、权限和事务回滚边界。
- frontend typecheck、production build、`git diff --check` 通过。
- Playwright `local-identity.spec.ts` + `first-login.spec.ts`：首轮 22 passed、2 failed。其中新增测试的错误提示定位与 Next.js 路由播报元素冲突，收窄定位后修正；另一个用例因整组密集身份请求触发每地址每分钟 60 次限流，未修改生产限制。两项在独立验证批次复测 2 passed，合计覆盖全部 24 项。今后密集身份回归宜分批运行，避免共用地址的速率预算影响用例。
- 新增浏览器覆盖列表预览/取消、详情确认删除、计数、旧 Session 和设备凭据被服务端拒绝、重新建立不同 user_id、本机身份私有历史保留及管理员会话不受影响。虚拟平台验证器验证通过，不等同于 Windows 原生系统弹窗人工验收。
- 没有修改 schema、私有配置或执行正式库清理；全部测试使用专用验证库及临时测试材料，未调用真实模型。改动保留在 main，未 commit/push/deploy。

收尾已用 `enablement-dev.sh start` 恢复本项目服务，核对 PID 工作目录后，3000 首页、用户管理路由及 8000 `/health` 均返回 HTTP 200；隔离 replay 的 18180 监听已停止。main 与本地 origin/main 的提交仍为 `1c9aaeb`，工作区保留本批及之前未提交改动。

## 修正：本机凭据清空后的新建入口

Windows 的“选择通行密钥”窗口只用于验证已有凭据；旧凭据已移除时，不会在该窗口创建新身份。原退出页又只保留“使用本机身份继续”，并跳过平台能力检测，导致用户停留在只能寻找旧身份的入口。

本次只修改前端入口、对应浏览器测试和说明，不修改后端、schema、私有配置或正式用户数据：

- 将创建按钮明确命名为“新建本机身份”，与“使用已有本机身份”区分。
- 本机身份退出页检测平台能力，并同时提供新建和浏览器身份选项；平台验证不可用时仍保留浏览器入口。检测及返回页面重新检测均不会弹验证窗口或自动创建用户。
- 退出后选择新建本机身份前说明原历史不会转入，并要求确认；取消确认不发起注册。取消空凭据选择窗口后继续保留新建/浏览器选项。
- 验证取消提示说明如何新建，不再只建议反复重试；退出说明不再无条件宣称原身份和历史仍存在。服务端明确返回停用后仍显示用户编号及管理员启用提示，不开放替代身份按钮。
- 成功进入后清除当前普通退出标记；管理员会话不受影响。只有本机凭据丢失、原账号仍存在的情况，不会删除原账号和历史，也不会把原历史迁给新用户。

人工操作：关闭 Windows 的旧身份选择窗口，刷新伴飞页面，选择“新建本机身份”，按新凭据创建提示操作；也可选择“仅在此浏览器使用”。无需再次清理电脑凭据或浏览器站点数据。

本项验证：frontend typecheck、production build、`git diff --check` 通过。`local-identity.spec.ts` 和 `first-login.spec.ts` 按身份请求频率分三批验证，全部 27 个用例通过（含复测）：第一批 7 passed、1 次管理员登录测试连接中断；第二批含该项复测 10 passed；第三批 10 passed。没有放宽生产限流或改变后端身份验证。

新增用例实际清空虚拟平台认证器的凭据，触发空凭据验证并模拟用户关闭系统窗口，验证不会提交认证或自动注册，随后可确认创建新本机身份；同时覆盖原账号尚存但本机验证不可用时使用浏览器身份、新用户不能读取原任务、原历史仍保留、取消新建确认零注册请求、退出标记正确清除、管理员会话保留和已停用身份不显示替代入口。现有登录、清 Cookie 后恢复、Chrome/Edge、双会话、删除、列表/详情和管理员首次改密均在这 27 项中回归；Windows 原生弹窗仍以人工验收为准。

## 修正：未找到本机身份时直接引导新建

服务端确认凭据无映射时，原来只返回“未找到该本机身份”文本；页面继续显示已有身份验证及重试入口。本次用明确错误码 `passkey_credential_not_found` 表示该情况，前端进入独立的“新建身份继续使用”状态：

- 提示“未找到该本机身份，请新建身份后继续使用”，本机验证可用时以“新建本机身份”为主操作，并保留浏览器身份入口；不可用时以浏览器入口为主操作。
- 该状态不显示“使用已有本机身份”“使用本机身份继续”或“重试”，不会自动创建用户或再次验证已失效凭据。
- 新建验证取消或遇到临时错误后仍保留新建状态；明确停用继续显示停用处理。未知凭据、错误签名和停用使用不同结果，不把通用验证失败当作身份不存在。
- 选择浏览器身份需要确认，可处理同时残留的无映射浏览器 Cookie；取消不发起创建、不覆盖 Cookie。已有有效或停用的浏览器映射继续接受服务端复核。
- 原凭据无法重放已消费的 challenge，不返回 Session，不清理电脑凭据；管理员会话不受影响。复用现有创建接口，不新增接口、schema、配置或账号恢复机制。

本项验证：专用 PostgreSQL 下相关后端 62 passed、658 deselected；typecheck、production build、`git diff --check` 通过。相关 Playwright 分批 6 passed + 10 passed，共 16 项通过。覆盖未知凭据明确分流、普通入口/退出入口新建主操作、移除重试与旧身份入口、取消新建无新用户、未知凭据 challenge 不可重放、错误签名不误判不存在、同时残留无效浏览器 Cookie 时的确认/取消/替换、平台不可用时降级、停用、双会话及管理员改密。未运行无关全量用例；没有放宽限流、自动注册或真实模型调用，测试写入仅在专用验证库。
