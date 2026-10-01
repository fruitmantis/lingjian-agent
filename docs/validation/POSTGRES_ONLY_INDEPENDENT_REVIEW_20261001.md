# PostgreSQL-only 独立复核（2026-10-01）

> 后续已完成授权定点修复：原复现 13 项全部通过，完整 PG 后端 954 项、相关浏览器 36 项全部通过，见 [匹配迟到写入修复及新回归](MATCH_LATE_WRITES_20261001.md)。下文完整保留修复前独立审查结论与原始失败证据；原复现脚本及断言未改动。

**结论：存在 1 项阻断本地版本收口的缺陷：匹配任务旧执行的迟到完善结果可覆盖新重试的需求画像。** PostgreSQL-only 路径、初始化结构及本次核对的隔离/回滚要求通过；不能用原 941 项通过推导迟到保护已完整成立。未修改产品源码、原测试、运行配置，未 commit、push 或部署。

## 被审对象

- 正式目录 `/home/yuan/project/lingjian-agent-enablement`，`main`，HEAD `727e122a4f340e8ad8d1e5509e9d45af22a4fcef`；审查开始时工作区干净。报告记录的是提交前 `b63a903` 加未提交内容，HEAD 确已变化。
- 对最终 `workspace-manifest.json` 的 **416 项**逐文件计算 SHA-256（包括删除项），**全部一致，无新增受测源码差异**；对应被测指纹 `c5e404f8b974bdddeaae4b8d5d59c05e74dc2fd1a58839faf344a91a5a75050b`。因此可使用最终证据，而非仅按 commit 名称认定不同版本。[核对结果](evidence/pg-independent-20261001/review-state.json)
- 已读当前 AGENTS、两份 PG-only 报告、源码清单、原 72 项失败 JUnit/日志、最终 JUnit/日志、定向恢复/解释证据、进程阻塞修正、真实模型脚本与请求记录。原 72 项均映射到当前用例，含 6 个改名实例；逐项解释见 [失败修复核对表](evidence/pg-independent-20261001/original-72-review.json)。映射通过本身不作为业务正确性的证明。

## 已核实通过

| 范围 | 代码及原始证据、结论 |
|---|---|
| PG-only、初始化、测试隔离 | `config.py:41`、`postgres_storage.py:13,96,128`、`tests/postgres_support.py:13`、`support/model_test_boundary.py:12`：显式 PG/psycopg URL，无 SQLite 可执行连接、测试中转或静默回退；负向测试中 SQLite 仅被拦截。随机 schema 创建无 `IF NOT EXISTS`，只清理成功创建的对象，线程池退出后才清理。原 `test_enablement_migration.py:13` 在实际 DDL/DML 后执行 PG 除零，断言已到注入次数、事务无表/函数残留及重试成功；不是 mock 整个初始化器。 |
| 实际运行结构 | 独立 psycopg 连接确认运行端为 **127.0.0.1:5432 / banfei_agent / public / PostgreSQL 16.15**，事务强制只读。与当前初始化器在 `banfei_agent_test.validation_<UUID>` 创建的结构相比，**319 字段、110 约束、62 索引、35 表、3 触发器、1 函数完全一致**；字段类型/默认值/非空、主外键/唯一/检查约束、索引键/条件及有效性均已比较，不仅检查版本/数量。两边序列均为 **0**，无序列绑定差异，也未调用 nextval/setval。保留的 **8 个增量升级脚本全部可导入**，未发现已删除模块引用。[系统目录原始结果及脚本](evidence/pg-independent-20261001/catalog-result.json) |
| 解释与修改严格区分 | `development_engine.py:215` 的矛盾校验只会拒绝错误修改，**不证明解释能成功**。成功解释另由 `test_advisor_ux.py:14,79`、`test_v12_agent.py:90` 的 ready/answer/历史/current/Version 断言，以及归档真实模型脚本的单次解释请求证明。本轮再独立查询 PG，确认成功答复持久化且 Version 不变；错误 regenerate 单独断言失败且不改版本。有限样例不代表所有自然语言均能正确分类。 |
| 真实回滚、重试及版本指针 | `development_lifecycle.py:132,230,247,292`；本轮在 **current 指针 UPDATE** 上装 PG 触发器，实际诊断包含 `PL/pgSQL function audit_pointer_fault() ... at RAISE`，非前置校验失败。[故障原始诊断摘录](evidence/pg-independent-20261001/trigger-diagnostics.json) 与独立 PG 查询证明版本未半保存；retry 复用原输入，修改后新 Version 关联 retry Run，current 前进、旧 confirmed 保留，未改条目及原 answer 不变；重复成功执行无新调用/版本，旧失败 Run 的迟到保存返回 409。 |
| 权限、连接和模型等待 | 资源管理原测试实际逐请求验证 14 个 method/path 的 401/403；所有权仍后端校验。本轮发展/发展、匹配/匹配、发展/匹配三组双用户并发，观测 **608 次应用 SQL** 的实际 database/schema、后台线程及 PG PID。A 等待模型时 B 在 **0.082–0.114 秒**完成；独立 `pg_stat_activity` 显示相关连接 idle 且无事务，同 schema 写锁可取得，双向越权均 404，任务归属和结果不串。资料处理与 watchdog 另经静态追踪，均走同一连接入口；资料提取/转换不包在数据库事务内。本轮动态结论限上述任务路径。[独立 JUnit](evidence/pg-independent-20261001/independent.xml) |
| 原失败是否靠放宽断言转绿 | 未发现为通过而放宽本次重点业务契约。异步解释可新增 Run，但仍不新增 Version；运行中账号删除改为 409 符合先落库契约。匹配 26 项规范化单测改为直接测保留的验证边界，完整调用另由三阶段/严格 envelope 测试覆盖。性能仍 3000 条、30 次候选检索及原 p95 <2 秒门槛。**原 8 模式供应商用例的恢复实际调用新的 revise，不能单独证明 retry API**；retry API 由其他原用例及本轮独立复验覆盖。补充的 8 项保留原断言，逐模式记录 HTTP handler 确实收到故障请求，并独立查询 PG 核对 invalid_result/provider/timeout。[供应商注入证据](evidence/pg-independent-20261001/supplier-evidence.xml) |

## 确认缺陷

**P1：匹配旧执行在超时回收、重试完成后仍可写入派生产物。**

- 位置：[`backend/app/routers/match.py:759`](../../backend/app/routers/match.py#L759) 调用派生保存时未携带/核对执行 run_id；[`_save_derivative:902–908`](../../backend/app/routers/match.py#L902) 仅按 match_record_id 查找并 UPDATE。第 780 行只在最终状态更新时检查 expected_run_id，此时旧需求画像已经提交。
- 复现：在专用随机 schema 创建合成匹配任务，阻塞第一次 `_generate_demand_profile` 的写入入口；仅在该 schema 将任务时间改旧并调用真实回收函数；更新合成伙伴资料，让真实 retry 路径重新计算，独立 PG 读得 `gap_analysis=AUDIT_NEW`、任务 ready；释放旧线程，再独立读取变为 **AUDIT_OLD，任务仍 ready**。
- 实测结果：新重试成功结果被旧快照静默覆盖。此处实证为需求画像；机会/标签建议同样未传执行标识，但本轮不把未经复现的覆盖范围算作另一项故障。
- 最小修复建议：向派生写入传递本次 run_id；在**同一个持写锁的保存事务中**验证当前执行标识及任务状态，再写需求画像/机会/标签建议，失效执行不写。只在调用前或最终状态更新时检查不够。无需新增表、队列或框架。本轮未修复。
- 独立测试 [`test_independent_pg.py:188`](evidence/pg-independent-20261001/test_independent_pg.py#L188) 的最终断言失败；[JUnit](evidence/pg-independent-20261001/independent.xml) 和[日志](evidence/pg-independent-20261001/independent.txt)保留 `AUDIT_NEW → AUDIT_OLD`。这是受控延迟/超时模拟，不声称运行库已发生数据损坏。

## 尚未验证与边界

- **私有备份隔离恢复未执行。** 两个允许的验证库均已存在，当前角色 `rolcreatedb=false`、`rolsuper=false`；未获得可由现有保护路径直接使用的全新数据库目标。本轮未覆盖已有库、提升角色权限或改写私有 dump 的 schema。[只读安全条件](evidence/pg-independent-20261001/restore-safety.json)；因此不能声称备份可恢复。13 份保留备份均仍存在，未删除、外传、提交 Git 或送模型。
- 本轮没有重跑完整后端/浏览器、构建及真实模型。审阅了相同源码指纹下的既有有限真实请求证据；独立复验只用合成数据和本机桩，不代表 Windows、ARM、远端部署或全量业务效果验收。
- 独立验证合计 **12 passed / 1 failed**（首组 4/1，补充供应商 8/0）；失败作为确认缺陷保留。本轮对象按既有保护清理；显式观察的 schema 均消失，其余保留 schema 未发现本轮专属合成记录，未清理它们。[清理核对](evidence/pg-independent-20261001/cleanup-result.json)
- 结束时产品/原测试/配置的已跟踪差异为零；新增文件只在本报告及 `docs/validation/evidence/pg-independent-20261001/`。服务未启停，运行库只读，HEAD 未变。

复现入口（从正式工作目录执行；自动加载已有私有验证配置，输出到新建 `/tmp` 目录，当前应保留 1 项失败）：

```bash
.venv/bin/python docs/validation/evidence/pg-independent-20261001/run_checks.py
```

收口前需修复上述迟到写入并通过对应回归；本报告不替代业务上线许可。

## 证据归档说明

2026-10-01 提交收口仅整理重复/中间证据及文档引用；正文中的测试结果、源码指纹和当时 Git 状态均保留原口径。原被测清单和证据指纹不重写；已删除文件的原 SHA-256、用途及保留替代证据见[收口记录](GIT_CLOSEOUT_20261001.md)与[清理清单](evidence/cleanup-20261001.json)。
