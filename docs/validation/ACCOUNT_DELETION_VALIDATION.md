> **阶段验证记录。** 本文的提交状态、HEAD 和测试数字属于当时基线；当前状态见 [2026-09-26 收口记录](GIT_CLOSEOUT_20260926.md)，现行规则见 [README](../../README.md)。

# 账号逻辑删除验证

日期：2026-09-25。工作区：`/home/yuan/project/lingjian-agent-enablement`，分支 main，HEAD `7a73e1825067ba466830578443225a912e54ef5e`。本轮及此前未提交修改均保留，未 commit、push 或 deploy。

## 当前规则

- 统一“删除账号、保留业务数据”。保留 `users.id` 和原账号资料，复用现有 `users.status='deleted'`，增加 token_version 使所有旧 Token 失效。正常用户列表、详情和后台用户总数排除已删除账号，更新、启用、解锁、重置密码接口均不能恢复该账号。
- 同一事务删除身份 Key 密文/映射、全部浏览器与旧 Passkey 凭据及关联 challenge；原 Key 不可逆摘要仍写入现有 revoked_identity_keys，以继续区分“原身份已删除”和输入错误。密码登录同时检查删除状态；保留的密码哈希不能用于登录。其他账号和管理员会话不受影响。
- 不再根据凭据类型、最后活动时间、业务历史、公共/共享/发布/跨用户引用决定能否删除；停止读取 `BROWSER_IDENTITY_RETENTION_DAYS`，已有私有配置无需调整。
- 仅保护当前操作账号、最后一个可用管理员，以及拥有 pending/running 发展 Run 或 matching/enriching 匹配任务的账号。可用管理员指已启用、有密码且未处于临时登录锁定的管理员。
- 确认令牌仍绑定操作者、目标、账号版本并有有效期；删除事务重新校验保护条件和操作者，避免过期确认与并发管理员操作。账号日常活动或新增已结束的业务历史不会阻止已确认删除。
- 两类任务在提交/重试的写入事务中重新检查发起账号状态，覆盖“范围判断期间账号被删除”的窗口，不允许删除后再启动新任务。
- 所有业务表、上传附件、owner、外键、共享/发布授权保持原样。任务列表/详情、反馈、资源核验人和认证审计等展示投影将已删除账号显示为“已删除用户”，不改写历史业务行。
- 复用 admin.user_deleted 审计，记录 actor_user_id、target_user_id、时间和目标用户名/显示名；不记录 Key。新身份使用新的 users.id 和 Key，旧 Key 不恢复身份，新身份不能访问旧私有历史。
- 用户列表与详情都提供删除，普通用户与管理员一致。确认弹窗仅含：

> 删除后，该账号及身份 Key 将无法使用，历史业务数据仍保留。确定删除？

按钮为“取消”“删除账号”。遇到三项保护时显示具体阻止原因。

## 数据与接口影响

无新增表/列、无迁移，schema 保持 16。复用 GET /admin/users/{id}/deletion-preview 和 DELETE /admin/users/{id}；预览简化为允许状态、原因和确认令牌，不再扫描或返回业务关联清理计数。旧确认令牌不能执行新版删除。删除 endpoint 不再硬删除 users 或任何业务记录。

没有对正式账号执行测试删除，没有运行库数据回填、清理、重建或私有配置修改。正式库 38 张表在验证前后只读逐表比较内容摘要，完全一致；schema 仍为 16。旧历史记录中的硬删除政策已标注由本文替代，不尝试恢复此前已被硬删除的数据。

## 实际验证

- 后端定向回归：**221 passed**。213 项使用专用 PostgreSQL 验证库临时 schema，8 项为原有 /tmp SQLite 生命周期兼容测试；其中部分迁移用例还显式操作 /tmp 文件。覆盖认证、管理员用户投影、反馈、所有权、Scope Gate、任务错误与发展生命周期。
- 删除专项覆盖：各类身份和管理员、0/100 天、有个人/公共/共享/发布历史仍可删，业务表逐行快照不变，Plan/Run/Version 保留，发布权限和图片文件不变，删除人/时间/目标审计，全部旧会话和 Key 失效，账号不可重新启用，新身份不继承历史，当前账号/最后管理员/运行中任务保护，确认之后新增运行任务的重检，双管理员并发删除，范围判断中删除，审计写入失败后的事务回滚。
- Playwright：**7 个不同用例全部通过**。列表/详情删除和取消、确认弹窗单句及按钮、管理员删除入口、自删保护、历史任务仍可查看并显示“已删除用户”、粘贴及导入旧 Key 显示已删除、停用与删除提示区分、其他身份和管理员会话保留。使用 PostgreSQL 临时 schema，无模型服务或真实模型调用。
- `npm --prefix frontend run typecheck`、`BANFEI_BUILD_CPUS=2 npm --prefix frontend run build`、`git diff --check` 通过。build、浏览器测试和开发服务顺序执行，无并行写同一 .next。
- 首轮后端新增夹具遗漏资源引用字段、浏览器断言误匹配 Next.js 的额外 alert；修正测试后，上述对应范围复验通过。中止的误包含全量目录的测试命令未作为通过依据。

证据仅存本地：`/tmp/banfei-soft-delete-final-backend.xml`、`/tmp/banfei-soft-delete-final-backend.log`、`/tmp/banfei-soft-delete-browser.log`、`/tmp/banfei-soft-delete-browser-final.log`、`/tmp/banfei-soft-delete-build.log`。测试产物与私有凭据未纳入 Git。

## 验收环境

使用既有私有配置恢复正式工作区服务，3000 `/admin/users` 与 8000 `/health` 均 HTTP 200，进程工作目录属于本项目，18180 无测试模型服务。main 与 origin/main 的提交指针仍相同；工作区保留本轮和此前未提交改动，供人工验收。
