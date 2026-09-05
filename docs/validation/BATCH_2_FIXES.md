# 第二批修复与验证记录

日期：2026-09-05。范围：模型场景、配置解析和校验、请求等待时间、前端异常收尾。第一批修改保留；第三、四批尚未执行。

## 修改文件及关键变化

| 文件 | 变化 |
| --- | --- |
| `backend/app/model_resolver.py` | 显式场景绑定不存在或已停用时抛出配置错误；不再吞掉数据库异常并切换到环境模型；保留数值 0。未绑定时维持原选择顺序。 |
| `backend/app/ai_client.py` | 未传 timeout 时使用模型配置；显式传入 60 秒时确实使用 60 秒，消除原有哨兵值歧义。 |
| `backend/app/routers/model_config.py` | 新增/修改时验证有限且非负的 temperature、0–1 的 topP、正整数 maxTokens 和 timeoutSeconds；绑定只接受已启用模型。密钥配置状态及连接测试复用实际密钥解析规则。 |
| `backend/app/routers/match.py` | 需求画像使用 demand_profile，自动标签建议使用 tag_suggestion；主匹配配置不可用时返回可理解的 503 错误。 |
| `backend/app/routers/profile.py` | 结构化提取和画像正文均使用 partner_profile；配置不可用时保留资料并返回 503。 |
| `backend/app/routers/capability_tags.py` | 人工扫描遇到无效场景绑定时报告配置错误，不显示虚假的扫描成功。 |
| `backend/app/routers/system.py` | 适配解析器新错误：无效默认绑定在模型状态中显示异常，避免整页因未捕获异常而失败。系统状态的完整整改仍属于第三批。 |
| `frontend/lib/api-request.ts`、`frontend/components/auth-provider.tsx` | 按操作设置等待时间；保留调用者 AbortSignal；统一断网、超时及参数校验提示。匹配/重试连接异常提示先查看“我的任务”，不自动重提。 |
| `frontend/components/admin-panels.tsx`、`frontend/components/admin-demand-panels.tsx` | 管理页接入相同请求等待策略。模型停启、设默认、场景绑定检查 HTTP 状态并显示失败；保存后恢复按钮，失败时保留输入；移除未经供应商确认的固定 token 上限；显示不可用绑定，说明推荐摘要暂无独立调用。 |
| `frontend/app/page.tsx` | 移除定时模拟的处理阶段，展示真实的等待提示；历史详情加载失败后退出加载状态。 |
| `frontend/app/admin/partners/[id]/page.tsx` | 保存、资料上传/下载/删除、画像生成、案例及交付物操作统一 catch/finally，恢复 busy 和按钮。 |
| `frontend/app/admin/partners/page.tsx` | 批量画像按当前启用伙伴数量计算等待预算，保留现有费用确认与顺序生成行为。 |
| `frontend/app/admin/users/page.tsx` | 创建、编辑、状态、重置、解锁、审批均捕获网络异常并恢复操作状态；创建/重置前清除旧临时密码展示，避免与新结果混淆。 |
| `frontend/components/task-list.tsx` | 捕获归档和恢复时的网络异常；重试使用统一长请求策略。 |
| `backend/tests/test_model_config.py` | 隔离验证解析优先级、失效绑定、参数、密钥状态、请求参数及场景调用链。 |
| `frontend/e2e/batch2-resilience.spec.ts` | 定向验证请求预算、取消、超过 30 秒的响应、超时提示和管理操作失败收尾。 |

## 场景与等待预算

| 操作 | 场景 | 前端等待预算 |
| --- | --- | --- |
| 伙伴匹配 | partner_match | 匹配/重试整条请求 360 秒 |
| 需求画像、项目机会 | demand_profile | 包含于匹配/重试请求 |
| 自动标签建议 | tag_suggestion | 包含于匹配请求 |
| 单伙伴结构提取、画像正文 | partner_profile | 180 秒 |
| 人工扫描最近 10 条需求 | tag_suggestion | 360 秒 |
| 模型连接测试 | 指定模型配置 | 45 秒 |
| 批量伙伴画像 | partner_profile | 当前启用伙伴数 × 180 秒 + 30 秒；至少按 1 家计算 |
| 普通查询和写入 | 不涉及模型 | 30 秒 |

未绑定场景的选择顺序：默认场景绑定 → 启用的默认模型 → 首个启用模型 → 环境变量。明确绑定无效时不会换用其他模型。

`recommendation_summary` 保留为配置项，目前没有独立调用，推荐理由随伙伴匹配生成。

## 接口、数据结构与业务影响

- 路由、接口字段、数据库结构未增删，无迁移；原有两角色和任务所有权约束保留。
- 行为变化：无效参数返回 422；保存不存在/停用绑定返回 400；主匹配、画像、人工扫描遇到不可用绑定返回 503。参数为 0 时按用户保存值发送。
- 未绑定场景的原选择行为保留。没有改动真实模型地址、模型名、API Key、默认标记或场景绑定。
- 前端不因超时推断任务已保存，也不自动发起新任务。任务后续处理原有部分完成及规则提取兼容行为保留。

## 验证结果

- 后端：71 项定向回归通过（43.73 秒），随后新增的系统状态配置异常用例通过（0.29 秒），共 72 项。覆盖配置选择、场景调用、参数、画像保护、任务生命周期、越权与 OpenAPI 安全声明。
- 前端：10 项定向测试全部通过。首轮 7 项通过；修正测试定位器冲突和用户子路径拦截后，其余 3 项定向重跑通过（14.7 秒）。其中实际延迟 31 秒返回的匹配请求正常完成。
- `npm run typecheck -- --incremental false` 通过；`git diff --check` 通过。
- 测试全部使用 pytest 临时目录或 `/tmp/lingjian-agent-e2e` 的隔离数据库/上传目录，使用模拟模型及浏览器请求拦截，没有真实模型调用。首轮测试夹具与定位器问题均已修正，无剩余测试失败。
- 无全量构建、无全量 E2E、无真实数据库迁移或历史数据修复。

复现命令（浏览器测试前先停止同项目的开发前端）：

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider backend/tests/test_model_config.py backend/tests/test_profile.py backend/tests/test_tasks.py backend/tests/test_authorization.py backend/tests/test_openapi.py
cd frontend
npm run typecheck -- --incremental false
npm run test:e2e -- e2e/batch2-resilience.spec.ts
```

最终复核：真实数据库、两份环境配置及 8 个上传文件共 11 个文件的 SHA-256 均与本批开始时一致，上传文件清单一致。已用 dev.sh 恢复前端，3000/8000 均健康；后端仍为原 PID 174329，未重启。

## 剩余边界

- API 仍同步等待模型。浏览器中断不保证停止后端工作；批量画像可能等待较长时间。预算依据现有调用步骤，HTTP 分阶段超时不等于严格的总执行上限。
- 本轮未向真实模型发送请求，供应商实际响应速度和各模型参数上限未作在线确认。
- 推荐内容/证据约束、系统状态完整只读化和异常脱敏留待第三批；历史数据修复留待第四批。
- 后端开发服务没有 reload；隔离测试服务加载了本轮代码，原 8000 端口后端未重启，需重启后端才能在日常服务中生效。

## Git 状态

在 main 直接修改，当前领先 origin/main 9 个既有提交；保留第一批的未提交内容。当前工作区共 17 个已跟踪文件修改、7 个未跟踪新增文件（包含两批内容）。本批不提交、不推送，不创建分支或 worktree。
