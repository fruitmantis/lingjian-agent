# 灵鉴 Agent 发布前自动化加固与验收报告

## 1. Release Decision

**GO**

23 项 Release Gate 全部通过；安全、A/B 隔离、迁移、任务故障恢复、并发重试、文件安全、生产构建、服务启动、浏览器核心 E2E 和一次受控真实模型 E2E 均有实际执行证据。两条历史 `cases → partners` 外键孤儿仍存在，但在本轮开始前已存在，migration 未新增任何 FK violation，且不涉及任务所有权链路。

## 2. 验证信息

| 项目 | 结果 |
|---|---|
| 验证日期 | 2026-09-04（Asia/Shanghai） |
| 项目路径 | `/home/yuan/project/lingjian-agent` |
| Branch | `main` |
| 验证起始基线 | `637b0379abcaa0cf9024c597dd774480927ce8d7` |
| Git push | 未执行 |
| 环境 | WSL2 Ubuntu-24.04，Linux 6.18.33.2-microsoft-standard-WSL2 |
| Python | 3.12.3 |
| Node / npm | 18.19.1 / 9.2.0 |
| Backend | FastAPI + SQLite |
| Frontend | Next.js 15.5.19 + React 19 |

仓库规则要求单人开发始终在 `main`，因此未创建附件中建议的安全分支。开始时工作区已有大量需保留的未提交成果；本地 checkpoint commit 因 `.git` 写权限/安全审批限制未能创建，已改用以下恢复材料：

- `/tmp/lingjian-before-release-validation.patch`：binary diff
- `/tmp/lingjian-before-release-validation-untracked.txt`：未跟踪文件清单
- `/tmp/lingjian-before-release-validation-source.tgz`：源码归档

三份恢复材料均未包含被 Git 忽略的 `.env`。未执行 reset、clean、checkout、revert 或 push。

## 3. 真实数据库基线与终检

所有破坏性、并发、账号、迁移、crash 和模型业务测试均使用 `/tmp` 或 pytest 临时数据库；真实 `data/app.db` 只读查询。

| 表/检查 | 初始基线 | 最终只读检查 |
|---|---:|---:|
| schema version | 9 | 9 |
| users | 1 | 1 |
| user applications | 0 | 0 |
| audit logs | 9 | 11 |
| match records | 48 | 48 |
| demand profiles | 45 | 45 |
| opportunities | 28 | 28 |
| tag suggestions | 32 | 32 |
| partners | 33 | 33 |
| cases | 3 | 3 |
| partner documents | 3 | 3 |
| deliverables | 0 | 0 |
| task owner 非空 | 48/48 | 48/48 |
| integrity_check | ok | ok |

最终 `foreign_key_check` 仍只有两条已知历史问题：`cases` rowid 3、4 指向缺失的 `partners`；任务相关表 FK 为 0，migration replay 未产生新增 violation。

真实库 audit logs 在 20:19～20:20 出现两条已有账号的正常 `auth.login_success`，当时 8000 端口已有一个非本轮启动的服务在运行。本轮自动化 API、浏览器与真实模型数据均明确指向 `/tmp` 测试库；真实库业务表数量未变化。该两条日志保留且未清理。

## 4. 修改内容

### P0 安全

- 新增统一运行配置加载，确保 `.env` 在认证模块读取前加载，且进程环境优先。
- 删除 JWT 固定 fallback；缺失、短于 32 位或使用历史默认值时明确拒绝启动。
- Token 加入 `token_version`，每次受保护请求回查用户状态、角色与版本；改密、重置、停用、角色变化后旧 Token 立即失效。
- HTTP Bearer 缺失时统一返回 401；业务路由与管理路由分别使用 active-user/admin 依赖。
- 空库不再创建 `admin/admin123`；bootstrap 只读取环境变量、强制强密码并设置首次改密。
- 禁止管理员停用/降级自己，禁止系统失去最后一个有效管理员。

### P1 可靠性与滥用保护

- 新增可配置数据库、上传与 Chroma 路径；默认仍为现有 `data/` 位置，测试可完全隔离。
- `matching/enriching` 超时任务在启动、列表、详情或 retry 时恢复为 `failed + interrupted`。
- retry 原子抢占；failed 或无有效推荐时重新 matching，有有效 partial 推荐时仅补 enrichment。
- 修复推荐持久化异常形成“partial + empty recommendations”后无法重新匹配的问题。
- 账号申请增加单进程按 client IP 滑动窗口限流、pending 总量保护、用户名/联系方式去重及 `BEGIN IMMEDIATE` 并发审批保护。
- 账号申请审批后的用户必须首次改密，申请密码 hash 在批准/驳回后清除。
- 上传改为 1 MiB 分块流式写入，默认 20 MiB 上限；超限返回 413 并清理部分文件。
- PDF/OOXML 做内容与扩展名检查；数据库删除先成功再删磁盘，避免 DB 删除失败后文件已丢失。
- PPTX 预览文本 HTML escape，并添加限制性 CSP；同时修复 `html` 模块被局部变量遮蔽的实际错误。
- 前端 API 增加 30 秒超时；列表、详情、工作台和主要后台页在 5xx/断网/超时后结束 loading、显示错误并提供重试入口。
- 模型配置页新增非 2xx 检查，避免错误 JSON 被当成数组后造成空白页。
- 文档更新：删除默认凭据说明，补充 JWT/bootstrap、验证命令和测试隔离规则。

### 测试与验证资产

- 新增 pytest 配置、测试 fixture、合成身份/任务数据、fake OpenAI-compatible LLM、进程故障注入和迁移回放。
- 新增 Playwright 配置和浏览器 E2E；测试服务固定使用 18000/18080/3100 与 `/tmp/lingjian-agent-e2e`。
- 生成 32 张截图到 `artifacts/validation/screenshots/`。

## 5. 自动化测试总览

| 测试集合 | 数量 | PASS | FAIL | SKIP | BLOCKED |
|---|---:|---:|---:|---:|---:|
| pytest | 50 | 50 | 0 | 0 | 0 |
| Playwright E2E（含 4 个视觉分辨率用例） | 12 | 12 | 0 | 0 | 0 |
| 合计 | **62** | **62** | **0** | **0** | **0** |

pytest 因 Codex 单次外部命令回传窗口限制分组执行，最终结果为：23 passed、15 passed、10 passed、2 passed，共 50/50。最后 2 项为真实进程级 crash recovery，而非仅单元 mock。

测试过程曾发现并修复四类问题后回归：机会完整度 nullable 序列化、PPTX 预览模块名遮蔽、测试环境 CORS、Playwright 严格定位器/路由拦截范围。没有删除有效断言或把错误行为改成测试预期。

## 6. 认证、申请与 A/B 权限矩阵

- AUTH-001～021：全部 PASS。
- APPLICATION-001～007 + pending capacity：全部 PASS。
- 两管理员并发批准同一申请：结果恰为一个 200、一个 409，只创建一个用户。
- 普通用户遍历 OpenAPI 中全部 `/admin/*` operation：全部 403。

| 能力 | user A 自己 | user A 访问 B | admin |
|---|---|---|---|
| active/archived list | 仅 A 数据 | B 不出现 | A/B 均可见 |
| detail | 200 | 404 | 200 |
| demand/profile/opportunity 关联 | 仅 A | 404 | 可见 |
| archive / restore | 成功 | 404 | 可操作 |
| failed / partial retry | 成功 | 404 | 可操作 |
| opportunity edit | 成功 | 404 | 可操作 |
| `/admin/*` | 403 | 403 | 按接口成功 |

结论：UI 隐藏不是安全边界，后端 owner/admin 判定已实际覆盖读写链路。

## 7. OpenAPI 权限扫描

- 实际生成：60 paths / 71 operations。
- 无 security 的公开操作严格等于 3 个：
  - `GET /health`
  - `POST /auth/login`
  - `POST /auth/user-applications`
- 所有 `/admin/*` operation 均声明 Bearer security，且普通用户动态调用扫描全部返回 403。

结果：PASS。

## 8. v8 → v9 Migration Replay

对 `data/app.db.bak-before-task-hardening-v9-20260904` 的临时副本实际执行两次初始化：

- v8 → v9 成功；48 条 match records 保持不变且 owner 全非空。
- users、applications、audit、match、demand、opportunity、suggestion、partner、case、document、deliverable 数量前后完全一致。
- 第二次启动结果与第一次 byte-level 数据快照语义一致，无重复迁移、重复插入或 schema 错误。
- integrity_check=ok。
- 两条已知 case orphan 前后完全一致；任务相关 FK 无异常。

结果：PASS，新增 FK violation=0。

## 9. 任务状态机、并发与 Crash Recovery

- TASK-001～007：全部 PASS。
- stale matching/enriching 恢复：PASS。
- empty partial recommendations 强制 rematch：PASS。
- recommendation persist 注入异常后 retry 重新 matching：PASS。
- 10 路并发 retry：仅一个取得执行权，其余返回冲突；无重复衍生记录。
- archive/retry 并发：最终状态一致。

真实进程故障注入：

| 场景 | 注入动作 | 重启结果 | Retry |
|---|---|---|---|
| matching | slow fake LLM 时 kill 测试专属 backend PID | failed / interrupted | ready |
| enriching | match 完成、enrichment 阻塞时 kill 测试专属 backend PID | failed / interrupted | ready |

结果：2/2 PASS；未终止任何非测试进程。

## 10. 文件接口

| 用例 | 结果 |
|---|---|
| 正常 DOCX 上传与解析 | PASS |
| 等于上限成功、超过 1 byte 返回 413 | PASS |
| 伪造 PPTX 拒绝且无残留文件/记录 | PASS |
| 磁盘文件缺失时下载/预览 404、删除收敛 | PASS |
| 注入 DB 删除失败时磁盘文件保留 | PASS |
| PPTX `<script>` / `<img onerror>` escape + CSP | PASS |

结果：6/6 PASS。

## 11. 前端、浏览器与视觉

核心浏览器流程全部实际执行：登录；账号申请—审批—首次登录—强制改密；A/B 自己任务；A 直输 B task URL；普通用户 `/admin`；管理员 A/B 全量任务与用户管理；停用/改密后的 session 失效；failed retry；ready retry 409。

异常态覆盖：401、403、404、409、500、502、network error、timeout/backend unavailable。工作台、我的任务、任务详情、后台概览、用户管理、伙伴管理、项目机会和模型配置均验证错误可见、loading 结束；交互页保留重试入口；Playwright `pageerror` 为 0。场景广场为静态配置页，不依赖后端请求。

视觉验证：

- 8 页面 × 4 分辨率 = 32 张 PNG。
- 四组页面级 `scrollWidth <= innerWidth + 1` 断言通过。
- 抽检 1024 登录、场景、用户管理及 1920/1440/1366/1024 任务详情：无侧栏错位、卡片遮挡、页面级横向 overflow、明显文本截断或旧配色混入。
- 管理后台与用户前台均保持浅灰背景、白卡片、蓝色强调、圆角、轻阴影的统一风格。

截图目录：`artifacts/validation/screenshots/`。

## 12. 工程检查与服务启动

| 检查 | 结果 |
|---|---|
| `git diff --check` | PASS |
| Python `compileall` | PASS |
| pytest | 50/50 PASS |
| `tsc --noEmit` | PASS |
| Next.js production build | PASS，20/20 页面生成 |
| FastAPI startup（真实库临时副本） | PASS |
| `GET /health` | 200，`status=ok` |
| OpenAPI generation | PASS，60 paths / 71 operations |
| Next.js production start | PASS，`GET /login`=200 |
| SQLite integrity/FK | integrity ok；仅 2 条 existing case orphan |

项目没有独立 `npm run lint` 脚本；直接调用会返回 Missing script。Next.js production build 自带的 lint/type validity 阶段通过，且 `tsc --noEmit` 独立通过。本轮未为此额外引入 ESLint 配置。

## 13. 真实模型最终 E2E

在所有 mock/自动化测试通过后，使用当前已有模型配置执行 **1 次**真实业务验收；未输出或修改 API Key、模型地址、模型名、默认模型或场景绑定。数据库为 `data/app.db` 的 `/tmp` 副本，账号均为副本内合成身份。

- 输入：“帮我找适合制造行业知识库 Agent 项目的伙伴”
- HTTP 200；task status=`ready`
- task owner=合成 user A：正确
- recommendations=5
- 关联 demand profile=1
- 关联 project opportunity=1
- 关联 tag suggestions=2
- 合成 user B 读取该任务：404
- 合成 admin 读取该任务：200

结果：PASS，无重复真实业务调用。

## 14. Known Issues 与 Remaining Risks

1. **历史 FK 数据**：`cases` rowid 3/4 为既有孤儿。本轮未删除或修复真实业务数据；建议后续确认案例归属后单独治理。
2. **账号申请限流是单进程级**：进程重启会清空计数，多实例之间不共享；符合当前单实例 MVP。若未来多实例部署，应迁移到网关或共享存储限流。
3. **client IP 取自直连连接**：当前未信任 `X-Forwarded-For`，避免伪造；反向代理部署后需在可信代理边界统一传递真实 IP。
4. **测试运行器版本约束**：当前 Node 18 使用可运行的 Playwright 1.49.1；未来升级 Node 后可同步升级 Playwright。
5. **现有 8000 监听服务**：发布验收发现 8000 已被现有 Uvicorn 占用，未终止未知/非本轮进程；本轮启动验证改用 18001。
6. **CI 未配置**：测试现已可重复运行，但仓库尚无 CI workflow；不属于本次 MVP 发布阻断项。

## 15. 清理与最终状态

- 本轮启动的 fake LLM、临时 backend、frontend dev/prod、Playwright 和 crash-injection 进程均已停止。
- `/tmp/lingjian-agent-e2e`、真实模型临时库副本、pytest 临时目录、Playwright trace/report 和临时 HTML 已删除。
- 正常保留 pytest/Playwright 测试源码、fixture、验证文档和 32 张截图。
- `.env` 中生成的 JWT secret 为本机忽略文件，未显示、未纳入 Git；仓库扫描未发现被跟踪/未跟踪源码中出现真实 API Key 或私钥。
- 当前分支为 `main`；本报告所述成果作为一次本地提交保存，不执行 push。
