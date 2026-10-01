# 匹配旧执行迟到写入定点修复（2026-10-01）

**结论：原独立复核 P1 已修复，三类派生写入均受保护；本轮未发现剩余阻断问题。** 最终完整 PG 后端 954 项、原独立复核 13 项、相关浏览器 36 项全部通过。

对象：正式 `main` 工作区，HEAD `727e122a4f340e8ad8d1e5509e9d45af22a4fcef` 加本轮未提交改动。开始时已跟踪文件无差异，仅有上轮独立审查报告和证据；均保留。没有 commit、push、部署或分支操作。

## 原失败与根因

用户指定的原入口 `docs/validation/evidence/pg-independent-20261001/run_checks.py` 修复前实跑 **12 passed / 1 failed**。原断言直接观察到需求画像 `AUDIT_NEW → AUDIT_OLD`，任务仍 ready。[修复前 JUnit](evidence/pg-late-writes-20261001/before-results.xml)、[日志](evidence/pg-late-writes-20261001/before-results.txt)、[原脚本及证据指纹](evidence/pg-late-writes-20261001/before-state.json)。未更改原审查脚本或失败断言。

原完善阶段只在最终更新任务状态时核对 run_id；需求画像/机会按 match_record_id 覆盖、标签建议独立写入，均可先提交迟到结果。另有两个相同执行身份缺口：入队 worker 启动时读取最新 run_id，以及 retry 的状态认领与新 run_id 分开提交。

## 定点修改

产品源码仅修改 `backend/app/routers/match.py`：

- 创建和 retry 生成的原 run_id 显式传入后台执行；启动时必须仍为该执行且处于 matching，不能借用最新 run_id。
- 完善阶段将原 run_id 传给需求画像、项目机会和标签建议。需求画像/机会由 `_save_derivative` 在同一事务内先获取既有 schema PG 写锁，核对 run_id 与 enriching 状态，再执行查重和 INSERT/UPDATE。标签建议在同一短事务中完成同样校验及本批建议保存。
- 失去执行权抛出本匹配模块内部的 `_MatchExecutionLost`，派生函数不把它吞成普通失败并继续保存。通用错误路径固定使用启动参数中的原 run_id，迟到模型错误不能覆盖新执行的状态、进度或错误。
- `_claim_task_retry` 将状态和新 progress/run_id 一次提交；原 `recover_stale_tasks` 的 UPDATE 已由 `Connection.execute` 获取同一事务写锁，回收状态与 progress 也在该事务内保存，无需改动存储层。
- 复查初选快照、推荐、阶段进度与最终状态：已有相同锁边界的 run_id/状态检查继续保留。模型调用不放入持锁事务。显式维护提取函数的既有无执行参数调用保持兼容；任务执行链始终传入已核验的原 run_id。

无接口字段、数据库结构、迁移、登录、入口或推荐算法变化。原两个直接调用内部函数的测试仅补齐真实运行所需的 progress/run_id 夹具；另一个机会回滚测试的连接代理补充转发 `lock_writer`，并新增实际 INSERT 到达断言。原业务断言全部保留。

## 常规回归及独立证据

新增 `backend/tests/test_match_late_writes.py` 共 **13 项**：

| 覆盖 | 方法与最终断言 |
|---|---|
| 三类保存 × 重试完成/仅回收/迟到报错，9 项 | Event 阻塞在实际保存函数调用执行权检查之前；确认无事务、未持锁。独立 PG 将该任务时间改旧，调用真实回收；需要重试时更新合成资料/标签字典，通过真实 retry 重新生成理解和结果。释放旧执行后直接 psycopg 查询完整任务行、progress/快照、需求画像、机会、所有标签及计数；与释放前逐值相同，旧线程实际 INSERT/UPDATE/DELETE 为 0。 |
| 当前正常执行、submission 重放和已结束执行重复调用 | 三类成果各 1 条，标签 occurrence_count=1，重放无新模型调用或数据变更，已结束执行被拒绝。 |
| 入队旧 worker 尚未开始就被回收/重试 | 队列参数携带原 run_id；执行旧队列项后没有新模型调用或数据变更。 |
| 旧模型迟到报错 | 旧详评被阻塞、回收及 retry 成功后，释放时抛出真实异常，通用错误处理不能改变新成果及任何任务/进度/错误字段。 |
| retry 执行权原子切换 | PG 触发器在保存新快照时实际抛错，断言此前 UPDATE 的任务状态和旧 progress 一起回滚。 |

连接证据包含实际 `current_database()`、`current_schema()`、PG PID 和 run_id；每次模型响应前用独立连接验证写锁可取得。保存点和最终状态证据在 [新增回归 JUnit](evidence/pg-late-writes-20261001/final-targeted.xml) 的 properties 中。事件等待只有有界失败超时，不用任意 sleep 控制竞态。

历史调试批次也保留：首批新增合成标签 evidenceText 不在需求原文中，被既有严格校验拒绝（11 failed / 90 passed，89 项既有测试全部通过）；修正证据文本后，又发现只更新伙伴资料会合法复用理解事实，未生成不同的机会/标签（1 failed）。最终夹具同时更新专用 schema 的合成标签字典，真实理解缓存失效，保留 NEW 断言，并追加 NEW 理解/答复实际调用断言。未放宽产品校验。[首批](evidence/pg-late-writes-20261001/fixture-source-failure-results.xml)、[缓存夹具批次](evidence/pg-late-writes-20261001/fixture-cache-failure-results.xml)。

## 最终批次

完整后端首批在 **678 passed / 1 failed** 时主动中止，原因是原机会回滚测试代理缺少 `lock_writer`，错误提前发生在 INSERT 之前。补齐代理并增强注入点断言后，相关机会用例和新增回归 **37 passed**；随后重新冻结输入、重新运行完整后端。此中止批次不计作完整通过。[中止批次 JUnit](evidence/pg-late-writes-20261001/interrupted-backend.xml)、[当时指纹](evidence/pg-late-writes-20261001/workspace-before-proxy-adaptation.json)、[适配后 37 项](evidence/pg-late-writes-20261001/proxy-adapted-targeted.xml)。

最终完整后端 PG：**954 passed / 0 failed / 0 errors / 0 skipped**，860.84 秒，包含原 941 项及新增 13 项。两条既有依赖弃用 warning（PyPDF2、Starlette 422 常量）。[完整 JUnit](evidence/pg-late-writes-20261001/final-backend.xml)、[完整日志](evidence/pg-late-writes-20261001/final-backend.txt)。这次是重新完整运行的结果，不是累计中间批次。

| 最终补充范围 | 实际结果与证据 |
|---|---|
| 原独立复核脚本（完整后端之后重新执行） | **13 passed / 0 failed / 0 skipped**，25.06 秒；原失败断言未改，独立 PG 观察为 `AUDIT_NEW → AUDIT_NEW`。[JUnit](evidence/pg-late-writes-20261001/final-independent-results.xml)、[日志](evidence/pg-late-writes-20261001/final-independent-results.txt) |
| 任务创建/重试相关浏览器 | **36 passed / 0 failed / 0 skipped**，3.2 分钟，WSL Chromium。[JUnit](evidence/pg-late-writes-20261001/final-browser.xml)、[日志](evidence/pg-late-writes-20261001/final-browser.txt) |

浏览器以 `PLAYWRIGHT_MODEL_MODE=replay` 通过受保护入口运行 `task-failure`、`task-navigation`、`task-progress`、`unified-entry`，以及 `release-validation` 的 **E2E-006**。失败/进度 UI 用例包含路由桩；创建导航/统一入口及 E2E-006 实际调用后端和隔离 replay 供应商，E2E-006 断言失败任务点击重试后完成、已完成任务 retry 返回 409。未把 UI 桩称为真实供应商或数据库竞态验证，后者由新增独立 PG 回归证明。

最终被测输入 SHA-256：`8b7759ce37e4d64df1896b3363f3c6b70f55b9761b8fe6663fae83e4e98efedd`。源码/测试全清单见 [workspace-manifest.json](evidence/pg-late-writes-20261001/workspace-manifest.json)，算法为对当前 Git 跟踪文件及未忽略新增文件计算 SHA-256，再对排序后的紧凑 JSON 映射计算汇总 SHA-256；排除 `docs/validation/`、`artifacts/` 及 Git 忽略的私有/运行/构建输出。本轮新清单基于当前 HEAD，不继承旧基线的已删除项。完整后端结束后逐文件核对无漂移。

## 历史结论更正与范围

原 PG-only 报告所称“迟到保护继续由全量回归覆盖”，能够证明当时已测的发展 Version/current 与部分匹配状态路径，**未覆盖匹配完善阶段三类派生保存**。原独立审查的 P1 和修复前失败证据仍有效，属于修复前版本；本轮以新增常规回归及原脚本复验关闭该缺口，不能把旧 941 项通过倒推为旧实现没有问题。

全部验证仅使用受保护的本机 PG 验证库及本轮随机 schema；运行库仅独立只读核对，未 seed、注入故障或恢复备份。结束后 **35 表 / 2322 行摘要全部不变，运行配置及 13 份保留备份摘要不变**。PG 只剩原审查已记录的 4 个其他验证 schema，本轮新建对象已清理，没有删除其他对象。[保护核对](evidence/pg-late-writes-20261001/final-protection.json)

为固定端口进程测试及浏览器测试，通过项目脚本暂停了已核对归属的服务，现已按原配置恢复后端、前端和 Caddy；`http://localhost/api/health` 及实际 IP `http://172.21.208.223/api/health` 均 200，3000/8000 保持回环绑定。[恢复记录](evidence/pg-late-writes-20261001/service-restoration.txt)。最终源码指纹及原审查脚本/证据再次核对无变化，`git diff --check` 通过；仍在原 main/HEAD，所有修改未提交。

本轮不处理备份恢复权限，不重新调用真实供应商；模型响应只在隔离自动化中合成/replay，修改不增加或改变模型调用。未复跑完整浏览器、Windows、ARM、生产构建或历史真实供应商样例，不据此扩大验收结论。

## 证据归档说明

2026-10-01 提交收口仅整理重复/中间证据及文档引用；正文中的测试结果、源码指纹和当时 Git 状态均保留原口径。原被测清单和证据指纹不重写；已删除文件的原 SHA-256、用途及保留替代证据见[收口记录](GIT_CLOSEOUT_20261001.md)与[清理清单](evidence/cleanup-20261001.json)。
