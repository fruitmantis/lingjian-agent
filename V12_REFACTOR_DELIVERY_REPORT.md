# V1.2 重构交付

结论：**READY FOR V1.2 MANUAL REVIEW**。新版保持运行，可开始人工体验；这不代表真实模型或真实业务验收通过。

## 分支与改动

- 工作目录：`/home/yuan/project/lingjian-agent-enablement`
- 分支：`feature/partner-enablement-v1.1`
- 功能代码 HEAD：`f00c67f3a305ebb5fcd257545df26d73bba55fa0`；后续交付提交仅包含截图、测试取证等待和本报告。
- 本轮功能提交：`4089bea`（V1.2 主流程与测试）、`f00c67f`（资源检索相关性修正）。交付归档 HEAD 为本报告所在提交，可用 `git log -1 -- V12_REFACTOR_DELIVERY_REPORT.md` 查询。
- 唯一需求基线：已评审的《灵鉴Agent全局需求与架构设计说明书 V1.2 评审修订稿》。未新建分支或 worktree，未 merge、push 或部署。

首页只保留“目标伙伴”和自然语言“发展方向”，按钮为“生成能力发展建议”。人数、岗位、基础、周期、投入、预算、硬约束、目标能力手选、确认能力不足等旧表单已移除，没有折叠或高级设置入口。数据库旧字段保留，但不再构成生成门槛；schema 仍为 12，无破坏性迁移。

## 当前 Agent 流程

1. **先理解方向，再检索资源。** 综合请求与当前获准画像形成可复用基础、能力重点和检索词。分析时不传资源库存，避免用课程数量决定发展优先级。正式标签优先关联；无法对应时保留自然语言重点，不创建新标签。
2. **每次读取最新画像。** 使用获准的能力、AI 画像、行业、服务领域、案例/交付件数量及可发送模型的已发布共享证据；已有服务等级字段时才使用，不把健康度当等级。画像有限仍可生成建议。原始附件、内部案例正文和交付件内容不进入模型。生成按钮说明使用范围；API 未授权画像使用时仅依据方向。
3. **检索不唯标签。** SQLite 同时使用正式标签、名称、摘要、用途、技术方向、适用对象及分析生成的主题词，排除仅由通用岗位词引入的不相关资源；先做发布、版本与三维权限检查。未新增向量库或能力字典。
4. **输出随意图变化。** 综合发展/探索问题返回分析和建议；简单课程/实验查询直接检索，不调用模型；“只给进阶实验”不生成完整长报告。资源类型不要求凑齐；缺实验、费用未知仍是成功业务结果。账号、环境、费用、先修等条件如实展示。
5. **解释与修改分开。** 解释原因、比较资源直接回答并保留对话，不建 Run/Version；实际调整创建新 Run，成功后生成新草稿，旧版本保留。草稿可直接查看、打开资源、提问和修改。confirmed 仅用于标记采用版本及伙伴可传递视图。

继续复用资源中心、共享版本、Review、三维权限和撤权、后端解析来源链接、Plan/Run/Version、幂等、事务、并发冲突、超时/重启恢复以及统一任务历史。失败调整不覆盖可用版本。学习/跳转不会更新正式能力、服务等级或画像结论。伙伴可传递视图白名单未扩大。

实现主要位于 `backend/app/development_{types,lifecycle,engine,views}.py`、`backend/app/routers/development.py`、`backend/app/enablement_catalog.py`、`frontend/components/development-assistant.tsx`、`enablement-workspace.tsx` 及场景/入口文案。新增认证接口 `POST /development/plans/{id}/conversation`，无新服务或权限体系。

## 验证

| 检查 | 最终结果 |
|---|---|
| `.venv/bin/python -m pytest backend/tests -q --tb=short` | 492 passed，0 failed，0 skipped；2 条既有 Starlette 弃用提示 |
| `cd frontend && npm run test:e2e` | 57 passed，0 failed，0 skipped；另补跑 2 项截图状态核对通过 |
| `cd frontend && npm run typecheck` | PASS |
| `cd frontend && npm run build` | PASS |
| V1.2 关键截图 | 1366×768、1920×1080；无横向溢出，侧栏与任务详情状态均可辨识 |
| 新版实际 API/UI 体验 | PASS：dev_admin 登录、资源页面、A～E 五个 ready 任务及解释/比较/修改链路 |

已重跑原伙伴匹配、任务、需求画像、项目机会、伙伴洞察、场景广场、管理后台、用户、模型配置、系统状态、资源中心、共享案例，以及版本、权限、撤权和失败恢复测试。旧人员/周期/强制诊断等测试已按 V1.2 改写，没有为旧测试保留门槛。

关键截图共 10 张，位于 [artifacts/v12/screenshots](artifacts/v12/screenshots/)：`01-minimal` 极简首页、`02-advice` 完整建议/草稿状态、`03-explanation` 对话解释、`04-short-revision` 仅实验响应与 V2 draft/confirmed V1、`05-resource-gap` 资源缺口；每组各 1366 和 1920 两个宽度。

## 打开新版体验

- 页面：[http://localhost:3100/enablement](http://localhost:3100/enablement)
- 后端：[http://localhost:8100/health](http://localhost:8100/health)
- 管理员：`dev_admin`，沿用当前新版开发账号密码。密码只保存在本机私有文件 `.isolation/runtime/dev/login.json`，本报告不打印凭据。
- 实际数据库：`/home/yuan/project/lingjian-agent-enablement/.isolation/runtime/dev/app.db`
- 上传材料与日志均在新版 `.isolation` 内；dev 数据库来自独立副本，并在重构前使用 SQLite backup 保存快照。
- `partner_development`：`manual-local-mock` / `local-development-mock`，`http://127.0.0.1:18180/v1`。新版后台禁止非本机网络连接。
- **REAL MODEL CALLS = 0**。未调用 DeepSeek、GLM 或其他外部模型。

请选择“测试伙伴 A（合成：数据交付基础）”或“测试伙伴 B（合成：Web 应用基础）”。已增加数据库/Agent 两类资源：4 门课程、4 个实验、2 个共享案例，均明确标为合成开发测试；保留原开发资源，当前共 7 门课程、6 个实验、3 个已发布共享案例。特意不配置 RAG 专用实验，用于体验正常缺口提示。

已用 local mock 在当前环境实际完成五个合成体验任务，并保留到统一任务历史；Agent 任务还保留了两条解释问答及 V2 草稿 / 已确认 V1。

建议依次体验：A 的数据库迁移、A 的 Agent 应用交付、B 的同一 Agent 方向、探索下一步方向、只给进阶实验；进入任务后问“为什么推荐这个方向”“这两个实验有什么区别”，再说“不要基础课，多给实验”。

## 保护结果与当前限制

- main 仍为 `f79cbb29ec7b3ad70c88e618e3161211f211c06a`；旧目录 167 个受保护文件及新版源 `.isolation/runtime/app.db` 哈希未变。
- 旧版 3000/8000 原进程保持运行，未登录旧版、未写旧数据库。新版 3100/8100/18180 已恢复并保留运行。
- 开发数据库完整性检查为 `ok`；原有 2 条历史外键异常保留，本轮未新增，未批量修复历史数据。
- local mock 是针对合成体验场景的确定性模拟，用来验证方向、画像、资源和对话流程；不能据此认定真实模型已经具备同等理解/生成质量。通用自然语言效果待你确认交互后另行授权真实模型测试。
- 合成资源链接用于展示与跳转流程，不是真实可学习的课程/实验；资源适用性、内容质量和真实业务效果尚未验收。

**READY FOR V1.2 MANUAL REVIEW**
