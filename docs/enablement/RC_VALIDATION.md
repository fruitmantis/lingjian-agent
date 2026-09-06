## 范围、基线与保护

本轮为 RC 准备，仅关闭 Plan/Run 状态表达问题并准备试点门禁，未进入新功能 Phase。

- 开始时功能分支 HEAD 精确为 `78e70ac0f3e258d3f4ce51a8ca60455a8887028d`，工作区 clean。建立 `phase-d-engineering-accepted-20260906-78e70ac`，没有建立“业务已验收”含义的标签。
- Phase C tag `phase-c-accepted-20260906-351489c` 保持 `351489c3d3c89899837930bd7aab01fe61f4a52a`。
- 稳定 main 保持 `f79cbb29ec7b3ad70c88e618e3161211f211c06a`，原目录 `/home/yuan/project/lingjian-agent` 未修改。保护证据见 `artifacts/enablement-rc/protection-verification.json`。
- 旧版 3000/8000 仅做进程/cwd、Git/文件哈希和匿名 `/health`；无旧版登录、会话、审计、last_login、SQLite 写入或迁移。167 个保护文件起止哈希比对，旧数据库仅做文件哈希，不连接 SQLite。
- pytest 数据库为 `/tmp/lingjian-pytest-*`；Playwright 使用 `/tmp/lingjian-enablement-e2e/app.db` 和独立上传目录，前端 3100、后端 8100、mock 18180。原服务 PID/cwd 在结束时再次核验。
- schema 仍为 **12**（读取 app_metadata.schema_version，非 SQLite PRAGMA user_version）；无迁移、数据模型或 Run 状态变更。没有动稳定版模型配置或写入正式资源。
- Phase D 已验收截图/证据保持原样，本轮新证据进入 `artifacts/enablement-rc`。

## 修改内容与接口兼容

1. `backend/app/development_views.py` 新增只读 `presentation` 派生，分别判断 current/confirmed 当前可读性、版本编号及最新 Run 原始状态/类型。来源撤权继续使用原 `protected`，不会由指针存在推导可用。
2. `backend/app/routers/match.py` 在统一用户/管理员列表和任务详情增加可选 `planPresentation`。既有 taskStatus、task_type、owner 规则、筛选和分页不变，没有新增路由。
3. `frontend/components/plan-status.tsx` 提供统一展示，接入 `task-list`、`task-navigation`、`development-assistant`，样式增量在 globals.css。现有匹配任务仍沿用原状态展示。侧栏“当前查看”的较早/归档方案响应任务变化事件并定时重验，拒绝迟到响应覆盖新状态；确认/归档无需整页刷新。
4. 前端 E2E 共用新的 evidenceRoot，防止覆盖已验收 Phase D 截图；新增 RC 状态场景及仅 `/tmp` 可用的中断展示测试夹具。

具体状态文案与伙伴可传递视图产品评审见 `docs/enablement/RC_PRODUCT_REVIEW.md`。`transferable` 白名单、三维权限、模型上下文与模型调用适配代码未扩大。

## 状态场景验证

| 场景 | 工程验证 |
|---|---|
| 首次生成失败、无版本 | 主状态 generation_failed；无 current/confirmed；失败真实状态不改写 |
| 首次正在生成、无版本 | generating，与已存在版本的业务可用性区分 |
| V1 draft | draft，当前草稿 V1、尚未确认 |
| V1 confirmed | available，已确认 V1 |
| V2 draft / confirmed V1 | available，同时显示当前草稿 V2、已确认 V1 |
| V2 调整失败 / confirmed V1 | available，current/confirmed 仍 V1，辅助最近调整失败 |
| V2 调整中断 / confirmed V1 | available，current/confirmed 仍 V1，辅助最近调整中断 |
| archived | archived，版本与 Run 保留 |
| 撤权后的版本 | restricted；不得误报为方案可用 |

`backend/tests/test_rc_presentation.py` 9 项覆盖真实生命周期、用户/管理员列表、侧栏任务详情投影一致性及 user B 隔离。`frontend/e2e/rc-plan-status.spec.ts` 在两个指定视口串行验证六类版本状态的详情、侧栏和列表，并断言失败调整的主状态不是 failed。

中断**展示**截图使用明确受限于 `/tmp/lingjian-enablement-e2e/app.db`、用户 A、RC 合成目标且已终止 Run 的测试夹具；不把它冒充 kill/restart。本轮全量后端另实际重跑 `test_phase_d_process.py` 的独立 8100 kill/restart/重试与确认版本保留验证。

## 实际执行命令与结果

工作目录除前端命令外均为功能 worktree。完整结果逐例记录于 `artifacts/enablement-rc/backend-test-results.json`、`browser-test-results.json`、`validation-results.json`。原始日志保留在被 Git 忽略的 `.isolation/logs`，机器结果记录其 SHA-256，不提交凭据或运行日志。

| 命令 | 结果/证据 |
|---|---|
| `.venv/bin/python -m pytest backend/tests/test_rc_presentation.py -q` | 修正测试夹具重复 run_id 后 9 passed；最初 8 passed / 1 fixture failure，未放宽业务约束 |
| `.venv/bin/python -m pytest backend/tests -q --junitxml=.isolation/logs/rc-backend.xml` | **399 passed / 0 failed / 0 skipped**，256.15 秒；15 条既有警告 |
| `cd frontend && npm run typecheck` | PASS，tsc --noEmit，退出 0 |
| `cd frontend && npm run build` | PASS，生产编译、类型检查、页面生成完成，退出 0；没有与开发服务并行写 .next |
| `cd frontend && PLAYWRIGHT_JSON_OUTPUT_FILE=../.isolation/logs/rc-browser.json npm run test:e2e -- --reporter=line,json` | 最终 **58 passed / 0 failed / 0 skipped，退出 0，395.17 秒**。初轮 56 passed / 2 failed（新增 helper 误解析合法 204）；修正后定向 2 passed。补侧栏刷新时一轮出现 Fast Refresh 导致导航中断（57 passed / 1 failed），已保留原始记录；另一次完整运行末尾收到 SIGTERM（退出 143），最终 JSON 未完成，未计为通过；保留中断日志并用独立 PID/退出码记录的测试驱动重新执行冻结代码完整套件。未改业务 API |

全量测试涵盖旧匹配/需求画像/项目机会、任务创建/详情/重试/归档/恢复、A/B/admin、伙伴洞察/原案例、场景、后台、用户申请审批/首次改密/锁定/会话失效、模型配置/系统状态以及 Phase A/B/C。没有只跑新增模块冒称全量通过。真实模型兼容性未执行；任何 mock 结果都不记为真实供应商通过。

## 截图与视觉复核

机器清单 `artifacts/enablement-rc/screenshot-manifest.json` 包含每张图的路径、SHA-256、像素尺寸及实际视口。1366×768、1920×1080 均采集：

- `rc-states/01-v1-draft-*`：V1 草稿。
- `rc-states/02-v1-confirmed-*`：V1 已确认。
- `rc-states/03-v2-draft-*`：V2 草稿、已确认仍为 V1。
- `rc-states/04-failed-revise-*`：V2 调整失败、已确认 V1 仍可用。
- `rc-states/05-interrupted-revise-*`：V2 调整中断、已确认 V1 仍可用。
- `rc-states/06-archived-*`：归档方案，历史保留。

每类均有 `detail-sidebar` 和 `list` 两种页面证据；侧栏当前条目滚动到可视范围。自动断言无页面横向溢出、关键状态在视口范围内且未被覆盖；确认版和失败 Run 同时可见。旧发展中心、资源、案例/伙伴/匹配/场景和任务类型等复用全量截图保存到本轮目录。

人工图像抽查清单已写入 `RC_VISUAL_REVIEW.md`；此处“图像复核”是工程视觉检查，不是业务方签字。

## 数据与真实模型门禁

- `FINAL_PILOT_DATA_GAP.md`：独立库实际 33 家伙伴、3 条内部案例、**0 课程/实验、0 案例共享配置、0 发展方案**，未收到业务批准试点包。既有内部案例不能当共享版本，合成 fixture 不算正式资源。
- DATA-01：BLOCKED，需要业务确认方向、课程/实验/共享案例、映射、访问条件、人工链接核验及可走通的真实路径。
- DATA-02：BLOCKED，工程结论已形成，但还缺“首批业务数据可用”的独立签审；两者均通过才可进入真实业务试点。
- `REAL_MODEL_VALIDATION_PLAN.md`：本轮 0 CALLS。建议未来另行授权最多 16 次外部请求，按两次调用/Run 区分诊断与方案。partner_development 当前无有效显式绑定，未来需仅在专用测试库绑定批准配置并先实现/验证逐调用预算和 usage 观测；未擅自改配置。
- `REAL_BUSINESS_ACCEPTANCE_TEMPLATE.md`：留空给业务负责人填写同伙伴两个不同目标、允许资源、证据不足/已确认差距/非培训限制与人工评审结果；BUSINESS ACCEPTANCE NOT RUN。

## 剩余限制与停止方式

- 伙伴可传递文本仍使用安全白名单；阶段目标、推荐理由、缺口的业务可读性需要真实数据下人工评审。只建议未来受控 partner_facing_summary 契约，本轮未新增字段或扩大权限。
- 状态筛选继续按既有执行结果筛选，不新增 Plan 状态筛选或第二套历史列表；列表呈现明确区分业务可用性与执行结果。
- 既有 15 条后端警告及 Next 开发服务跨来源预警未作为本轮范围扩展处理；全量测试/生产构建是否通过以实际结果为准。
- 本轮没有处理既有孤儿案例或历史数据问题，未对原库做修复；真实资源上线前仍需业务核验。
- 完成后新版 3100/8100/mock 18180 均停止，旧版 3000/8000 保持原进程运行。继续使用旧版无需迁移、合并或切换分支，沿用原访问入口即可。
- 未 merge main、未 push、未部署、未替换旧服务、未调用真实模型。未核验 GitHub 服务端，不声称远端同步。

当前仅 **ENGINEERING READY / CONDITIONAL GO**；REAL MODEL NOT AUTHORIZED，BUSINESS DATA BLOCKED，BUSINESS ACCEPTANCE NOT RUN。等待用户提供真实业务数据及明确模型授权后，才进入最终 RC 验收；不是正式上线许可。

## 最终提交状态

用户已明确授权本地 RC 归档。报告源文件、机器证据、测试脚本和截图随本地 RC 归档提交；不包括数据库、上传材料、运行凭据或原始日志。归档提交与 accepted 标签由 Git 核验，不代表真实业务上线通过。

`artifacts/enablement-rc/code-baseline.json` 记录实际通过测试的代码提交 066f782 及逐文件 SHA-256、目录 tree ID。归档新增文档和证据不改变被验证的产品与测试代码；不得将“归档提交号不同”误解为重跑了测试，也不得把旧 hash 写成新测试结果。
