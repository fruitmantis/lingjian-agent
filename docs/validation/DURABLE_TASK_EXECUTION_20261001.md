> 2026-10-01 数据库清理说明：本文中的混合数据库数字仅为历史实测记录，不代表当前 PG-only 验证。当前规则见 [PG-only 验证](POSTGRES_ONLY_20261001.md)，不再执行文中的旧文件数据库路径。

# 任务先落库、后台执行与渐进展示验证

日期：2026-10-01。工作区 `main`，基线 `b63a903`。本轮保留此前未提交的 HTTP 入口、伙伴匹配摘要及画像等改动，不切分支、不提交、不推送、不部署远端。

## 实现范围

- 伙伴匹配创建接口与能力发展创建、调整、重试接口：必要校验和 submission 幂等检查后，独立提交任务、运行标识及用户原始输入，再调度现有进程内后台执行器。没有模型前置调用，也没有失败后补建任务。匹配复用现有任务快照保存运行标识；发展复用既有 Run，不新增表。
- 首轮理解、范围判断及后续调用在后台运行。范围外正常结束并保留任务；尚无推荐或 Version 的任务仍可查询。后台调度停止也返回已提交的任务 ID，并将任务标记为可重试的中断。
- 阶段起止时间保存在现有任务/Run JSON 快照。匹配为理解需求、初选、推荐、项目分析；发展为方向分析、资源查找、建议生成。无额外模型调用、队列或新状态机。
- 匹配推荐先保存、立即可见，再完善项目分析；后续失败保留推荐。发展展示通过校验的分析，正式建议仍须成功保存 Version；调整失败不覆盖原 current/confirmed。
- 创建返回后进入 `/tasks/{id}`，复用侧栏任务列表并选中新任务。详情完整显示本次原始输入，以现有轮询更新进度和阶段结果；耗时由后端时间恢复，结束后停止计时。旧历史未记录阶段时间时不伪造耗时。
- 启动回收未结束任务，保留重试、所有权、幂等、并发与模型超时策略。继续使用现有管理员错误记录，不另建错误入口。

主要产品文件：`backend/app/routers/{match,development}.py`、`development_{engine,lifecycle,types,views}.py`、`match_understanding.py`、`task_failures.py`、`task_progress.py`、`database.py`、`main.py`；前端 `components/{task-progress,task-detail,development-assistant,task-navigation}.tsx`、`app/page.tsx`、`app/globals.css`、`lib/api-request.ts`。同步更新 AGENTS、README、相关后端与浏览器测试，以及隔离回放夹具。

## 实际验证

### 后端

相关测试最终去重 **251 项通过**，其中 **243 项使用专用 PostgreSQL 临时 schema**，**8 项为 SQLite 兼容测试**。这是各批次修复后最终结果的去重汇总，不是全仓库测试结果。没有对运行库执行测试写入。

覆盖 `test_durable_task_execution`、`test_task_creation`、`test_tasks`、`test_authorization`、`test_error_diagnostics`、`test_rc_presentation`、`test_development_lifecycle`、`test_development_engine`、`test_unified_flow`、`test_timeout_task_recovery`、`test_development_api`、`test_partner_match_stages`、`test_model_timeouts`、`test_model_timeout_settings`、`test_scope_gate`。

新增专项 19 项覆盖：

1. 首轮模型阻塞时，两类创建接口仍在 1 秒内返回，独立数据库连接可查任务与运行标识，原文完整且业务结果为空。
2. 超时、连接、认证、格式等六种首轮失败分别注入两类任务；任务保留，正确进入失败状态。
3. 分析结果可在 Version 之前查询；推荐保存后、项目分析尚未结束时即可查询，后续失败仍保留推荐。
4. 子进程服务在创建提交之后、后台尚未执行时终止；重新初始化后，任务仍存在并标记中断。
5. 执行器停止时，已落库任务仍返回 ID，避免变成未知提交结果。

既有核心测试同时覆盖重复/并发 submission、失败重试、所有权和引用权限、current/confirmed 保护、缓存失效、固定模型及超时重试。发展创建接口 20 次测试的 P95 为 **0.031828 秒**，仅代表本机隔离测试条件。

测试入口：私密加载 `BANFEI_TEST_DATABASE_URL` 指向本机 `banfei_agent_test` 后，使用 `.venv/bin/python -m pytest backend/tests/<上述文件>.py -q`。不要指向运行库。原始本机证据位于 `/tmp/banfei-task-pg-results.xml`、`/tmp/banfei-task-pg-followup.xml`、`/tmp/banfei-task-dispatch-final.xml`，按测试类和名称以最后一次结果去重。

### 前端

- `npm --prefix frontend run typecheck`：通过。
- `npm --prefix frontend run build`：通过（Next.js 15.5.19，31 个静态页面生成成功）。构建期间已停止开发服务，未并发写同一 `.next`。
- WSL Chromium 相关 Playwright 最终去重 **20 项通过**：`model-timeout-transport.spec.ts` 5 项、`task-navigation.spec.ts` 10 项、`task-progress.spec.ts` 2 项、`unified-entry.spec.ts` 3 项。
- 浏览器测试覆盖创建后自动打开/选中、完整原文、分析与正式结果的先后展示、刷新恢复、结束后耗时停止、模式切换、任务导航、长响应/流式响应/取消，以及异步创建不先请求模型等待策略。
- 检查 1366×768、1920×1080、390×768；截图保存在 `/tmp/banfei-task-progress-evidence/`。截图使用合成资料，不含真实 Key。
- 模型相关端到端流程使用显式 `PLAYWRIGHT_MODEL_MODE=replay`，其余使用 UI/故障注入夹具。更新旧断言以适应异步返回及现有折叠详情/移动导航，不以完整画像暴露给普通用户来满足旧测试。

浏览器各批次结果保留于 `/tmp/banfei-async-browser.txt`、`/tmp/banfei-task-ui-replay2.txt`、`/tmp/banfei-task-ui-complete.txt`、`/tmp/banfei-unified-final.txt`；前期失败及修复后的结果均保留，不将单个有失败的批次称为全绿。

### 本机服务恢复

验证后通过 `bash enablement-dev.sh start` 恢复，`status` 确认后端、前端及 Caddy 均运行。实际 IP 的 `http://172.21.208.223/login` 与 `/api/health` 均返回 200，未跳转；仅 80 对外监听，3000/8000 仅监听 127.0.0.1，无 443 监听。只作只读健康核验，没有在运行库创建测试任务。

## 数据与未验证边界

- 无数据库 schema 变更、重建、seed 或业务数据迁移；沿用原任务、快照、Run、Version 和归属。
- 本轮模型调用顺序与故障恢复由隔离回放和故障注入验证，未调用真实付费供应商，因此不代表真实模型输出质量或供应商响应时间已验收。
- Windows Edge、ARM/内网部署未在本轮实测。没有引入持久化队列：进程被终止后由现有启动回收标记中断，用户从原任务重试，不宣称自动续跑。
