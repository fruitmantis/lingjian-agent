> **历史归档，不是当前开发规范。** 保留当时的需求、环境、测试和结论；旧品牌、分支、端口、数据库及授权状态均不代表当前 main。历史命令不可直接用于现有运行库。当前入口：[README](../../../../README.md)。

## 交付结论与阶段边界

Phase B 前台融合代码已实现，自动化回归与生产构建通过。当前能力是资料准备、真实资源检索、来源上下文联动和任务类型展示；**不表示发展方案业务已经可用**。

- 代码实现：本报告列出的 Phase B 范围已完成。
- 自动化测试：完整后端 296 项、完整浏览器 51 项通过；最终核验人补充后，定向 26 项后端与 8 项浏览器再次通过。
- 真实模型验证：本轮未执行，真实模型调用 0 次；不计为“模型验证通过”。
- 业务验收：Phase 0/A 已由用户验收；Phase B 业务与视觉验收仍待用户评估。合成测试不能替代真实资源、试点伙伴及方案业务验收。

## 旧版保护与隔离环境

| 项目 | 本次实际核验 |
| --- | --- |
| 稳定目录 | `/home/yuan/project/lingjian-agent` |
| 稳定分支 / 提交 | `main` / `f79cbb29ec7b3ad70c88e618e3161211f211c06a` |
| 基线标签 | `baseline/pre-enablement-20260905-f79cbb2`，沿用 Phase 0 标签 |
| 原工作区 | Git clean；163 个受保护源码、配置及上传文件哈希均未变化 |
| 旧服务 | 后端 8000 / PID 227786；前端 3000 / PID 236033，启动目录仍为原目录及其 frontend |
| 独立目录 | `/home/yuan/project/lingjian-agent-enablement` |
| 独立运行库 | `.isolation/runtime/app.db`，现为 schema v11 |
| 独立上传目录 | `.isolation/runtime/uploads`，8 个独立普通文件，无软链接或硬链接写回旧数据 |
| 一致性备份 | `.isolation/snapshots/phase-b-pre-v11.db`，使用 SQLite backup API 从独立 v10 运行库保存 |
| 配置 / 依赖 / 输出 | 本 worktree 的 `.env`、`frontend/.env.local`、`.venv`、`frontend/node_modules`、`frontend/.next`；日志 `.isolation/logs` |
| 实际验证端口 | 前端 3100、后端 8100、本地 mock 18180；CORS 和前端 API 均使用新版端口 |
| 自动化数据 | pytest `/tmp/lingjian-pytest-*`；Playwright `/tmp/lingjian-enablement-e2e`；不写原业务库 |
| 交付时运行状态 | 新版和 mock 均停止，3100/8100/18180 无监听；原 3000/8000 继续运行 |

未执行远端核验，不声称与 GitHub 服务端同步。没有修改 main 指针、merge、push、部署或替换稳定服务。

旧数据库对照需要单独说明：与 **Phase 0 快照** 比较，16 张既有数据表中有 14 张内容完全一致；`users` 只变化 `last_login_at` / `updated_at`，`user_audit_logs` 只追加 1 条 `auth.login_success`（UTC 2026-09-05 23:14:25）。用户集合、密码、角色、状态等字段未变，旧审计记录未改写。该对照不是同一时刻的 Phase B 前后快照，不能据此宣称旧库字节完全未变；已保留登录现场，未回写或清理。

## 需求编号与已实现内容

| 编号 | 实现及证据 |
| --- | --- |
| NAV-01 | 侧栏新增“伙伴服务能力发展中心”；开启新任务、场景广场、伙伴洞察、全部任务、个人中心及有权限用户的管理后台入口保留；复用 App Shell。 |
| NAV-02 | 任务响应显式返回 `task_type=partner_match`；用户和管理员列表可筛选类型；`development_plan` 返回真实空结果。详情保留匹配主体，未知/未开放类型不伪装为方案结果。 |
| SCN-01 | 能力发展类别新增“制定伙伴服务能力发展方案”“查找课程与实验”“学习优秀伙伴案例”；前者标记“可整理诉求”，原能力短板分析继续显示建设中。复用一个资料准备与资源检索能力，不把课程/实验/案例注册为独立 Skill。 |
| PRT-01 | 伙伴详情“制定发展方案”只传 partner_id；后端读取启用伙伴、当前可见画像、内部案例/交付物引用。不存在或无权查看的来源返回不可用。 |
| MAT-01 | 首页匹配结果和任务详情的推荐卡片增加“针对该项目制定发展方案”；只传 task_id / partner_id，后端重查任务所有权及实际推荐关系。带入原项目需求和风险，固定标记“待能力发展流程复核”；诉求输入保持空白，不自动形成培训需求。 |
| RES-02 | 课程/实验/案例 Tab；名称、能力、岗位、产品/技术、难度、语言、站点、发布状态、费用、账号、环境和先修条件筛选；分页。仅当前已发布且系统可见的内容可返回，已下架筛选没有可读内容。 |
| RES-03 | 资源卡片及详情展示目标用途、适用对象、预计投入、先修/访问条件、来源平台、当前人工核验可用状态。未知字段明确显示“未知”；展示当前发布版本的核验时间、核验人和核验内容。 |
| RES-08 | `POST redirect` 接收版本标识；后端在写事务中重新鉴权并解析来源 URL。事件仅 `redirect_initiated` / “发起跳转”，不记录学习、完成或能力提升。 |
| CASE-05 | 伙伴详情显示当前可读共享学习案例；共享案例可回到贡献伙伴或携带 case_id + case_version 进入发展中心；目标伙伴需明确选择。每次读取及发起跳转都重新校验共享状态，不使用内部案例正文填充共享资源。 |
| SEC / 共享约束 | 沿用有效会话、user/admin 与 owner 边界；A/B 越权 404；管理员也不能绕过前台发布/撤权门禁。复用 Phase A 的三维授权、发布版本和授权 epoch。系统内可见不代表模型发送或伙伴外发；未新增外发/复制接口。 |

## 页面、API 与数据结构改动

新页面：`/enablement`、`/enablement/resources/[type]/[id]`。前台主体为 `frontend/components/enablement-workspace.tsx`；复用全局蓝、青绿、白、浅灰视觉，没有独立培训系统 Shell。

已有页面：侧栏、`/partners/[id]`、首页匹配卡片、`/tasks` / `/tasks/[id]`、`/scenes` 增量融合；后台任务复用同一类型筛选组件。管理员用户、模型、标签、系统状态与原业务路由保持原实现。

新增受认证 API 共 5 个：

| 方法与路径 | 行为 |
| --- | --- |
| `GET /enablement/resources` | 筛选/分页当前有效发布版本；从快照字段查询，草稿标签映射不会污染发布结果。 |
| `GET /enablement/resource-filters` | 返回可见发布池中的元数据选项及现有正式能力标签。 |
| `GET /enablement/resources/{source_type}/{source_id}` | 字段白名单详情，可指定 source_version；旧版本、撤权、无效归属、失效标签不可读取。 |
| `POST /enablement/resources/{source_type}/{source_id}/redirect` | body 仅 source_version，不接受客户端 URL；保存发起跳转审计后返回已解析来源。 |
| `GET /enablement/context` | 从 partner_id / task_id / case_id / case_version 重建获准查看的来源上下文；不创建任务或写画像。 |

所有新增接口 `Cache-Control: no-store`。前台聚焦及每 15 秒重新核验；请求切换取消旧读取，读取失败清除内容；发起跳转前执行后端当前权限和版本校验。已被用户人工复制到系统外的资料不在页面撤权控制范围内，本轮未提供方案复制能力。

已有 `GET /agent/tasks`、`GET /admin/tasks` 增加 task_type 筛选，列表和详情返回实际类型。未新增 Development Plan 后端主对象或任务。

OpenAPI 当前 **76 paths / 91 operations**，公开操作仍仅健康检查、登录、内部账号申请 3 个；新增 5 个操作全部声明认证并使用有效用户依赖。

## 迁移前后及恢复路径

v10→v11 只新增 `resource_redirect_events` 及 actor/time 索引，事件类型约束为 redirect_initiated。记录 actor、资源三元引用、事件标识与时间，不存来源 URL、模型材料或学习结论。无旧业务表重建、清空或批量修复。

| 对照 | 迁移前 | 迁移后 |
| --- | --- | --- |
| schema_version | 10 | 11 |
| 原有 23 张表逐表内容哈希 | 基准 | 全部相同 |
| partners / cases / deliverables | 33 / 3 / 0 | 33 / 3 / 0 |
| match_records / demand_profiles / project_opportunities | 48 / 48 / 48 | 48 / 48 / 48 |
| 新跳转事件 | 无表 | 0 行 |
| integrity_check | ok | ok |
| 既有外键异常 | cases 行 3、4 引用缺失伙伴 | 同样 2 处；新增 0 |

事务中创建表/索引并更新版本，任一步失败 rollback。自动化覆盖三处故障注入、回滚后重试、重复执行；不会产生半完成迁移。已在 pytest 临时副本及独立运行库实测，原 v9 业务库未迁移。

回退无需动旧版：停止独立服务，继续原 3000/8000。若需要重建新版库，从保留的 v10 一致性快照在另一独立文件中恢复后重放迁移；保留当前 v11 库和事件记录用于排查，不直接覆盖原库或唯一备份。本轮没有执行恢复覆盖。

## 实际自动化执行结果

命令均从独立 worktree 执行。以下重复运行按实际批次记录，不相加伪装为不同用例数。

| 命令 / 批次 | 通过 | 失败 | 跳过 / 未运行 |
| --- | ---: | ---: | ---: |
| `.venv/bin/python -m pytest backend/tests/test_enablement_workspace.py backend/tests/test_enablement.py backend/tests/test_enablement_migration.py -q` | 71 | 0 | 0 |
| `.venv/bin/python -m pytest backend/tests/test_enablement_workspace.py -q -s`，性能及实际 v10 快照补充 | 23 | 0 | 0 |
| `.venv/bin/python -m pytest backend/tests -q`，首次全量 | 294 | 1 | 0 |
| 同上，更新 OpenAPI 清单并增加认证断言后 | 296 | 0 | 0 |
| `.venv/bin/python -m pytest backend/tests/test_enablement_workspace.py backend/tests/test_openapi.py -q -s`，最终核验人投影后 | 26 | 0 | 0 |
| `npm run test:e2e --prefix frontend -- enablement-workspace.spec.ts`，首次 | 1 | 7 | 0 |
| 同上，第二次 | 6 | 1 | 1 未运行 |
| 同上，第三次 | 8 | 0 | 0 |
| `npm run test:e2e --prefix frontend`，全量回归 | 51 | 0 | 0 |
| `npm run test:e2e --prefix frontend -- enablement-workspace.spec.ts`，最终补充后与截图更新 | 8 | 0 | 0 |
| `npm run typecheck --prefix frontend`，三次（含最终） | 均通过 | 0 | 0 |
| `npm run build --prefix frontend`，最终生产构建 | 通过 | 0 | 0 |

已解决的失败：OpenAPI 仍断言旧数量；select 缺少明确可访问名称；测试断言误包含侧栏状态和 Next announcer；fixture 重启重复准备造成同名测试记录；截图使用了错误的既有页标题和管理员自有任务假设。修正后保留原认证边界和任务归属，没有为了通过测试扩大数据权限。

最终检索性能：2000 条课程/实验 + 1000 条共享案例、20 次进程内目录搜索，P95 **42.8ms**（更早一次 33.1ms），低于 2 秒门槛。该值包含目录查询和投影，不是浏览器端到端或外部平台时延测量。

实际运行验证：新版 `/health` 200、未登录资源接口 401、3100 中心页面 HTTP 200；原 3000 页面和 8000 `/health` 均 200。独立运行库保留真实历史快照但未创建测试账号或填入合成资源；业务操作测试全部在 /tmp 合成库完成。

原始执行日志保存在 `.isolation/logs/phase-b-*.log`，未提交 Git；可追溯的非敏感结果和源码哈希见 `artifacts/enablement-phase-b/verification.json`。

## 原功能回归

| 原功能 | 实际覆盖与结果 |
| --- | --- |
| 伙伴匹配 | mock 推荐、证据与缺口、请求超时、失败/部分成功、重试和即时任务导航通过；没有真实模型验证。 |
| 任务列表 / 详情 | A/B 所有权、admin 全量、分页、归档/恢复、状态轮询、游标追加、机会未保存输入保留通过。 |
| 伙伴洞察 | 伙伴详情、画像读取、案例/交付物摘要、管理员保存/上传/画像失败提示通过。 |
| 场景广场 | 旧场景保留，新入口可达；多分辨率截图与浏览器错误检查通过。 |
| 管理后台 | 概览、伙伴、课程实验、案例共享、需求画像、机会、标签等权限和页面回归通过。 |
| 用户及模型配置 | 用户申请/审批、首次改密、账号状态、会话失效、管理员边界；模型场景绑定与失败反馈通过。 |
| 系统状态 | 状态刷新不改业务数据、模型未验证提示、关键页面布局通过。 |

## Playwright 截图清单

目录：`artifacts/enablement-phase-b/`。每项保存 1366×768、1920×1080 两个浏览器 viewport 的完整页面截图（因此图片全页高度可能超过 viewport）。只隐藏 Next 开发工具浮层，不隐藏业务区域。

| 页面 | 1366 证据 | 1920 证据 |
| --- | --- | --- |
| 发展中心首页 | center-1366.png | center-1920.png |
| 资源中心 | resources-1366.png | resources-1920.png |
| 课程详情 | course-1366.png | course-1920.png |
| 共享案例详情 | shared-case-1366.png | shared-case-1920.png |
| 伙伴详情新入口 | partner-1366.png | partner-1920.png |
| 匹配结果新入口 | match-1366.png | match-1920.png |
| 场景广场 | scenes-1366.png | scenes-1920.png |
| 全部任务入口对应的“我的任务”页及 task_type | tasks-1366.png | tasks-1920.png |
| 项目来源与风险待复核 | project-context-1366.png | project-context-1920.png |

共 18 张，文件 SHA-256、实际尺寸与源码哈希均记入 verification.json。自动检查页面无横向溢出、中心导航在 viewport 内且不越出侧栏，并人工查看了中心、资源、课程、共享案例、项目上下文、任务、场景截图；未发现关键遮挡或导航错位。截图仅包含合成数据。

## 未实现项、已知问题及 Phase C 条件

明确留给 Phase C：AI 能力判断、问题重新分类、发展方案生成、Plan/Run/Version、生成与编辑串行化、冲突控制、确认版本、伙伴可传递视图、对话调整、失败恢复与方案任务类型实际持久化。Phase B 诉求仅在当前页面内存中，不保存；刷新或离开页面后丢失，UI 已明确提示。

没有新增课程播放、实验执行、LMS、外部伙伴登录、向量库、队列、微服务、复杂 RBAC、第二套模型管理或案例主数据。

已知事项：

1. 原有 2 条孤儿案例仍待业务确认归属；共享前台拒绝无效归属，不擅自修复原数据。
2. 独立运行库当前没有正式发布的课程/实验或共享案例，资源中心真实空态正常；需管理员依据业务确认清单录入、授权、核验并发布。本轮没有伪造正式资源。
3. 真实模型、真实外部源站可达性、付费/账号可用性未验证。外部跳转浏览器测试由路由拦截响应，不访问真实外站。人工可用状态不承诺源站实时可用。
4. 两条既有 HTTP 422 弃用警告和 Next 开发态跨源提示不影响本轮测试或生产构建；没有顺带升级依赖或修改稳定配置。
5. 实际历史快照迁移测试依赖本地私有备份；完整复现实库对照需要保留 `.isolation/snapshots`，备份不进入 Git。
6. 页面对已打开内容采用聚焦 / 15 秒轮询重新校验，发起跳转另做即时后端校验；不是向客户端推送撤权。系统外人工复制内容的撤回不在本期能力内。

**具备进入 Phase C 的工程实现条件**：独立环境已保护；Phase A 授权/发布基础可被前台安全复用；来源标识及资源版本引用契约已落实；真实任务类型兼容、原功能回归与构建通过；Phase A 详细设计保留后续 Plan/Run/Version 与 confirmed_version_id 外发边界。

但尚不具备发展方案业务上线或真实模型验收条件。下一阶段需单独授权，并在业务验证前明确试点伙伴、能力方向、正式资源/缺口清单和固定验收样例。本轮已停止，没有进入 Phase C。

## 继续使用旧版与新版停止方式

旧版继续使用原 3000 前端 / 8000 后端，无需切分支、迁移或恢复数据库。本轮已执行独立 `bash enablement-dev.sh stop`，只停止登记且 cwd/start-time 匹配的新进程组；最终新版 PID 278229/278230 已退出。

如以后重新启动独立环境，再从 `/home/yuan/project/lingjian-agent-enablement` 使用 `bash enablement-dev.sh start|stop|status`。不要用宽泛进程终止命令，也不要在此分支运行原 `dev.sh stop`。上述是已完成操作的复现说明，没有把本轮 Git、启动或测试工作交给用户补做。
