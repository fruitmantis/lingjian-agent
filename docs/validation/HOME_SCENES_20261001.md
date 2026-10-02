# 首页六场景模板验证（初次交付）

> 后续独立复核发现三类边界问题。修复和当前 76 项回归见[最新修复报告](HOME_SCENES_FIXES_20261002.md)；以下为初交付历史记录。

日期：2026-10-01（UTC；本机 +08:00 已进入 10 月 2 日）。正式工作区 `/home/yuan/project/lingjian-agent-enablement`，分支 `main`，HEAD `07e31bb3318ec9aa67a8259fd0dc840b7577afb1`。本轮未提交、未推送、未部署。

## 工作区交接与实施边界

原转场实施线程最后事件为 `2026-10-01T15:45:22.182Z` 的 `task_complete`。实施前多次复核，其 13 个源码/测试文件均与原交付清单一致，没有新回合或源码变化。本轮在同一 checkout 接续，没有新建仓库、分支或 worktree。

原有未提交的转场组件、任务详情、任务导航、进度、样式、测试、文档和录屏均保留。此次修改仅涉及下列 7 个前端文件，另补充本报告和验证索引：

- `frontend/lib/scenes.ts`：追加独立 `HOME_SCENES` 配置；场景广场的完整注册表和原导航不变。
- `frontend/app/page.tsx`：六按钮、双模式独立草稿、替换确认、占位选择与提示、同步重复提交保护；移除首页旧分类/换一批/混杂场景卡。
- `frontend/components/enablement-workspace.tsx`：向已有发展输入传递首页草稿。
- `frontend/components/development-assistant.tsx`：受控方向输入、提交忙状态及同步重复点击保护。
- `frontend/app/coze-workspace.css`：轻描边按钮，桌面 3×2、窄屏 2×3，保留模式控件样式。
- `frontend/e2e/home-scenes.spec.ts`：12 项行为验证。
- `frontend/playwright.config.ts`：将新专项纳入现有 UI 子集。

后端、API、PG schema、模型配置、认证和部署配置未改。两类创建仍沿用先落库、返回真实 ID、打开并选中任务，再读取真实进度与已保存结果的现有机制。

## 最终行为

六项为 AI项目找伙伴、按行业找伙伴、按能力找伙伴、伙伴发展建议、能力短板分析、为项目补能力。前三项填匹配需求，后三项填发展方向；发展保留真实 PartnerSelect，匹配无需伙伴。

按钮不使用 `actionHref` 导航或提交业务请求。模式变化通过同页 history 更新；主页 DOM 保持，`partner_id`、`task_id`、`case_id`、`case_version` 保留。模板填入后聚焦并选中首个 `【占位提示】`。两个模式各自保留草稿，空草稿或未改模板直接替换，目标草稿含用户编辑时确认“已有未提交内容，要替换成这个场景模板吗？”，取消不改变模式或内容。

未替换占位内容只给提示，不阻止自由编辑或提交。提交中按钮禁用；失败保留原文、允许修正重试；同一轮重复点击只发一个创建请求。成功后离开新需求入口，沿用原连续转场和任务选中行为。

## 实际验证结果

| 检查 | 结果 |
|---|---|
| 六场景专项，实际 IP `http://172.21.208.223` | 12 通过，0 失败，0 跳过；进程耗时 37.54 秒 |
| 原转场、真实 HTTP 回放、进度、导航、失败保护和统一入口 | 51 通过，0 失败，0 跳过；进程耗时 235.00 秒 |
| TypeScript `tsc --noEmit --incremental false` | 通过，退出码 0 |
| Next.js 生产构建，`BANFEI_BUILD_CPUS=2` | 通过，退出码 0 |
| `git diff --check` | 通过 |
| WSL Chromium 截图复核 | 桌面 1366×900、窄屏 390×844；两种模式按钮布局、占位选择及无横向溢出通过 |
| Windows 用户现有浏览器会话、Windows Edge 手动完整交互 | 未验证，当前会话没有 Computer Use 所需工具绑定 |
| ARM、真实模型质量、全量后端回归 | 未执行，本次前端范围不包含这些检查 |

两个最终浏览器集合共 63 项，不包含首轮失败数字。首轮专项 10 通过、2 失败，原因均为新增合成夹具不一致：拒绝创建后详情仍返回 200，误触发原任务恢复；失败文案未采用现有重试按钮对应文案。修正夹具的 404 和标准失败响应后，保留原断言重跑，最终 12 项全部通过；未为通过测试修改产品恢复或错误机制。

[逐用例结果](evidence/home-scenes-20261001/initial-browser-results.json)、[执行退出码和耗时](evidence/home-scenes-20261001/initial-execution-summary.json)、[最终源码 SHA-256](evidence/home-scenes-20261001/initial-source-manifest.json)、[类型检查](evidence/home-scenes-20261001/initial-typecheck.txt)、[构建输出](evidence/home-scenes-20261001/initial-build.txt)。源码清单覆盖本轮与继承转场共 16 个文件；原转场中未涉及本轮的 9 个文件哈希保持一致。

## 可复现步骤

仅在现有隔离验证环境执行提交类检查：

1. 依次点击六按钮，检查正确业务模式和文本框、首个占位提示选中，任务列表没有因点击模板新增任务。
2. 分别编辑匹配和发展草稿，来回切模式确认文字保留；点击目标模式另一模板，取消确认后模式和原文不变，确认后仅替换目标草稿。
3. 从带伙伴及项目/案例参数的入口切换场景，确认来源参数和伙伴仍在；发展选择另一允许伙伴并自由输入，提交体使用所选伙伴 ID 和完整原文。
4. 模拟创建失败，确认输入可编辑且原文保留；重试成功后打开真实任务并选中侧栏。连续点击只创建一次，切历史任务不串内容。
5. 桌面及窄屏以 Enter/Space 操作场景按钮，检查 3×2/2×3 排列和横向溢出。继续运行现有转场回归验证慢响应、逐帧原文连续、刷新、减少动效与任务切换。

## 命令与数据安全

先私密加载现有 `.isolation/runtime/dev/validation-environment.json`，不输出连接串。通过项目脚本核对并管理当前服务；浏览器测试和构建串行执行，避免共同写 `.next`。

```bash
npm --prefix frontend run typecheck -- --incremental false
PLAYWRIGHT_MODEL_MODE=ui PLAYWRIGHT_HTTP_ORIGIN=http://172.21.208.223 .venv/bin/python scripts/run_postgres_validation.py browser home-scenes.spec.ts --reporter=line,junit
PLAYWRIGHT_MODEL_MODE=replay .venv/bin/python scripts/run_postgres_validation.py browser task-transition task-progress.spec.ts task-navigation.spec.ts task-failure.spec.ts unified-entry.spec.ts --reporter=line,junit
BANFEI_BUILD_CPUS=2 npm --prefix frontend run build
git diff --check
```

运行器只为专用 PostgreSQL 验证库创建随机临时 schema，测试上传和诊断放本轮 `/tmp` 目录，验证器只清理其自建 schema。UI 专项拦截合成接口；已有真实 HTTP 持久化用例使用隔离 PG 和回放模型，没有付费真实模型调用或真实伙伴资料发送。测试前只读统计正式库运行中匹配/发展任务均为 0；未向正式库写测试数据，未读取用户身份凭据文件。

本机服务已通过原 `enablement-dev.sh start` 恢复。实际 IP `/login`、`/api/health` 均为 HTTP 200，无协议跳转；80 对外，3000/8000 仅监听 127.0.0.1，回放端口 18180 已退出。此为 WSL 服务与自动化验证，不代表 Windows 用户会话已登录或实机验收完成。

## 截图证据

截图来自本轮 WSL Chromium 的合成隔离页面，不是用户现有 Windows 浏览器会话；未修改截图内容。

- [匹配桌面](evidence/home-scenes-20261001/home-scenes-1366.png)
- [匹配窄屏](evidence/home-scenes-20261001/home-scenes-390.png)
- [发展桌面](evidence/home-scenes-20261001/development-scenes-1366.png)
- [发展窄屏](evidence/home-scenes-20261001/development-scenes-390.png)
