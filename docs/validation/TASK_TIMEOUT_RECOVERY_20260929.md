# 模型超时与任务恢复验证

日期：2026-09-29。工作区 `/home/yuan/project/lingjian-agent-enablement`，分支 `main`，基线 `b894d19b35d4900aa791db2914f3a1475147945a`。本次修改未提交，保留此前未提交的 UI 和模型设置改动。

## 问题与修复

首次匹配和发展任务原先在任务持久化前调用统一理解；该阶段模型超时会抛出 502，前端可能把它当作数据库提交结果不明而保留待提交标记。已有发展任务的待提交标记和失败 Run 残留的执行锁也可能阻止重试。

- 已知模型超时在首次理解、调整或重试阶段按执行失败处理。匹配任务保存原 requestId 对应的 failed 记录；发展任务在同一事务中保存原 submission 对应的 Task/Run，Run 为 failed，错误分类为 timeout，释放执行锁，不创建 Version。
- 匹配重试先取得执行锁，再进行模型理解；准备阶段再次超时也会保存失败原因，原推荐结果保持不变。发展重试复用原 Plan/request，失败不改变 current 指针。
- 读取或重试发展任务时，按现有所有权检查恢复指向已终止 Run 的执行锁。前端恢复已有失败任务时清除旧待提交标记；正在发送的请求不会因读到旧失败 Run 而提前解锁。
- 已知执行异常与真正提交不明分开处理。新增错误响应字段 `failureCode` 只包含既有错误分类；准备阶段没有提交任务的错误标记 `submissionAccepted: false`。超时策略预检失败同样不冒充已发送业务请求。
- 网络断开或数据库提交结果不明仍保留原提交标识，通过读取原任务/提交查询恢复，不自动重复发送业务 POST。普通界面不再展示“提交未确认 / 核对任务”，失败任务可从原任务重试。
- 未增加表、状态枚举、队列或重试框架；没有改动模型 Prompt、供应商、权限与成功结果的生成规则。

## 数据边界

先只读核查了本地 Task、Run、结果及错误记录，没有找到用户描述的两条新异常。用户随后确认异常在企业内网试运行环境，WSL 和云端 ARM 均无此问题。

本轮未连接企业内网，没有直接修改、删除或合并这两条记录，不能确认它们是否重复。本地运行库未执行数据修补或测试写操作，没有重建数据库。新代码提供现有失败任务的正常详情/重试恢复路径；内网原记录是否符合该路径，需要该环境实际数据确认。未部署任何服务器。

## 实际验证

1. 专用 PostgreSQL 验证库临时 schema：**81 passed**，选择 `timeout_task_recovery or test_unified_flow or test_model_timeouts or test_scope_gate`。包含原生/HTTPX 超时、超时重试耗尽、原输入重用、首次失败持久化、提交幂等及并发、原任务重试、旧结果保护、执行锁恢复、越权不可触发修复、范围外不建任务、真实提交异常区分。全部使用合成模型响应/故障，不调用供应商。
2. WSL Chromium 界面与请求传输回归：最终 **48/48 passed**，`task-failure.spec.ts` 和 `model-timeout-transport.spec.ts`，桌面 1366×768、窄屏 390×844；部分结果保护用例另检查 1920×1080。覆盖创建后超时跳转、失败页重试、刷新恢复、丢失响应只查询原请求、旧正文保留、管理员脱敏错误显示、预检失败及代理传输。
3. 首次浏览器执行 44/46 通过；2 个窄屏用例遗漏展开导航，补上实际操作后通过。新增首次发展任务用例的 URL 参数由测试误写的 `partner` 改为实际 `partner_id` 后，两尺寸均通过。合计 48 个唯一用例全部通过，不把中间失败报告称为单轮全绿。
4. `npm run typecheck`：通过。`BANFEI_BUILD_CPUS=2 npm run build`：通过。构建前确认运行中匹配任务和发展 Run 均为 0，按项目脚本停止服务，构建结束后恢复；没有并行写同一个 `.next`。
5. 扩展生命周期/引擎/API 回归另得 **114 passed / 16 failed**。针对全部 16 个失败，在独立测试进程内用 `git show HEAD:backend/app/development_lifecycle.py` 加载修改前的生命周期函数对照，同样 16 项失败。8 项生命周期测试缺少准备阶段模型桩，7 项恶意输入测试仍假设准备阶段失败后已有 Run，1 项自然语言修改测试存在旧流程预期。此对照仅替换测试进程内生命周期函数，不是完整 HEAD 检出；没有切分支、覆盖工作文件或恢复旧设计。本轮未为这些旧预期放宽产品校验。

本轮未测试 Windows Edge、企业内网或 ARM，不把 WSL 自动化通过当作这些环境已验收。

本机证据：`/tmp/banfei-recovery-backend.xml`、`/tmp/banfei-recovery-extended.xml`、`/tmp/banfei-recovery-baseline.xml`、`/tmp/banfei-recovery-ui/combined-summary.json`、`/tmp/banfei-recovery-typecheck.log`、`/tmp/banfei-recovery-build.log`。测试诊断仅写临时目录。
