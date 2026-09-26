> **阶段验证记录。** 本文的提交状态、HEAD 和测试数字属于当时基线；当前状态见 [2026-09-26 收口记录](GIT_CLOSEOUT_20260926.md)，现行规则见 [README](../../README.md)。

# 错误处理最小优化验证

## 2026-09-26 能力发展最小复用补充

- 复用 `task_failures` 分类、`FailureNotice` 组件和原诊断日志。生成、调整、回答使用对应动作文案；服务异常不提供重试。失败 Run 仅在没有活动执行时提供原重试入口，失败不改变 current。
- 已读取保存的 Plan/Run 才说明“发展诉求已保留”；“当前建议仍可使用”依据后端 `presentation.current_available`。提交未确认、尚未保存的追问不声称诉求已保留；历史调整回复也不笼统声称旧建议可用。
- 丢失创建响应时，通过新增的只读 `GET /development/submissions/{submission_id}` 查询本人原提交；任务详情使用 Run 的 `submission_id` 或已保存回答核对原执行。浏览器会话保留待核对标识，刷新不重复 POST；查不到原提交时继续保持未确认，不把 404 当成失败或自动补发。
- 补记后台编辑校验、外发校验、空回答的真实异常；提交关联 Run/请求编号，回答保存故障记录保存环节。继续使用已有管理员展开、复制及敏感信息遮蔽，成功重试不清历史。
- 修复资源标签契约冲突：新生成条目不让模型给资源分配正式标签，生成结构禁止该字段；资源按 ID/版本引用，仍校验候选、权限、URL、枚举和正式分析标签。历史/人工编辑的显式标签继续验证是否属于资源，冲突记录资源、提交标签和允许标签；无标签资源可正常推荐。不更改正式标签字典或历史版本，不迁移 schema。
- 验证：选定后端 **51 项全部使用 PostgreSQL 临时 schema 并通过**；`task-failure.spec.ts` **13 项通过**，最终读取提示调整后相关 2 项复验通过；TypeScript 无增量类型检查与 `git diff --check` 通过。后端报告 `/tmp/banfei-development-errors.xml`；浏览器使用 `/tmp/banfei-development-errors-playwright.cjs` 连接现有前端并拦截全部 API，不另启服务或共写 `.next`。
- 本轮未调用真实模型、未重试正式失败任务；正式库没有测试写入。更改保留于 main，未 commit / push / deploy。下方为 9 月 25 日历史记录与当时复验方式。

日期：2026-09-25。范围：当前 main 工作区未提交改动；不是上线或业务验收结论。

## 实现范围

- 普通提示：一般失败使用“本次处理失败，请重试。”；明确配置、认证、连接、供应商及存储异常使用“服务异常，请联系管理员。”；请求结果未确认使用“暂未确认结果，请刷新查看。”。必填项、登录过期及可操作业务限制继续具体提示。
- 合法空推荐列表视为无匹配项；非空列表全部未通过候选、评分或理由校验仍算失败，诊断记录具体字段原因。能力发展失败和临时刷新失败保留已有可用建议；权限拒绝仍清除受保护展示。
- 后端在转换前记录真实异常，复用服务器日志，并向 Git 忽略的 `.isolation/logs/errors.jsonl` 追加 JSON 行。无需数据库 schema 变更。时间、task_id/request_id、环节、异常类型和原因、堆栈均保留；模型名称、HTTP 状态及必要响应片段在可取得时记录。
- 堆栈包含文件、行号、函数调用链，不包含局部变量和源码行；不记录请求正文/Prompt或 SQL 绑定参数。配置密钥、模型凭据、Token、身份 Key、Cookie、连接凭据脱敏后才截取字段长度。响应片段最多 2,000 字符，异常消息最多 6,000 字符，堆栈最多 24,000 字符，截取有标记。
- 数据库故障不阻止文件诊断；诊断文件写入失败时保留服务器日志。处理失败后保存失败状态再发生数据库错误，两条真实异常分别保留。重试成功只更新任务当前状态，不删除追加日志。
- 后台“系统状态 → 最近错误”通过受 require_admin 保护的 GET /admin/system/errors 读取，返回 Cache-Control: no-store。默认倒序显示最近 50 条，可展开和复制完整的脱敏记录。读取最近 8 MiB 日志范围；文件本身不自动清理。
- 历史粗分类不补造真实原因，本功能从启用后记录新发生的错误。没有新增错误中心、告警、工单、模型分析或数据库表。

## 实际验证

- `frontend npm run typecheck`：通过。
- `frontend npm run build`：通过。运行服务先停止，避免与开发服务同时写 `.next`；浏览器验证结束后使用原私有配置恢复。
- 后端相关回归：224 项通过，其中 192 项 PostgreSQL、32 项既有 SQLite 兼容路径；另补充双重故障用例 1 项 PostgreSQL 通过。合计 225 项通过。
- PostgreSQL 均由私有 BANFEI_TEST_DATABASE_URL 指向本机 banfei_agent_test 并使用临时 schema；SQLite、上传夹具和诊断日志仅在 /tmp。无运行库测试 seed 或故障注入。
- 后端覆盖真实校验原因、模型 HTTP 状态/响应片段、密钥与 Cookie 脱敏、SQL 参数与校验输入隔离、程序堆栈、日志写入兜底、请求关联、管理员权限、重试历史保留、空匹配、旧建议保留、超时/中断、普通身份及管理员认证。
- Playwright `task-failure.spec.ts`：8 项通过，包含普通提示、空匹配、提交未确认、保留已有建议，以及后台展开、复制和桌面/窄屏布局。
- 相关故障回归：`batch2-resilience.spec.ts` 与 `release-validation.spec.ts` 中选定 7 项通过，覆盖请求时限、取消、字段校验、提交超时、归档/重试断网、E2E-007、E2E-009。
- 实际错误页和相关浏览器回归合计 15 项通过。后端故障由隔离注入验证；未调用真实模型。
- 浏览器演示使用合成数据；实际管理员人工验收仍由用户执行。

## 本地复验入口

通过已有私有验证配置给子进程提供 BANFEI_TEST_DATABASE_URL，不打印连接串或凭据：

```bash
.venv/bin/python scripts/run_postgres_validation.py backend -q -k 'error_diagnostics or task_failures or recommendations or development_engine or model_config or authorization or phase_d_reliability or development_lifecycle or system_status or openapi or local_identity or test_auth'
.venv/bin/python scripts/run_postgres_validation.py browser task-failure.spec.ts
PLAYWRIGHT_MODEL_MODE=replay .venv/bin/python scripts/run_postgres_validation.py browser release-validation.spec.ts batch2-resilience.spec.ts --grep 'E2E-007|E2E-009|request budgets|request wrapper|validation response|submission timeout|task archive'
```

浏览器测试必须先确认并停止本项目的 3000/8000 服务，结束后通过 `bash enablement-dev.sh start` 恢复原运行环境。未 commit、push 或 deploy。
