# 能力发展可选伙伴关联 — 2026-10-02

状态：实现、原运行库升级、隔离验证与本地服务恢复已完成，2026-10-02 02:35 UTC 后可刷新使用。独立验收尚未由另一任务确认。

## 变更范围

- 单个自然语言输入框即可开始能力发展；关联已有伙伴资料可选。不建立虚拟伙伴，不改公共伙伴画像。
- DevelopmentRequest 及分析/答复契约允许 target_partner_id=null；空选择规范化为 null，非空无效 ID 仍拒绝。已有任务不允许改变关联。
- 不关联时跳过画像查询、伙伴依赖查询及伙伴指纹；检索、生成和后续理解使用发展描述和 known_baseline。
- 模型理解必须返回 effective_baseline。解释轮保存到 Request 的有效请求快照，修改轮保存到 Version；后续即使原纠正移出最近三轮对话，基础仍送入模型。原文留在任务，维持模型最小投影不发送 raw_demand。
- 历史联合查询改为 LEFT JOIN；合法空关联没有“不可用伙伴”或虚构伙伴，仍支持侧栏、分页、搜索、详情、归档及原 owner/admin 权限。
- 清除或更换关联清除来源 task/case/version，保留输入；模式切换保留各自草稿。六个模板采用本轮用户文本，后三个使用通用主体并增加可选基础。
- 保留先落库后模型、Plan/Run/Version/current、幂等、重试、失败不覆盖旧结果和迟到响应保护。

## 迁移

`backend/app/development_partner_schema.py` / `scripts/migrate_development_partner.py`：schema 18 → 19，只对 development_plans、development_requests 的 target_partner_id 执行 DROP NOT NULL；保留现有 FK。

脚本先将原运行库完整 pg_dump 写入新的私有目录并验证可读，再在带锁等待上限的事务里执行 DDL、核对 FK、记录版本，验证全部业务表行数未变。无删除、回填、伪伙伴、重新 seed 或权限修改。

事务出错自动回滚。提交后只有两列均不存在 NULL 数据才能用受保护 rollback 恢复非空约束；已有无关联任务时明确拒绝，不能为回退丢弃数据。

## 验证记录

- TypeScript / Next.js 正式构建：通过。
- 后端首轮：195 通过、1 失败；失败是原文不应进入模型的旧安全边界。实现已恢复该边界，修正后的最终回归为 196 通过、771 未选择（范围外）。
- 新增 PostgreSQL 用例覆盖 NULL/空字符串/真实伙伴，真实外键，旧 schema 事务成功与失败回滚，原文保留，模型实收纠正，越过最近三轮后的基础保存，重试/幂等/current，列表分页搜索、归属权限及归档恢复。
- 新增浏览器用例使用用户原样需求，在桌面和窄屏不选伙伴提交、双击、刷新重开与续问；另测清除/更换来源后保留草稿。
- 全部写入和模型桩只使用专用 PostgreSQL 随机临时 schema、合成数据及 loopback replay。没有付费真实模型验证。
- 原运行库：已实际从 18 升到 19；两列 is_nullable=YES，现有 FK 保留，全部业务表行数未变，用户/伙伴/Request/Plan/Run/Version/条目/匹配记录摘要未变。原服务已按 `bash enablement-dev.sh start` 恢复。首次自动审批因最初只读范围拒绝，补充后续用户原文后同一命令重审通过。

证据工作目录：`/tmp/banfei-optional-partner-do1wfd00`。保留修改前源文件快照、源码摘要、日志和进度检查点。

独立验收另行进行；本轮浏览器自动化范围是 WSL Chromium，不能等同用户 Windows 浏览器人工验收。没有提交、推送或远程部署。

原库私有备份：`/home/yuan/project/lingjian-agent-enablement/.isolation/backups/optional-development-partner-20261002T023022Z`（完整 pg_dump，707766 bytes）。仅本地保留，不提交备份或凭据。

## 最终结果与证据

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| PostgreSQL 后端相关回归 | 196 passed | `/tmp/banfei-optional-partner-do1wfd00/backend-final.log` |
| 回放桩更新后的相关回归 | 34 passed | `backend-replay-followup.log`（同目录） |
| 多轮模型实际输入捕获 | 关联/无关联两项通过；纠正已移出最近三轮，但请求仍含纠正基础 | [无关联模型实收](evidence/optional-development-20261002/unlinked-actual-model-baseline.json)、[有关联模型实收](evidence/optional-development-20261002/linked-actual-model-baseline.json) |
| 浏览器相关用例 | 最终 83 个不同用例全部通过；初轮加针对性补跑，非一次全绿运行 | `browser-first.log`、`browser-final.log`、`browser-last.log`、`advisor-final.log`（同目录） |
| 类型检查与生产构建 | `npx tsc --noEmit` 与 `npm run build` 均通过 | `build.log`（同目录），最终类型检查退出 0 |
| 原运行库升级 | schema 19；两列可空；FK及原记录不变 | [迁移核验](evidence/optional-development-20261002/runtime-migration.json) |
| 原服务恢复 | backend/frontend/Caddy 均 running；HTTP80，3000/8000仅回环；18180已停止 | [恢复核验](evidence/optional-development-20261002/runtime-restored.json) |
| WSL 与 Windows 主机 HTTP | localhost、172.21.208.223 的 `/api/health` 均 200；WSL 两地址首页也 200 | 同上；Windows 检查经允许的主机执行，初次受限 shell 的实际 IP 请求受限后未据此判服务失败 |

浏览器 83 项覆盖无关联原样需求、真实 HTTP 落库和回放结果、重复点击、刷新重开、侧栏选中/分页、滚动连续性、两种模式、迟到响应、新旧任务切换、保留/清除来源、键盘与窄屏、权限撤回、讨论/修改/历史版本。测试中校正了早于当前 UI 的旧断言：内嵌画像摘要已折叠、主回答代替首阶段分析、每次续问有 Run、范围外请求先落库后正常结束、现行错误提示与统一字号。没有为满足测试恢复旧生产流程或扩大产品实现。

合成数据视觉证据：

- [桌面开始前](evidence/optional-development-20261002/unlinked-before-start-1366.png) / [桌面结果](evidence/optional-development-20261002/unlinked-persisted-result-1366.png)
- [窄屏开始前](evidence/optional-development-20261002/unlinked-before-start-390.png) / [窄屏结果](evidence/optional-development-20261002/unlinked-persisted-result-390.png)
- [桌面完整录屏](evidence/optional-development-20261002/unlinked-flow-1366.webm) / [窄屏完整录屏](evidence/optional-development-20261002/unlinked-flow-390.webm)

复现：在隔离回放环境打开 `/?mode=development`，保持“不关联已有伙伴资料”，输入“我有个伙伴，现在只有基本的上云迁移能力，想往AI agent开发方向发展，请推荐下相应的课程和实验”，点击开始；预期先获得任务 ID，原文收缩为本次需求、侧栏选中，真实阶段完成后显示已有资源。刷新后原文/结果保留，续问不另建 Version。来源入口下清除关联，应同时清除 task/case/version 参数且保留输入。

不在原运行库重复创建验收数据或调用真实模型。生产可用性通过实际迁移和只读健康检查确认，完整业务交互在专用 PostgreSQL 临时 schema 测试。WSL Chromium 的截图/录屏与 Windows 主机 HTTP 检查不能替代用户 Windows 浏览器人工验收；真实供应商生成质量、ARM/AgentArts部署未验证、未操作。

Git HEAD 保持 `07e31bb3318ec9aa67a8259fd0dc840b7577afb1`；保留先前全部未提交改动，未 commit/push/deploy。`git diff --check` 通过。本轮相对开工快照的变更清单见 `/tmp/banfei-optional-partner-do1wfd00/changed-since-task-start.json`。
