# 伙伴服务能力发展中心 V1.1：Phase 0 / Phase A 开发启动记录

## 基线与范围

需求依据为用户提供 V1.1 完整评审稿（1718 段），唯一需求含义取第 27 章，验收取第 29 章。本次用户四项实施口径优先于文档中“明确选择版本”等宽松表述。只完成 Phase 0/A，不实现 B/C、不合并、不推送、不替换服务。

2026-09-05 实查：原目录 `/home/yuan/project/lingjian-agent`，干净 main，HEAD `f79cbb29ec7b3ad70c88e618e3161211f211c06a`。标签 `baseline/pre-enablement-20260905-f79cbb2`。未重新核验 GitHub 服务端，不以 origin 缓存声称远端同步。

旧后端 PID 227786，启动 19:19:14，cwd 原目录，8000；旧前端 PID 236033，启动 20:33:59，cwd 原 frontend，3000。业务源码均未晚于对应进程启动修改；`.env` / `frontend/.env.local` 修改时间早于启动，无数据路径进程级覆盖，实际旧库 `data/app.db`、上传 `data/uploads`，前端连接 localhost:8000。只读健康检查通过。未通过内存转储证明运行字节码；以干净源码、进程工作目录/启动时间与配置对应为基线证据。

新分支 `feature/partner-enablement-v1.1`，worktree `/home/yuan/project/lingjian-agent-enablement`。原分支指针保持。遵照本轮显式授权，在新 worktree 实施及分批本地提交，覆盖旧 AGENTS 的 main-only 限制。

## 隔离与数据保护

- `.isolation/snapshots/baseline.db` 为 SQLite Connection.backup 一致性快照，从只读旧库连接获取；再通过 backup 创建 `.isolation/runtime/app.db`。禁止复制活动单个 db 冒充备份。
- 上传为独立普通文件，拒绝软链接；副本中 partner_documents/deliverables 的 file_path 重定位到新 `.isolation/runtime/uploads`，原记录不动。这是隔离路径变换，与业务迁移分别比较。
- 新 `.env` 使用全新 JWT 密钥；数据库、上传、chroma 预留路径均在新目录。旧密钥未复制到环境文件；快照中原模型记录作为受保护备份保留，不调用。
- 新 `.venv`、`frontend/node_modules`、`.next`、日志及缓存独立；私有快照、配置、运行数据、日志均排除 Git。原源码、环境及上传 SHA256 清单仅存私有证据目录。
- 新环境前端 3100、后端 8100；E2E mock 18180。监听冲突即停止启动，不终止占用者。E2E 合成数据库 `/tmp/lingjian-enablement-e2e/app.db` 与副本分开。
- 浏览器 localStorage 按端口隔离；CORS 仅新前端，JWT 不通用。隔离运行器阻断非回环出站；不改既有模型选择、地址或密钥，不允许测试副本向付费服务发送业务材料。

实查 v9：partners 33、cases 3、deliverables 0、match_records 48、demand_profiles 48、project_opportunities 48、users 1、capability_tags 24。integrity_check=ok；既有外键异常为 cases rowid 3/4 → partners，两条。新共享层禁止孤儿案例进入。数量来自本轮查询，非抄写文档。

启动现状：config.py 从项目根 `.env` 加载，进程变量优先；默认数据路径从源码根定位。initialize_application 会执行 initialize_storage、空库 bootstrap、陈旧任务恢复，故所有启动与测试只在副本/合成库运行。旧迁移为 database.py 内 v8→v9 事务迁移；保留该机制，不引入框架。

## Phase A 最小详细设计

映射：RES-01/03/05/07；CASE-01/02/03/04；SEC-01/03/04/06/07/08/09 的资源权限基础；RES-04 与 CASE-06/07 的引用/撤权基础。RES-02 前台搜索、CASE-05 上下文、DEV/MOD/NAV/SCN 等留给 B/C；不能把基础函数通过等同后续完整验收。

数据：新增 enablement_resources（课程/实验草稿、revision、发布指针、三维授权、授权代次）；resource_capability_map 关联既有 capability_tags；enablement_resource_versions 不可变发布快照；case_share_configs 以既有 case_id 为主键；case_share_versions 仅保存独立授权共享文案与学习标签，不复制原始案例正文；enablement_reviews 记录核验人/服务端时间/链接状态/所核验 revision；enablement_audit_events 记录状态操作与代次，不保存敏感正文。共享角色由管理员明确维护，不自动给伙伴归因。

迁移：v9→v10 只建必要新表/索引，最后更新 schema_version。BEGIN IMMEDIATE 中完成 DDL 和版本更新，失败全部回滚；重复执行不新增记录。不修改旧业务数据；历史 FK 异常不修复但须验证无新增。旧初始化不得把 v10 降回 9。回退部署仅回到旧目录/服务，隔离库恢复则从保留快照生成新文件；不对原库做 downgrade，不抹除失败证据。

API：新增 `/admin/enablement/resources` 列表/创建、`/{id}` 详情/编辑、`/{id}/review|publish|unpublish|permissions`；案例共享配置挂在 `/admin/cases/{case_id}/sharing`，同样支持核验/发布/下架/授权。全链路 require_admin，沿用 Token 实时用户状态检查。普通用户/未认证不能访问管理接口。后台在原伙伴案例条目提供共享设置入口，不另建案例主数据录入。

资源元数据包含名称、简介/目标、岗位、产品技术、难度、语言/站点、先修、预计时长、费用/账号/环境条件、来源平台及 HTTPS/HTTP URL。未知字段显式“未知”，不得在后续约束匹配中视为满足。URL 禁止凭据、脚本协议与本机入口；后端不探测外链，不引入 SSRF。人工核验需要明确链接可用及内容/授权核验；发布必须核验当前 revision，有有效正式能力映射。修改草稿不改变已发布快照，修改后需重新核验发布。

共享配置必须有有效案例和启用伙伴。内部案例更新不自动刷新共享版本；共享已有审计时禁止直接硬删源案例/伙伴，以 409 提示先处理引用，避免删除审计或返回原始 FK 异常。

## 权限、资源引用与撤权契约

1. 系统可见、模型可发送、伙伴可外发三个布尔值默认 false；不能从管理员可见推导其它授权。候选使用还必须当前已发布/可见、实体有效、能力标签有效。核验本身不自动授权。
2. 引用 `{source_type: course|lab|case, source_id, source_version}`；课程/实验 id 是 resource_id，案例 id 是原 case_id。版本绑定所属对象，不接受模型 URL。服务端从有效记录解析最终 URL。模型投影为最小允许字段且不含 URL/核验备注；伙伴投影不含系统 ID、内部诊断、审计、内部 case 描述。
3. 降低权限/敏感撤权提升 authorization_epoch；旧版本授权代次不再有效。重新授权不自动复活旧共享内容，须核验和重新发布。普通资源下架保留审计快照但禁用当前入口；案例停止共享隐藏共享正文。后台可受控查审计，不能绕过模型/伙伴投影检查。
4. 后续方案说明文字必须逐段保存来源依赖及外发许可；没有明确许可的文字不能外发。发现任何已撤权来源时，所有依赖该来源的说明段落也隐藏；依赖不完整则整个伙伴视图拒绝复制并提示重新生成，不仅隐藏资源卡片。系统外已发送副本不能技术召回。

## 后续 Run / Plan / Version 设计（本轮不建表或执行器）

- Plan: id、owner_user_id、target_partner_id、active/archived、current_version_id、confirmed_version_id、revision、active_run_id。一份方案一个任务入口，任务聚合不混入 match_records。
- Run: id、plan_id、submission_id、based_on_version_id、operation(generate/revise/edit)、pending/running/ready/partial/failed/interrupted、deadline、execution_token、输入快照、错误阶段。owner+submission 唯一、plan 单运行租约；同一失败 run 并发重试 CAS 只允许一个请求获得执行权。
- Version: id、plan_id、version_no、based_on_version_id、完整结构化快照、资源条目、文字来源依赖、确认审计。唯一(plan, version_no)。草稿只能内部查看/编辑。伙伴视图仅允许当前 confirmed_version_id，不接受任意历史确认版或 current 草稿。
- 同一方案生成、调整和编辑串行；请求先核对 Plan.revision 和 based_on_version_id，并原子取得执行权；保存再次核对 execution_token、active_run_id、base_version、Plan active，较早请求迟到结果不能覆盖后续状态。
- 保存新 Version、条目、current 指针、Run ready 同事务，失败回滚，不产生有效半成品。资源缺口/证据不足/待评估是完整业务成功结果，可保存带提示版本；技术失败/部分执行失败保留 Run，不产生 Version，也不改变 current/confirmed。
- 新草稿保留旧 confirmed；确认必须指定当前草稿并通过最新引用/外发校验。预览/复制都重新校验当前 confirmed 和授权代次，复制使用服务端白名单输出，不信任前端已有预览。
- 运行中归档返回 409；先等执行完成或中断识别后再归档。归档后禁止运行、编辑、确认及复制；恢复不改版本指针但重新校验引用。
- 模型默认 180s、执行 10min；重启 60s 内识别 interrupted，人工重试。无队列；三并发是不同 Plan，同一 Plan 串行。Phase C 实现并测试上述行为，不以本设计声明为已实现。

## 验证计划与阶段门槛

每批提交前检查暂存 diff、密钥/数据排除、对应测试。基线 pytest、typecheck、build、Playwright；A 新增权限矩阵、发布核验与版本不变性、无效引用/源变化/撤权、事务失败恢复、历史数据逐行摘要比较、重复迁移；后台 1366×768 / 1920×1080 截图与 E2E。所有测试 mock，无真实模型验证。B 前台检索性能(2000+1000/P95≤2s)、C Run/Version、D 剩余全链路验收按独立阶段推进。

首批试点方向、真实课程/实验、共享授权材料与人工业务评审尚待业务确认。软件实现、自动化通过、真实模型验证、业务验收分别出结论；本轮不判真实业务试点 GO。

## Phase 0 已执行结果

- pytest -q：222 passed，0 failed/skip，2 个现有依赖弃用警告。
- npm ci 首次失败：Next 可选 Playwright peer 与原锁文件不兼容；新环境固定原 Playwright 1.49.1，并在 frontend/.npmrc 明确 legacy-peer-deps，随后 npm ci 通过。不升级旧依赖。
- npm run typecheck、npm run build 通过。
- npm run test:e2e：36 passed / 1 failed；重跑仍复现。原因是测试 stale=2s，而 slow mock 单阶段5s，状态轮询会提前恢复运行中任务。只将测试 stale 调整60s，失败用例定向重跑1 passed。最终完整回归见交付报告。
- 基线截图保存在私有 .isolation/evidence/baseline；旧版本已跟踪截图未替换。后续回归截图改到新私有证据目录。
