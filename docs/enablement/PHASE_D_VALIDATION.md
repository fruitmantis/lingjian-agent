## 1. 结论与适用范围

**最终建议：CONDITIONAL GO。** 工程自动化与 mock 兼容性达到本次门槛；真实模型授权、首批业务资源与人工业务评审尚未完成，不能宣布真实业务上线。

- 代码：完成 NFR-04 局部时限修正，未扩充业务功能。
- 工程/mock：最终后端全量 390 个不同用例通过（按端口隔离分为 389 + 1）；完整浏览器 56 个用例通过。此前定向重跑不重复计入最终数量。
- 真实模型：**BLOCKED - USER AUTHORIZATION REQUIRED；NOT RUN；0 CALLS**，服务商/模型/时间均未选择、未执行；历史批量 DeepSeek 授权不用于本轮。
- 首批真实资源：**DATA-01 / DATA-02 = BLOCKED - BUSINESS DATA REQUIRED**。
- 真实业务试点、真实判断质量与业务方人工验收：**NOT RUN**。
- 状态文案与外发可读性留有产品评审项，详见视觉复核；安全字段白名单未扩大。

## 2. Phase A/B/C 当前实现与 Phase D 改动

本轮重新执行验证后确认：Phase A 课程/实验、人工核验、共享案例独立版本和三维权限仍可用；Phase B 中心/资源/伙伴/项目/场景/统一任务融合保持；Phase C Request/Plan/Run/Version、诊断、候选校验、编辑、确认、归档、撤权和伙伴可传递白名单的 mock 闭环通过。

产品代码修正集中在 NFR-04，位于 `backend/app/development_deadlines.py`、`development_lifecycle.py`、`development_engine.py`、`development_model.py`：默认模型 180 秒、Run 600 秒；测试可缩短但不能延长；主动回收超时运行、保存事务前后复核执行权和时限，并防止迟到诊断继续发起下一次模型调用。模型适配使用 HTTP 读取超时与 asyncio.timeout 整次请求到期取消，迟到输出不得保存。

先写回归复现了超过 601 秒的 Run 仍能保存（1 failed）；后续分段慢回包测试又复现 0.25 秒上限实际耗时 0.486 秒（1 failed）。分别修正 Run 时限与 HTTP 整次调用时限，并重跑最终回归。未改动接口、路由、资源/案例模型、权限、外发字段或前端业务行为；新增内容其余为测试、截图和报告。

## 3. 稳定版与隔离保护

- 原目录 `/home/yuan/project/lingjian-agent`、main `f79cbb29ec7b3ad70c88e618e3161211f211c06a` 保持；167 个受保护文件哈希变化数为 0，原工作区 clean。
- 稳定数据库仅做文件 SHA-256 检查；未用 SQLite 连接，未登录、创建 session、更新 last_login_at 或写入审计。8000 仅匿名 `/health`，3000 不执行认证/E2E。
- 8000 原 PID 227786、3000 原 PID 236033 的 cwd 保持，健康正常。
- 依赖、构建、配置及 `.isolation/runtime` 保持独立；9 个运行数据/上传文件均为本地普通文件，无软/硬链接到旧数据。
- pytest / 进程故障使用 `/tmp` 私有目录；E2E 使用 `/tmp/lingjian-enablement-e2e`、3100/8100/mock 18180。只停止本次创建的进程。
- 未修改 main 指针；未 merge、push、部署或远端同步核验。

证据：`artifacts/enablement-phase-d/startup-verification.json`、`protection-verification.json`、`docs/enablement/PHASE_D_SCOPE.md`。

## 4. Schema 与迁移回归

本阶段 **schema 无变化：12 → 12，共 32 表**。使用 SQLite 官方 backup 保存独立库快照 `.isolation/snapshots/phase-d-pre.db`；与独立运行库逐表行摘要一致、integrity_check=ok。

旧快照已存在 2 条 cases 外键异常；本次新增 0 条，未修复原业务数据。v9→v10、v10→v11、v11→v12 的增量迁移、重复执行、逐点失败与恢复在测试副本重跑通过；未在稳定库执行迁移。私有快照不进入 Git；其他机器重放真实快照测试须另行提供获准快照。

证据：`schema-verification.json`，`backend/tests/test_enablement_migration.py`、`test_enablement_workspace.py`、`test_development_migration.py` 的本阶段结果。

## 5. 可靠性、并发与事务

| 项目 | 本阶段实际验证 | 结果 |
|---|---|---|
| NFR-01 | 50 次 HTTP 创建，3 秒 slow mock，每次 202 时该 Run 尚未完成；页面刷新保留已落库版本 | PASS |
| NFR-02 | 2000 课程/实验 + 1000 共享案例；60 次目录检索、30 次模型候选过滤 | PASS |
| NFR-03 | 3 个 owner / 3 个 partner / 3 组课程和案例；诊断调用 barrier 同时进入；各一版本、无交叉 ID | PASS |
| NFR-04 | 默认 180/600 秒；0.08 秒 slow mock、0.25 秒分段回包、0.2 秒 Run 看门；无页面查询仍中断、可重试、确认 V1 保留 | PASS |
| NFR-05 | 在自己创建的 8100 进程 running 时 kill；重启恢复 interrupted，重试生成 V2，confirmed 仍 V1 | PASS |
| NFR-06 | 同 submission 同请求重放同 Plan/Run；不同 payload 409；并发 claim 唯一、同 Plan revise 唯一执行权 | PASS |
| NFR-07 | 已有 current V2 / confirmed V1，在 Version、Item、Diagnosis、current 指针四处注入 SQLite 失败；逐表行不变、无孤儿、重试可生成 V3 | PASS |
| NFR-08 | 原功能后端和完整浏览器重新回归，未只运行新增模块 | PASS |

时限采用同一生产逻辑的短时限注入，未实际等待 180 秒/10 分钟。性能只代表本地 WSL 单实例验收，不含浏览器与外部来源耗时，不宣称生产 SLA 或高于 3 并发的容量承诺。统计方法为 nearest-rank P50/P95，无剔除慢样本。

## 6. 安全、三维权限与撤权

A/B/admin 后端验证覆盖列表、详情、revise、edit、confirm、transferable、copy、archive/restore；B 访问 A 的方案返回 404；admin 保留全量权限。系统/模型/外发 8 种权限组合在资源和案例投影重跑，并增加发展方案候选/外发组合验证。

金丝雀 `INTERNAL_SECRET_PHASE_B_DO_NOT_SHARE` 在授权内部上下文中直接断言存在；在模型请求、生成持久化字段、preview/copy、错误、应用日志和审计字段中直接断言不存在。最终测试日志另做字符串扫描。未发现越权、金丝雀泄漏或失败 Run 覆盖 confirmed 的严重阻断问题。

普通课程下架：历史名称/快照不变、当前不可用、redirect 不返回 URL、后续候选不包含，不静默替换。案例正常停止共享：旧快照保留，当前正文/入口/外发隐藏，后续 revise 的模型请求不包含旧案例。敏感撤权：版本数据库内容不变、当前访问隐藏并提示重新生成/联系管理员、copy 禁止；重新发布 V2 后，旧 V1 引用/授权 epoch 不会复活。为覆盖说明文字中的来源内容，继续沿用保守的整份受影响生成内容隐藏策略。

## 7. 模型兼容性与固定样例

本地 OpenAI-compatible HTTP mock 验证了：strict JSON schema 请求字段、正常 JSON、Markdown 包裹、空响应、非法 JSON/enum、HTTP 503、slow timeout、分段慢回包总时限、失败后重试。正常响应通过严格校验；Markdown 包裹仍被拒绝，未做放宽兼容；其他非法响应进入失败且原 V1 可用。**这不证明 DeepSeek/GLM 等真实供应商接受该 schema。**

既有恶意 mock 回归包含伪造 partner/resource/case/version、URL、非法 enum、额外字段、内部备注和强结论，非法结果不能产生有效版本。实际外发 URL 始终由当前授权资源解析，未放宽 ID/URL/schema 校验。

固定样例：

- 同一伙伴“数据库迁移 / Agent 应用交付”：使用现有数据库/盘古大模型正式标签的两组人工指定测试目标；断言能力标签、trainable_gap 与候选资源 ID 集合不相交。它证明结构化检索按目标变化，不证明真实模型能自动选择正确业务目标。
- missing/partial 证据均保持 needs_assessment / model_inference；模型“确认不足”不进入正式强结论。
- 地域/人力/商务/资质属于 non_training_constraint；强行安排培训资源的 mock 被拒绝。
- 缺实验使用“当前资源库未找到匹配实验”并形成 ready，不虚构实验。
- unknown 条件保持 unknown，不能转为 meets。
- 人员基础未知时不建任务；用户显式接受假设后落库并在保存版本/刷新后展示。
- V1 confirmed 后 revise 失败，current/confirmed 均不被失败覆盖。

这些是合成样例的自动化验收框架；固定真实样例和业务判断质量仍需业务负责人签审。

## 8. 实际命令与结果

在新 worktree，最终后端按端口隔离执行，未遗漏固定 8100 用例：

```text
.venv/bin/python -m pytest backend/tests/test_phase_d_model_and_samples.py backend/tests/test_phase_d_process.py -q --tb=short -o junit_family=legacy --junitxml=.isolation/logs/phase-d-adapter-final.xml
.venv/bin/python -m pytest backend/tests --ignore=backend/tests/test_phase_d_process.py -q --tb=short -o junit_family=legacy --junitxml=.isolation/logs/phase-d-backend-final.xml
```

第一批 11 passed，包括 8100 kill/restart/performance 用例；第二批 389 passed，包括第一批中 10 个适配/样例用例。去重后 **全量 390 passed / 0 failed / 0 skipped**。第二批排除的唯一进程用例已在第一批通过，避免与最终浏览器共享 8100。

在新 worktree 的 frontend：

```text
npm run typecheck
npm run build
PLAYWRIGHT_JSON_OUTPUT_FILE=../.isolation/logs/phase-d-browser-final.json npx playwright test --reporter=line,json
```

最终完整浏览器 **56 passed / 0 failed / 0 skipped**；typecheck/build PASS。构建在独立前端服务启动前执行，之后产品前端未修改，仅补充测试及截图采集。最终后端/浏览器日志与逐项耗时由机器证据保存。

此前全量后端 374、撤权补充 11、固定样例补充 4、完整浏览器 54、假设补充 2、截图重采集 5 均曾通过；总时限适配修正后又执行上述最终全量验证，不将重复执行累加为不同测试数量。

原有两条 Starlette 422 常量弃用警告仍存在。浏览器有既有 Next 开发跨源提示与终端颜色环境警告，未借机升级依赖。

迭代失败未隐瞒：时限回归修复前 1 failed；分段慢回包总时限修复前 1 failed；新固定样例最初使用不存在的“AI”标签名称，1 failed，改为现有正式标签后通过。前两项是实际可靠性缺陷，最后一项为测试 fixture 名称错误。最终各批结果以机器证据为准。

## 9. 完整原功能回归

| 范围 | 实际后端测试 | 实际浏览器测试 |
|---|---|---|
| 伙伴匹配与支撑证据 | test_recommendations / test_model_errors | batch3-quality / release-validation |
| 创建、详情、归档、恢复、重试 | test_task_creation / test_tasks / test_process_recovery | task-navigation / batch2-resilience / release-validation |
| A/B owner、需求画像、项目机会 | test_authorization / test_demand / test_tasks | release-validation / batch3-quality |
| 伙伴洞察、原案例、材料 | test_profile / test_files / test_authorization | release-validation / enablement-workspace |
| 场景广场、App Shell | test_enablement_workspace | enablement-workspace / visual-parity |
| 管理后台 | test_authorization / test_system_status | release-validation / enablement-admin |
| 用户申请、审批、首次改密、锁定 | test_applications / test_auth | release-validation / batch2-resilience |
| 模型配置、系统状态 | test_model_config / test_system_status | batch3-quality / release-validation |
| A 资源后台、B 资源中心、C 方案 | test_enablement* / test_development* / test_phase_d* | enablement-admin / enablement-workspace / development-assistant / phase-d-assumptions |

结果均 PASS，逐用例行号与耗时见 backend-test-results.json / browser-test-results.json。匹配与用户测试全在隔离库，无稳定版登录。

## 10. 视觉、可读性与证据包

52 张合成截图：两种视口各 17 张方案/表单状态 + 9 张原页面回归。包括中心、完整诉求、V1 draft/confirmed、V2 draft/confirmed V1、诊断、安排、缺口、失败保留旧版、编辑、外发、撤权、统一任务、资源、伙伴、匹配、场景、显式假设。清单记录每张图的视口、实际图像尺寸和 SHA-256。

无横向溢出、导航可见及页面错误检查通过。可读性复核和未关闭状态文案问题在 `docs/enablement/PHASE_D_VISUAL_REVIEW.md`；不把自动化布局通过说成业务体验已签审。

核心文件：

- PHASE_D_ACCEPTANCE_MATRIX.md：53 个 P0 与 ACC-01～20 的逐项证据。
- FIRST_PILOT_DATA_CHECKLIST.md：真实能力方向、伙伴、课程/实验/共享案例、元数据、人工核验及三维权限清单。
- artifacts/enablement-phase-d/validation-results.json
- artifacts/enablement-phase-d/acceptance-matrix.json
- artifacts/enablement-phase-d/screenshot-manifest.json
- artifacts/enablement-phase-d/protection-verification.json
- artifacts/enablement-phase-d/backend-test-results.json / browser-test-results.json / schema-verification.json

原始 JUnit、Playwright JSON 与日志保留在 `.isolation/logs`，不提交；机器证据提供它们的哈希及脱敏测试清单。没有提交数据库、上传文件、实际密钥或敏感日志。

## 11. 未完成与最终条件

1. 真实模型受控验证：缺本轮授权，D3 整体 BLOCKED。获准后需记录服务商、模型、输入范围、每次调用与时间，执行正常/资源缺口/证据不足/非培训限制/unknown/revise/供应商异常，不绕过当前校验。
2. 首批正式数据与真实路径：DATA-01/02 BLOCKED；课程/实验和共享目录不能用本轮合成 fixture 顶替。需要业务签审清单。
3. 固定真实业务样例、伙伴沟通可读性：NOT RUN。当前外发通用阶段和元数据偏机械；仅提出未来受控 partner_facing_summary 建议，没有开放任何内部字段。
4. 状态文案：列表/侧栏的最近 Run “失败”和详情 Plan “进行中”可能误读；旧版本仍可用已验证，呈现规则需产品复核。
5. 既有两条 cases 外键异常保留，资源运营前需业务确认归属；不批量修复旧库。
6. 验证针对 SQLite 单实例、3 并发和规定资源规模；不承诺更高容量、长周期稳定性或生产可用性。

因此可提交最终工程评审，**不能作为无条件业务上线 GO**。未发生需停止相关验收的越权、泄漏或 confirmed 被失败覆盖事件。

## 12. 停止与交接

新版 3100/8100/mock 18180 已由测试生命周期停止，端口最终检查无监听；旧版 3000/8000 原进程继续运行，无需重启旧服务或登录旧版完成任何交接操作。

以后只在明确授权启动新版时使用新 worktree 的 `bash enablement-dev.sh start|stop|status`；脚本核验归属，不操作原目录 dev.sh 或宽泛 kill。当前独立运行库未写入本轮合成资源。

本轮到 Phase D 证据交付为止：不 merge、不 push、不部署、不宣布真实业务上线。等待用户审核本报告及条件项。
