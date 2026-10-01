> 2026-10-01 数据库清理说明：本文中的混合数据库数字仅为历史实测记录，不代表当前 PG-only 验证。当前规则见 [PG-only 验证](POSTGRES_ONLY_20261001.md)，不再执行文中的旧文件数据库路径。

> **阶段验证记录。** 本文的提交状态、HEAD 和测试数字属于当时基线；当前状态见 [2026-09-26 收口记录](GIT_CLOSEOUT_20260926.md)，现行规则见 [README](../../README.md)。

> 删除规则更新：账号统一逻辑删除并保留业务数据；本文旧删除限制仅为历史记录，当前行为见 [账号逻辑删除验证](ACCOUNT_DELETION_VALIDATION.md)。

# 普通用户身份 Key 改造（2026-09-24）

本记录替代旧普通 Passkey / Browser Identity 运行流程；旧验证记录保留为历史。本批直接在正式工作区 main 实施，未提交、推送或部署。

## 当前行为

- 首次访问普通业务入口自动创建普通用户及 256 位随机长期 Key，自动进入；首次弹窗可复制、下载 `.txt`、关闭/稍后保存，或切换已有 Key。
- `/login` 优先恢复当前浏览器的有效身份，不自动创建用户；`/login?method=key` 用于显式 Key 登录/切换，输入错误不创建、不改写当前会话。正确 Key 恢复原 user_id、任务及历史，并记住当前浏览器。
- Key 表单支持“导入凭据 .txt 登录”，浏览器本地读取此前下载的凭据或只含单个完整 Key 的 .txt，再调用现有 Key 登录接口；不上传文件，不创建用户。
- 个人中心始终从本人端点读取同一 Key，支持复制/下载；不在浏览器 localStorage/sessionStorage 保存长期 Key。
- 普通退出撤销旧 Cookie/Token 绑定，保留新的浏览器凭据但不发放 Token；持久退出标记使刷新/重开浏览器仍停留入口，点击“继续使用当前身份”免 Key 恢复原用户。Key、历史、其他浏览器及管理员会话保留。
- 管理员独立账号密码、改密、权限、任务详情保持原实现；用户列表/详情显示鉴权方式及后端生成的脱敏 Key 标识（固定前缀 + 随机前 2 位 + … + 末 5 位），不返回完整凭据。
- 普通注册、审批、密码、首次改密、Passkey 接口不再开放。旧用户/旧凭据保留但不迁移，不绑定到新身份。

首次自动创建与已有 Key 登录的边界：新浏览器先打开 `/` 会按要求创建新身份；首次弹窗切换已有 Key 时不会再创建用户，不合并或删除刚产生的空身份。已有 Key 的用户可直接访问 `/login`，全程不创建新用户。

## 接口及安全

| 接口 | 行为/权限 |
| --- | --- |
| `POST /auth/identity/session` | 严格 Origin；恢复 Cookie 指向的身份，仅显式 create=true 时可创建 |
| `POST /auth/identity/key/login` | 严格 Origin；验证 Key 摘要，恢复用户，不创建用户 |
| `GET /auth/identity/key` | 仅已认证普通本人；解密展示，禁止缓存，管理员不能代查 |
| `POST /auth/identity/logout` | 严格 Origin；撤销当前 Cookie / 签名 Token 指定会话并保留新的浏览器凭据；不发放 Token、不动管理员 |

Key 为 `bf_` 前缀加 32 随机字节的 URL-safe Base64。服务端保存 SHA-256 摘要与 Fernet 认证密文；密文绑定 user_id，不能交换给另一用户展示。每用户只有一行 Key 映射、摘要唯一，不实现更新/轮换入口。独立浏览器会话仍复用已有 identity_credentials 的 browser 类型，Cookie 随机秘密只存摘要；普通 JWT 增加 sid，逐请求检查会话归属、有效期、用户状态和 token_version。

Key 不放进通用 UserOut、TokenResponse、管理员返回、认证审计或模型上下文；输入错误不回显提交值。身份 POST 继续限流，业务 owner 校验保持原实现。长期 Key 用户有历史时只停用，空用户仍可经预览、确认删除；保留旧用户原清理约束。

## 数据库与私有配置

schema 14 → 15 仅增加 `user_identity_keys(user_id PRIMARY KEY, key_hash UNIQUE, encrypted_key, created_at)`，不修改已有业务列或用户数据。迁移脚本先 pg_dump 再事务 DDL，故障回滚、重复执行不重建、不回填旧用户。

本地已备份并执行迁移。变更前后核对除 schema 元数据与新增空表外的 35 张表，共 669 行完全一致；没有执行正式库测试 seed 或用户清理。备份及核对证据：`.isolation/identity-key-migration/20260924T082910Z/`（Git 忽略、私有权限）。

`BANFEI_IDENTITY_ENCRYPTION_KEY` 已写入现有 Git 忽略的运行 environment.json；与 JWT 签名密钥分离并有私有备份。缺失/格式错误拒绝启动，错误密钥无法解密时明确失败、不生成替代 Key。数据库备份必须与原加密配置配套保留。回退需停服、保留 v15 新数据及密钥并协调代码/schema；不得用旧库覆盖新增身份和业务数据。

## 验证

测试只使用本机 banfei_agent_test 的临时 schema；历史兼容及进程故障测试只用 /tmp SQLite。浏览器测试使用独立测试加密密钥，不继承正式加密配置。本批不调用真实模型，不部署。

- frontend typecheck、production build、`git diff --check` 通过。
- 后端全量首轮 704 passed / 5 failed；失败均来自测试夹具更新（历史快照应在建立测试凭据后记录、进程测试旧 amr/token）。修正后选择相关模块及新增安全用例复测：47 passed / 664 deselected，包含全部 5 个原失败及 2 个新用例。合计当前 711 个后端用例经全量与补测覆盖通过；PostgreSQL 为主，既有历史兼容/进程故障模块仍用 /tmp SQLite，不将其计作 PostgreSQL 运行验证。
- Playwright 首批 `local-identity.spec.ts + first-login.spec.ts`：9 passed / 2 failed；两项为测试定位器歧义（任务在侧栏和列表同时出现、Next.js 自带 role=alert）。收窄到任务表格单元格/登录表单提示后，与 `release-validation.spec.ts` 的 E2E-001～005 一起复测：7 passed。合计 16 个不同浏览器用例覆盖通过。
- 覆盖自动创建、刷新不重复创建、弹窗/个人中心同一个 Key、两处复制/下载、清理站点数据后恢复同一用户及原任务、错误 Key 不建用户、首次弹窗切换原身份、退出/重开浏览器不自动建号、旧 Token 失效、两种会话互不影响、多标签页只创建一次并同步退出、过期普通 Token 通过 Cookie 恢复、越权 404、管理员首次改密与任务详情隔离。
- 使用本机已安装的 Chrome/Edge 实际浏览器二进制验证同一 Key 跨浏览器恢复，通过；无系统凭据验证调用。首次弹窗与个人中心截图已检查，临时证据 `/tmp/banfei-key-identity-key-popup.png`、`/tmp/banfei-key-identity-key-account.png` 仅含隔离测试凭据。
- 后端新增检查密文不能交换给其他用户、伪造/他人会话 sid 拒绝、无 Cookie 时退出也撤销当前 Token、加密配置错误不轮换 Key、摘要/密文及唯一约束、事务回滚、管理员与旧认证边界、后台响应无 Key、删除规则及 schema 迁移失败回滚/重复执行。
- 私有配置权限 0600，Git 可见文件扫描未发现正式加密密钥。没有对正式库运行 E2E/测试 seed，没有调用真实模型。验证日志留在 `/tmp/banfei-key-{backend-all,backend-final,browser,browser-final,typecheck,build}.log`。

本地人工验收入口：`http://localhost:3000`（首次自动创建），`http://localhost:3000/login`（已有 Key），`http://localhost:3000/account`（身份凭据），`http://localhost:3000/admin/login`（管理员）。

收尾：通过 `enablement-dev.sh start` 恢复本项目服务，核对进程工作目录归属；3000 首页、普通/管理员登录页及 8000 `/health` 均为 HTTP 200。隔离 replay 的 18180 监听已退出。main 与本地 origin/main 提交仍为 `1c9aaebc6000877730959b9d88af0572d1139cfe`，本批及之前改动保持未提交（102 个路径），未 push/deploy，等待人工验收。

## 修正：同一浏览器退出后无需再次输入 Key

原实现将退出和忘记浏览器身份合并：清掉 Cookie、撤销凭据后只剩 Key 表单；普通 `/login` 又无条件跳过了会话恢复。本次调整为：

- 退出时在同一事务中撤销旧凭据/Token 绑定，并为已证明的有效身份保留新的随机浏览器 Cookie，不创建用户、不生成/轮换 Key、不发放登录 Token。只有有效 Cookie 或仍有效且未撤销的 Token 可以证明用户，不能用残留 user_id、已撤销 Token 或设备信息恢复。
- 前端持久退出标记保留“继续使用当前身份”，点击才恢复。刷新、重开、多标签页同步退出不会自动登录或建新用户；清除 Cookie 后继续会回到 Key 入口，不静默新建。
- 普通访问 `/login` 或业务请求 401 后返回该入口时，优先复用有效 Token/Cookie，免 Key 自动恢复。显式切换用 `?method=key`，保留首次弹窗和退出页的其他 Key 登录操作。
- 不新增接口、字段、schema 或私有配置，不使用机器码/浏览器指纹。旧版退出已经清掉的凭据无法事后恢复，需 Key 登录一次；之后采用新规则。

本次验证结果：

- frontend typecheck、production build 通过。
- 后端 PostgreSQL 选定认证/用户清理/OpenAPI 子集：93 passed、621 deselected；覆盖旧 Cookie/Token 撤销、无 Cookie 时有效 Token 证明、过期/撤销/伪造凭据不记住身份，以及替换失败事务回滚。
- Playwright `local-identity.spec.ts + first-login.spec.ts`：14 passed；`release-validation.spec.ts` E2E-001～005：5 passed。共 19 项通过，包括 Chrome/Edge、退出后重开浏览器点击继续、正常 `/login` 自动恢复、业务 401 自动恢复、Cookie 丢失后无误建用户、Key 切换、owner 隔离和管理员独立会话。
- 已检查退出页截图，主操作为“继续使用当前身份”，次操作为“使用其他 Key 登录”；截图保留于 `/tmp/banfei-remembered-identity-continue.png`。
- 测试均使用隔离验证数据库；未对正式数据库执行测试 seed/业务写入，未调用真实模型。日志：`/tmp/banfei-remembered-{backend,typecheck,build,browser,release}.log`。


本次收尾：`enablement-dev.sh start` 已恢复当前项目服务；3000 首页、普通/管理员登录页及 8000 `/health` 均 HTTP 200，进程 cwd 属于当前项目，18180 测试服务已退出。`git diff --check` 通过；main 和本地 origin/main 均为 `1c9aaebc6000877730959b9d88af0572d1139cfe`，工作区仍为本批累计 102 个未提交路径，未 commit/push/deploy。


## 补充：导入身份凭据登录

用户补充授权文件导入后，Key 登录表单在粘贴/登录操作下增加“导入凭据 .txt 登录”。选择后自动验证并登录原身份；首次弹窗的已有 Key 入口、无有效身份的入口、退出后的其他 Key 登录共用该表单。

- 支持现有及此前下载的 UTF-8 .txt 凭据、只含一个完整 Key 的 .txt，以及 BOM/Windows CRLF/前后空白。
- 只在浏览器内读取文件，向现有 `/auth/identity/key/login` 提交一个 Key 字段；不上传/存储文件，不将 Key 写入浏览器持久存储、日志或管理员数据。
- 客户端拒绝非 .txt、超过 16 KB、空白/格式错误/截断/多 Key 文件；未知 Key 由原服务端返回错误。失败不创建用户、不修改原浏览器身份；取消选择不提交，选错后可重选同名文件。
- 手动粘贴、继续当前浏览器身份及管理员会话保留。没有后端接口、数据库/schema、私有配置或依赖变更；下载凭据说明同步增加导入提示，旧文件仍兼容。

本次验证结果：

- frontend typecheck、production build、`git diff --check` 通过。
- PostgreSQL 隔离 Playwright `local-identity.spec.ts + first-login.spec.ts` 首轮 17 passed / 1 failed；失败是新增测试使用的任务标题与既有夹具不同，实际任务已恢复。修正定位标题后定向复测 1 passed，合计 18 项覆盖通过。
- 新增 4 项导入用例：实际下载→清除 Cookie→导入恢复同一用户/任务/Key且用户数不变，BOM/CRLF 纯 Key 导入，取消及 8 类错误文件不发送请求，未知 Key 失败保留浏览器身份且可重选同名文件重试。验证请求仅含 Key、管理员 Token 保留；原手动输入、自动登录、免 Key 继续、会话隔离、Chrome/Edge 和管理员首次改密用例继续通过。
- 已检查导入入口截图：`/tmp/banfei-key-import-login.png`。日志：`/tmp/banfei-key-import-{typecheck,build,browser,browser-recheck}.log`。
- 仅前端实现与测试/文档变更，后端未变更，本次未重跑后端全量。没有正式库测试写入或真实模型调用。


本次收尾：本项目 3000/8000 已恢复运行，已核对进程 cwd；普通 Key 入口、管理员入口和后端 `/health` 均 HTTP 200。main 与本地 origin/main 仍为 `1c9aaebc6000877730959b9d88af0572d1139cfe`，本批累计 103 个路径保持未提交，未 commit/push/deploy。


## 补充：已删除身份与错误 Key 的区分（schema 16）

- schema 15 → 16 仅新增 `revoked_identity_keys(key_hash PRIMARY KEY, revoked_at NOT NULL)`。独立表不关联 users，不保存明文、密文、用户标识或业务数据；删除原 Key 及用户时在同一事务写入摘要。删除受阻/失败不会残留失效记录，失效 Key 不再获配给新用户。
- 现有 Key 登录接口返回结构化 `detail.code/message`：`invalid_key`（格式错误）、`unknown_key`（无匹配或旧版失效）、`identity_deleted`（确认删除）、`identity_disabled`（停用）。错误响应不缓存、不回显 Key、摘要、用户 ID 或删除时间。
- 前端统一处理粘贴和导入。确认删除时显示“原身份已删除”，用户明确点击“创建新身份”才新建 user_id 和 Key；创建失败仍可重试。停用提示管理员重新启用，不提供新建快捷入口。文件读取/格式问题仍在浏览器本地提示。
- 已删除/未知 Key 的错误只附带服务端核验的浏览器身份可用布尔值，用于判断是否显示“返回当前浏览器身份”；不更改 Cookie/Token，不影响其他有效普通身份和管理员会话。浏览器无有效身份时，未知/旧版失效提示仍保留显式创建入口，不能依赖残留 localStorage 假定还能恢复。
- 现有 `/auth/identity/session` 增加可选 `replace`（默认 false，仅与 create=true 配合）。仅显式点击新建时使用，使新建确实产生新用户；自动恢复流程保持原语义，不因 Key 登录失败调用新建。不删除/合并浏览器此前的有效用户、Key 或历史，只替换当前浏览器会话绑定。
- 此前已删除、未留下摘要的 Key 不回填、不猜测、不恢复备份，兼容提示“凭据无效或已失效，请确认 Key 或凭据文件。”。
- 显式迁移脚本 `scripts/migrate_revoked_identity_keys.py` 先 pg_dump 再事务 DDL，失败回滚，重复执行保留新增失效记录。回退须停服并保留失效表、协调代码/schema，不用旧库覆盖后续数据，不用漏记摘要的旧代码继续删除用户。

本次验证与运行库迁移结果：

- frontend typecheck、production build、`git diff --check` 通过。
- 后端认证、删除、迁移、存储和 OpenAPI 选定子集：148 passed / 572 deselected。补齐浏览器可用性判断后定向认证复测：25 passed / 695 deselected。覆盖删除原子性、晚期失败回滚、摘要不含用户关联、不泄漏凭据、停用与旧版无记录的区别、显式新建和旧 Key 永不复用、迁移失败回滚/重复执行/既有数据不变。PostgreSQL 为主，既有 SQLite 兼容迁移模块只在 /tmp 测试，不计作 PostgreSQL 全量验证。
- Playwright 首轮 `local-identity.spec.ts + first-login.spec.ts`：21 passed / 1 failed。失败来自最后一项触发真实 60 次/分钟限流（停用提示已通过，重新启用后的登录返回 429）；保留限流原值，单独复测 1 passed。入口细节修正后，已删除/停用/旧版未知凭据分批复测 5 passed；合计 23 个不同浏览器用例覆盖通过。不将高密度批次的限流误判为凭据错误。
- 已检查最终删除提示截图 `/tmp/banfei-deleted-key-entry.png`：主操作“创建新身份”，次操作“使用其他 Key 登录”；不存在有效浏览器身份时没有失效的返回按钮。创建失败可重试，输入已删除的其他 Key 不覆盖现有普通身份/管理员 Token。
- 日志：`/tmp/banfei-revoked-key-{backend,backend-final,typecheck,build,browser,browser-recheck,browser-final}.log`。测试只用专用验证库临时 schema 或 /tmp 兼容文件；未对运行库执行测试 seed/删除验证，未调用真实模型。
- 本地运行库已备份并执行 v15→v16 增量迁移。新增失效表为空，未回填历史删除；37 张既有表内 697 行（排除 schema 版本行）内容核对一致，私有运行配置字节不变。备份及核对记录位于 `.isolation/revoked-key-migration/20260924T130411Z/`，目录 0700、数据库备份和配套私有配置 0600，均被 Git 忽略。
- 已恢复当前项目 3000/8000，普通/管理员入口及 `/health` 均 HTTP 200，进程 cwd 已核对，18180 未监听。main 与本地 origin/main 仍为 `1c9aaebc6000877730959b9d88af0572d1139cfe`；当前累计 105 个未提交路径，保留既有改动，未 commit/push/deploy。


## 补强：Key 登录请求体大小与注入回归

- 仅调整现有 `POST /auth/identity/key/login`：JSON 解析前限制请求体为 4096 字节。已声明超限时不读取正文；其余按实际流式字节累计，超过上限立即停止读取，不依赖 Content-Length，覆盖缺失/虚报长度、分块传输及多字节内容。
- 超限统一返回 HTTP 413 和 `request_too_large`，不回显凭据，响应禁止缓存，不进入数据库、不创建身份、不替换 Cookie/Token。损坏编码、JSON 语法或过深嵌套仍返回固定格式错误，避免泄漏解析异常。
- 保留现有严格 Key 格式、摘要查询、参数绑定和浏览器本地 .txt 解析。没有新增接口、schema、私有配置或依赖；管理员登录规则不变。
- PostgreSQL 专用验证库临时 schema 中执行 `backend -q -k 'test_local_identity or test_auth or test_admin_auth_methods'`：71 passed / 663 deselected。包含超限在解析/存储前拒绝、及时停止读取、恰好 4096 字节的普通/分块请求可恢复身份和历史、异常 JSON、SQL/脚本/命令/路径类非法 Key，以及普通/管理员会话不受失败请求影响。
- Playwright `local-identity.spec.ts --grep 'credential file import'`：4 passed。覆盖实际下载后导入恢复历史、BOM/CRLF、未知 Key 重试，以及新增 SQL/脚本/命令/路径类错误文件在浏览器内被拒绝且不发起登录/业务请求。
- frontend typecheck、`git diff --check` 通过。未改前端产品代码，本次未重复 production build 或无关全量测试。日志：`/tmp/banfei-key-body-limit-{backend,browser}.log`。
- 没有修改数据库结构或私有配置，没有对正式库执行测试写入，没有调用模型；改动保持未提交、未 push/deploy。


## 补充：管理员通过脱敏 Key 标识核对用户

- 用户已确认格式为 `bf_` + 随机部分前 2 位 + `…` + 末 5 位，例如 `bf_Ab…xY123`。用户列表、详情增加只读“Key 标识”，详情同时显示既有用户 ID。该标识用于辅助核对，不提供完整 Key 查询、找回、修改或新增认证入口。
- 复用 schema 16 的 `user_identity_keys`，按 users.id 关联、校验密文绑定和摘要后在后端脱敏。现有管理员列表/详情响应仅新增 `identity_key_hint`，禁止缓存；不向管理员返回完整 Key、密文或摘要，不加入普通 UserOut、日志或模型上下文。没有 schema、私有配置、依赖或数据迁移。
- 管理员/无长期 Key 的旧身份显示“—”；有映射但无法校验或解密时显示“暂不可用”，不阻断其他用户，不改写、生成或轮换凭据。停用用户仍可核对原标识。分页、筛选和访问权限保留。
- 后端 PostgreSQL 选定认证、管理员用户投影与 OpenAPI 用例：81 passed / 659 deselected。新增覆盖列表/详情/分页的用户对应关系、停用身份、旧身份和管理员空值、完整凭据/密文/摘要不外泄、普通与匿名访问拒绝、损坏/串换密文或摘要不显示错误标识、读取不改写凭据。
- frontend typecheck、production build 通过；最终不换行样式补充后再次 typecheck 通过。Playwright 首轮 1 passed / 1 failed，失败为新增响应等待条件误匹配前端 HTML；限定后端 API URL 后该项复测 1 passed。共 2 个不同浏览器用例覆盖通过，包括列表到详情核对、接口无完整 Key、管理员/普通会话独立退出，以及普通用户之间任务隔离。
- 已查看列表和详情截图；Key 标识保持单行，窄表格沿用横向滚动。1280/1920/390 三种宽度在独立浏览器拦截所有后端请求的展示检查中通过，包括“暂不可用”展示；该检查未访问数据库。最终截图 `/tmp/banfei-admin-key-hint-final.png` 使用合成展示数据。
- 日志：`/tmp/banfei-admin-key-hint-{backend,build,browser,browser-recheck}.log`。数据库测试只使用专用验证库临时 schema，无正式库测试写入或模型调用。3000/8000 已恢复，改动保持未提交、未 push/deploy。
