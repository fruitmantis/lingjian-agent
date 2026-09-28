# Coze 风格 UI 首批实施与验证

2026-09-28，等待用户确认视觉方向。工程验证通过不代表业务上线许可。

## 分支与边界

- 用户本轮明确授权从当前 main 新建并切换 `feature/coze-ui`，覆盖 AGENTS.md 默认不建分支的约束。
- 初检：main、工作区干净、目标分支不存在。
- 基线 / 当前 HEAD：`9296aecf105b81eb550c5cf6c52ae46c69fa849b`。没有 commit、push、合并、部署或新 worktree。
- 当前正式目录：`/home/yuan/project/lingjian-agent-enablement`。Git 分支创建需要写当前目录引用的共享 Git 元数据，已通过执行权限审批；没有读取旧工作区源码或启动其服务。
- 产品代码仅改前端 TSX 展示结构与 CSS。后端、API、数据库、模型、提示词、登录、权限、任务状态、Plan / Run / Version / current 与资源分类均未改动。

## 已完成

- `coze-workspace.css` 统一首批页面的颜色、间距、控件、Tab、边框、圆角、阴影、表格与弹层样式；复用现有字体、图标和原 Logo，保留华为红及语义色。无新依赖、UI 框架或 Coze SDK。
- 公共侧栏 230px、浅灰底。入口、顺序、历史任务与独立滚动保留；窄屏增加可展开导航，导航到另一页面后收起。
- 首页 840px 居中输入区，两个业务模式保持显式 Tab。能力发展将伙伴选择与方向输入组织到一个容器，完整画像摘要和证据可展开查看；来源上下文与数据使用说明保留。原场景分类、示例、换一批与入口保留在“从场景开始”中。
- 两类任务详情正文 860px，顾问答复为主。目标 / 需求、伙伴推荐、分数、证据、风险、使用提示均保留；既有追问输入在内容底部。版本、可传递视图、运行记录及归档仍在“更多”。没有新增匹配追问能力或模拟流式输出 / 思考过程 / 进度。
- 资源中心宽布局，1366px 桌面主区 1056px、1920px 主区上限 1280px。紧凑筛选、三列卡片；小屏两列 / 单列。课程 / 实验的岗位、专区和层级，以及案例两级分类不变。详情、发起跳转及案例发展入口保留。
- 新视觉作用域限定为 `/`、`/tasks/{id}`、`/resources` 及其现有详情页。其他页面和管理后台不启用新主题。共享任务展示组件增加的纯布局 class / wrapper 不改变后台业务行为。

## 截图

[可切换页面、尺寸、首屏 / 完整页的前后对比](../../artifacts/coze-ui/review.html)。共 84 张原始 PNG：7 个页面状态 × 3 个尺寸 × 前后 × 首屏 / 全页；SHA-256 清单见 [screenshot-manifest.json](../../artifacts/coze-ui/screenshot-manifest.json)。

| 页面 | 改版前 1366 | 改版后 1366 |
|---|---|---|
| 新任务 · 资源匹配 | [前](../../artifacts/coze-ui/before/01-new-match-1366-viewport.png) | [后](../../artifacts/coze-ui/after/01-new-match-1366-viewport.png) |
| 新任务 · 能力发展 | [前](../../artifacts/coze-ui/before/02-new-development-1366-viewport.png) | [后](../../artifacts/coze-ui/after/02-new-development-1366-viewport.png) |
| 任务详情 · 能力发展 | [前](../../artifacts/coze-ui/before/03-development-detail-1366.png) | [后](../../artifacts/coze-ui/after/03-development-detail-1366.png) |
| 任务详情 · 资源匹配 | [前](../../artifacts/coze-ui/before/04-match-detail-1366.png) | [后](../../artifacts/coze-ui/after/04-match-detail-1366.png) |
| 资源中心 · 课程 | [前](../../artifacts/coze-ui/before/05-resources-course-1366-viewport.png) | [后](../../artifacts/coze-ui/after/05-resources-course-1366-viewport.png) |
| 资源中心 · 实验 | [前](../../artifacts/coze-ui/before/05-resources-lab-1366-viewport.png) | [后](../../artifacts/coze-ui/after/05-resources-lab-1366-viewport.png) |
| 资源中心 · 案例 | [前](../../artifacts/coze-ui/before/05-resources-case-1366-viewport.png) | [后](../../artifacts/coze-ui/after/05-resources-case-1366-viewport.png) |

截图在应用改动前完成留存；全部为浏览器合成夹具，不含真实伙伴资料或身份 Key，并配置身份字段遮罩。改版前任务侧栏简化夹具缺少当前选中任务的日期，出现 `Invalid Date`；后续补齐了夹具元数据，未因此修改产品日期或任务逻辑。首页和资源对比数据不受影响。

## 实际验证

| 验证 | 结果 |
|---|---|
| 改版前 `coze-ui.spec.ts`（capture phase=before） | 3 PASS，完成原界面截图 |
| `npm --prefix frontend run typecheck` | PASS |
| `npm --prefix frontend run build` | PASS；Next.js 15.5.19，31 个静态页生成完成 |
| 最终 `coze-ui.spec.ts` | 3 PASS / 0 FAIL / 0 SKIP，86.5 秒 |
| `task-failure.spec.ts` + `unified-answer.spec.ts` | 14 PASS，保留有效建议、重试、丢失响应、错误脱敏与资源引用顺序等现有回归通过 |
| `git diff --check` | PASS |
| 业务逻辑对比 | 与基线比对 4 个涉及页面 / 组件的 21 个异步函数体，全部原样保留 |

相关测试使用现有 `scripts/run_postgres_validation.py browser` 及新增 `frontend/playwright.coze.config.ts`，专用本机 PostgreSQL 验证库和临时 schema；私有连接由现有 `validation-environment.json` 注入进程，不打印。页面业务请求由合成夹具拦截，不调用模型，不写运行库。不是供应商集成测试或真实业务验收。

最终视觉用例覆盖 1366×768、1920×1080、390×844；21 个页面状态横向溢出检查全通过。另实际点击 / 键盘验证：Tab、伙伴选择、画像展开、发展提交、追问提交及正文、更多 / 历史版本 / 运行记录、课程岗位 / 专区 / 层级 / 搜索、资源详情、外链跳转、案例分类 / 详情 / 发展入口、匹配提交、场景展开 / 换一批、窄屏导航、键盘焦点和减少动画。发送请求的伙伴 ID、方向、当前版本 ID 均断言保留。页面脚本异常及未处理接口请求均为 0。

首轮新增用例存在两个测试问题：能力发展 Tab 同名定位不唯一；伙伴选择后的路由切换未等待完成。均已修正测试定位 / 等待，无业务流程改动。截图审查发现资源搜索按钮被挤成两行，已修正 CSS 最小宽度并通过最终截图与交互回归。14 项现有回归先通过，随后这三项视觉交互用例在最终修正后通过，未声称全量套件通过。

## 预览与待确认

原本的开发服务、Caddy 已通过 `enablement-dev.sh` 暂停，并在浏览器测试结束、生产构建结束后恢复。没有 build / dev / Playwright 同时写 `.next`。启动脚本提示文本仍含 `main`，实际工作分支是 `feature/coze-ui`，没有因此改运行脚本。

已显式使用现有根 CA 验证 HTTPS（未关闭证书校验）：`/api/health`、`/`、`/?mode=development`、`/resources` 均返回 200，三项原服务运行正常。仅取页面 HTML，不执行浏览器身份创建。

预览入口沿用私有配置中的 `https://172.21.208.223`；新任务模式为 `/?mode=development`，资源为 `/resources`。已有用户继续使用原浏览器 / 身份 Key；未进行身份创建、清库或恢复历史数据。截图中的 `coze-plan` / `coze-match` 是浏览器夹具 ID，不存在于运行库，任务详情视觉请看对比图，实际预览可打开自己的已有任务。

- 待用户确认本轮视觉，再覆盖其他页面及管理后台。
- 仅 WSL Chromium 浏览器布局验证；Windows 浏览器与 ARM 未实测，本轮未部署 ARM。
- 未运行全量后端 / 全量浏览器 / 真实模型测试。工程通过不替代业务验收。
- 原字体方案继续生效：Latin / 数字本地 Huawei Sans，中文系统 fallback；跨系统字形仍可能不同。
