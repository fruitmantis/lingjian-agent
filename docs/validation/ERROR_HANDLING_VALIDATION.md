# 错误处理最小优化验证

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
