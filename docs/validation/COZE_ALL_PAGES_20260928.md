# 全站 Coze 风格统一 · 2026-09-28

## 工作基线与范围

- 工作目录：`/home/yuan/project/lingjian-agent-enablement`。
- 保持 `feature/coze-ui`；HEAD 为 `9296aecf105b81eb550c5cf6c52ae46c69fa849b`。本轮基于此前未提交的首批改版、字体精修和边框修复继续，未切换分支、创建 worktree、提交、推送、合并或部署。
- 用户后续明确授权将当前样式扩展到全部业务页面和后台。本轮只改共享样式、四个 CSS Module、AppShell 的样式适用范围，以及三个反馈页的 className。保留页面文字、字段、业务展开方式、操作事件、路由目标和业务请求；全部非独立页面复用已有的小屏导航按钮。
- 未改后端、接口、数据库、权限、身份逻辑、任务状态、版本及资源分类。没有业务模型调用，没有向运行库执行 E2E 写操作。

## 实际修改

1. `frontend/components/app-shell.tsx`、`frontend/app/coze-workspace.css`：全站启用现有工作台外壳；桌面侧栏 230px、浅灰背景；后台导航独立滚动，底部账号操作可达；普通目录/管理页保持宽布局，新任务/顾问正文保持阅读宽度。
2. `frontend/app/globals.css`、`frontend/app/ui-system.css`：统一文字层级、灰色、边框、按钮与标签尺寸。卡片保留 **1px #D4D4D0**，16px 圆角和轻阴影；说明块使用浅灰；目录卡片悬停不抬升。反馈页接入共享 page/table 类，登录、改密和身份弹窗使用相同控件体系。
3. `partner-materials-manager.module.css`、`material-files.module.css`、`enablement-admin.module.css`、`opportunity-ui.module.css`：颜色、圆角、阴影改用共享 token；资料预览使用 16px/26px 本地字体；长标题不会挤压弹窗关闭按钮。
4. 本轮字体未更换，沿用前轮获准自托管的 **Noto Sans SC / SIL OFL 1.1**，来源、文件和许可证在 `frontend/public/fonts/noto-sans-sc/`。保留原 Logo 和少量品牌红、成功/警告/失败语义色。

## 页面与截图

- 覆盖当前 **36 个 page.tsx 路由**：新任务、场景、伙伴列表/详情、任务列表/两类详情、三类资源及详情、账号/反馈、所有后台栏目及详情、登录/改密/403；4 个兼容路由验证跳转目标。动态路由使用合成代表记录。
- 改前/改后使用同一份合成内容、固定时间、100% 浏览器缩放，等待 `document.fonts.ready`。窗口：1366×768、1920×1080、390×844。
- 每个尺寸 38 个对照状态，合计 **114 状态**。每个状态提供单屏和正文/卡片/表格局部截图。资料弹窗关闭按钮修复后另外更新相关截图。
- 对照入口：[`review.html`](../../artifacts/coze-all-pages/review.html)；也可直接浏览 `before/`、`after/`。改密与资料预览补充截图位于 `extra/`。凭据及密码输入已遮蔽；全是合成数据。
- 三尺寸没有整页横向溢出；宽表格保留容器内横向滚动。全部 114 对照状态的 main 文本一致。源码 AST 检查见 `scope-verification.json`：除视觉属性及已说明的移动导航作用范围外，TSX 没有业务变动。

## 验证记录

验证入口为既有 `scripts/run_postgres_validation.py browser`，私有 `BANFEI_TEST_DATABASE_URL` 指向本机 `banfei_agent_test` 的临时 schema。截图使用浏览器合成 API 拦截；反馈交互回归仅写专用验证 schema，上传与错误日志在 `/tmp`。运行服务、Playwright 服务和 build 顺序执行，不并行写 `.next`。

- 改前截图：3/3 通过。
- 全站与交互回归：首次 29/33 通过；4 个失败属于测试问题（3 个新兼容跳转测试拦截器误命中文档 URL、1 个既有反馈测试仍断言旧错误文案）。修正测试，不改产品接口或错误逻辑。
- 针对性复测 **7/7 通过**（4 个失败用例修正后通过，另加 3 个尺寸的弹窗修复回归）。33 个不同 UI 用例最终全部通过；详细统计见 `artifacts/coze-all-pages/test-results-summary.json`。
- 最终 `npm --prefix frontend run typecheck`、`npm --prefix frontend run build`、`git diff --check` 通过；Next.js 15.5.19 完成 31 个静态页面生成。
- 已恢复原开发/HTTPS 服务。预览 `https://172.21.208.223`；使用原项目根 CA 校验证书，`/login?method=key`、`/api/health` 与本地 WOFF2 均返回 200；字体响应 SHA-256 与仓库文件一致。证据见 `preview-health.json`。
- 本地对照页已在用户的 Windows Edge 窗口中打开；该操作仅展示静态截图，不代表 Windows 业务流程自动化测试。
- 相关测试覆盖：移动导航、资料查看/关闭、管理员改密表单、资源跳转、筛选、表格控件、任务失败/恢复展示、顾问答复、反馈上传/删除/错误保留与处理状态。
- 字体核验阻断外部来源请求，检查实际渲染中文/英文/数字及 400/500/600/700 字重。机器证据在 `extra/fonts-*.json`；凭据与诊断代码等用途允许保留等宽字体。Coze 本身的 WSL/Windows 字体取证沿用前轮证据，本轮不重新推断。

本轮自动化范围为 WSL Chromium 和本机隔离 PostgreSQL；不等同于 Windows Edge 全套功能验收或 ARM 验证。

## 复跑

先通过 `bash enablement-dev.sh status` 核实并停止当前运行服务；加载原私有验证配置中的 `BANFEI_TEST_DATABASE_URL`（不打印凭据），再运行：

```bash
.venv/bin/python scripts/run_postgres_validation.py browser --config=playwright.unified-ui.config.ts
```

如仅验证视觉对照，使用 `--config=playwright.all-pages.config.ts`。该配置默认与现有 before 合成数据做文本比较，不覆盖改前截图。所有页面运行结束后再 build 并恢复 `bash enablement-dev.sh start`；不得与运行服务共用 `.next` 同时启动。
