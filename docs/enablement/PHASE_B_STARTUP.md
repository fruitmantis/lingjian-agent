# Phase B 开发启动与接口设计

需求基线：V1.1 第 27 章；验收：第 29 章。Phase A 已获用户验收。
本次核验：稳定目录 /home/yuan/project/lingjian-agent，main f79cbb29ec7b3ad70c88e618e3161211f211c06a；独立目录 /home/yuan/project/lingjian-agent-enablement，feature/partner-enablement-v1.1，起点 5408e2d6caaabc69d965226a1060d85f1f222019，两工作区干净。未核验远端同步。旧服务 3000/8000 保留；验证使用 3100/8100 和 18180 本地 mock。

## 本轮设计
- NAV-01 / SCN-01：复用 App Shell，新中心 /enablement，助手与资源双 Tab，三个资源 Tab；场景入口指向实际可用的资料准备和检索能力，资源不成为独立 Skill。
- RES-02/03：新增已登录用户 /enablement/resources 检索与详情，复用 Phase A 当前发布版本、授权 epoch、标签有效性和三维权限校验。只查询系统可见版本；管理员也不能绕过前台发布校验。元数据白名单，未知字段显示未知。共享案例不读取内部正文。
- RES-08：POST redirect 只接受版本，不接受客户端 URL；事务中重新授权并由后端解析 URL，记录 redirect_initiated / 发起跳转，不推断外部学习行为。
- CASE-05 / PRT-01 / MAT-01：链接仅携带标识。GET /enablement/context 在后端重查任务归属、推荐伙伴、当前启用伙伴以及共享版本。画像和有效证据引用仅供内部查看，系统可见不代表模型发送或伙伴外发。原匹配风险标记为待能力发展流程复核，不能静默变成培训需求。请求取消及刷新防止旧来源覆盖新来源；失效即清除展示。
- NAV-02：既有匹配记录响应补充 task_type=partner_match，列表可筛选；development_plan 返回真实空集合。保留任务所有权和原详情主体，不新增假任务。
- Phase B 不调用模型，不生成/保存发展方案，不实现 Plan/Run/Version。后续关系与 confirmed_version_id 外发、串行编辑、迟到结果、防撤权文本泄露等继续遵守 STARTUP_AND_DESIGN.md；本轮页面不是方案业务闭环。

## 增量迁移与回退
schema v10 → v11 仅新增 resource_redirect_events 及索引，不改写旧任务或资源数据。事务完成后才更新 schema_version；失败全部回滚，可重试。迁移前使用 SQLite backup 保存独立运行库 v10 快照，重复执行不重复创建。不修改原数据库。回退可停止新版服务、继续原服务；新版恢复在独立副本上从 v10 快照重建，保留失败副本和事件审计供排查。

## 验证和提交
同步编写资源筛选、共享白名单、A/B/admin、撤权、上下文、任务类型和迁移测试。Playwright 在 /tmp 合成数据上回归原功能并保存两个分辨率截图；构建与浏览器测试串行，避免共写 .next。按实际验证批次审查暂存内容并提交；无 push、merge、部署。完成报告后停止新版验证服务。

首批验证：`.venv/bin/python -m pytest backend/tests/test_enablement_workspace.py backend/tests/test_enablement.py backend/tests/test_enablement_migration.py -q`：71 passed。涵盖前台授权独立性、共享正文白名单、当前版本/撤权、所有元数据筛选、A/B/admin 上下文、真实 task_type 和迁移故障回滚。前端页面骨架 `npm run typecheck --prefix frontend` 通过，后续继续浏览器验证。
