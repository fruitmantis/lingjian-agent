# Phase A 后端批次验证

已实现管理员资源/共享配置14个API操作、7张增量表、独立发布版本、revision冲突检查、用途授权默认拒绝、当前修订人工核验、三维用途白名单、撤权代次与源有效性校验。新层不复制案例正文；已有共享引用的案例删除返回409，首次共享/删除串行。

对应 RES-01/03/05/07、CASE-01/02/03/04、SEC-01/03/04/06/07/08/09；RES-04、CASE-06/07仅资源引用及撤权基础，完整方案/历史说明文字过滤留Phase C。

实际验证（2026-09-06，新worktree，mock，临时库）：

| 命令/验证 | 结果 |
|---|---|
| pytest -q（最终，含JUnit输出） | 270 passed，0 failed/error/skipped，2个依赖弃用警告 |
| pytest -q backend/tests/test_enablement.py backend/tests/test_enablement_migration.py backend/tests/test_files.py backend/tests/test_openapi.py | 56 passed，0 failed/skipped |
| python backend/scripts/verify_enablement_snapshot.py | 隔离v9→v10，16个旧表逐行摘要不变，新增7表；2条既有FK，0新增，完整性ok，重复结果相同 |
| 新启动器start→stop→status | 新服务启动健康、退出后确认停止，旧服务不动；非回环connect被阻断，回环8100允许 |

故障注入覆盖首/中/末DDL、schema标记写入、发布指针更新失败；版本事务回滚后可重试，无半版本。两请求并发发布只有一个成功；源案例首次共享与删除不会同时成功。

曾发现并修复：迁移故障注入原本误把第10处当DDL（实际9处DDL），改为覆盖最后schema写入；旧历史修复工具主动拒绝v10导致25个夹具错误，保留工具v9保护并重建其合成v9测试夹具，额外验证拒绝v10。未执行历史业务修复。

本批没有真实模型验证、没有业务内容验收；未实现Plan/Run/Version执行链，也未实现前台检索/跳转。原有匹配模型体系、健康度算法和任务所有权规则未改。
