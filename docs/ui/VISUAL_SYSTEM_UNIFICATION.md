# 全局视觉统一交付记录

2026-09-08。范围：视觉样式、公共控件及相关前端回归；不涉及业务架构。

## 当前代码与保护范围

- 工作目录：`/home/yuan/project/lingjian-agent-enablement`。
- 分支：`feature/partner-enablement-v1.1`；HEAD：`ad0cbf28e3616951f3c87871c0c999bd023d27fb`。
- 本轮未提交。开始时已有未提交的业务分类、注册、画像等修改，均保留；不将这些修改计为本轮成果。
- `main` 保持 `f79cbb29ec7b3ad70c88e618e3161211f211c06a`；未 merge、push、部署。
- 保持华为红、黑白灰、原 Logo、本地字体和原导航。全局品牌/字体 token 与修改前一致。
- 本轮没有修改后端、API、数据库 schema、模型配置或业务数据。
- 浏览器功能测试只使用 `/tmp/lingjian-enablement-e2e/app.db`；模型仅为本地 mock。REAL MODEL CALLS = 0。

## 统一规则

| 元素 | 最终规范 |
|---|---|
| 场景、课程、实验、案例、伙伴目录卡片 | 白底、无边框、8px 圆角、统一基础阴影；悬停上移 2px 并增强阴影 |
| 输入与阅读容器 | 同系列白色卡片，保持静止；内部用分割线和间距分层 |
| 表格与工具栏 | 更轻的阴影、统一表头/行距/分割线；宽表仅容器内滚动 |
| 卡片内容 | 标准内边距 24px；窄屏 20px；区块间距 24px |
| 表单 | 输入框和普通按钮 40px；表格内编辑和分页控件 32px；沿用华为红 focus |
| Tab | 文字式 Tab，44px 交互高度，选中深色文字与红色下划线 |
| 数字指标 | 对齐网格、28px 数字、13px 标签；保留错误/警告语义色 |
| 可访问性 | 保留键盘焦点、减少动画偏好；表格保存/取消增加可理解的名称 |

阴影统一使用 `--shadow-surface`、`--shadow-surface-hover`、`--shadow-data`、`--shadow-overlay`。没有新增品牌色。

## 页面覆盖

| 页面组 | 本轮处理 |
|---|---|
| 登录、注册、权限提示 | 白色浮层、控件与间距；注册入口和字段不变 |
| 开启新任务两个模式 | 统一输入容器；保留能力发展上下两张卡片和现有目标伙伴/方向字段 |
| 场景广场、伙伴洞察、资源中心 | 卡片阴影、字号、间距、悬停与键盘反馈一致；资源筛选更紧凑 |
| 伙伴详情、画像、资源详情 | 摘要与属性扁平排列，减少内部卡片嵌套 |
| 全部任务、匹配详情 | 表格、任务类型、时间和操作对齐；匹配证据区域采用分割线 |
| 能力发展建议 | 保留顾问式正文与自然语言调整；内部资源分段；版本/运行信息仍在二级操作 |
| 个人中心、用户详情 | 信息字段不再各自套灰色卡片 |
| 后台概览、需求画像、机会、报表 | 指标网格与表格统一；筛选功能不变 |
| 后台伙伴、资源、案例共享、标签、用户、模型、系统状态 | 原生输入框补齐样式、表内编辑尺寸统一、轻量状态行、宽表局部滚动 |

`/enablement` 与旧资源详情兼容路由继续保留，不新增工作台或导航。

## 主要文件

- `frontend/app/ui-system.css`：集中存放共用视觉规则。
- `frontend/app/globals.css`：收拢重复容器规则，保留原配色、字体和业务布局。
- `frontend/app/layout.tsx`：加载共用视觉样式。
- `frontend/app/page.tsx`：匹配结果纯展示结构和样式类。
- `frontend/components/admin-panels.tsx`、`admin-demand-panels.tsx`：控件、表格、指标与状态样式。
- `frontend/components/enablement-admin.tsx`、`enablement-admin.module.css`：资源后台表格与布局。
- `frontend/components/enablement-workspace.tsx`、`task-list.tsx`：筛选/分页/任务表格样式类。
- `frontend/e2e/ui-system.spec.ts`：共享卡片、控件、卡片标题及空白点击、键盘与减弱动画验证。
- `frontend/e2e/batch2-resilience.spec.ts`：保存按钮的可访问名称适配。

保留了原有匹配、自然语言 explain/revise、版本状态、确认、撤权、共享与权限流程。对比修改前快照：148 个事件处理器、30 个异步函数主体没有改写。

## 验证

| 命令 | 结果 |
|---|---|
| `npm --prefix frontend run test:e2e` | 全量 66 PASS / 0 FAIL / 0 SKIP，8.3 分钟 |
| `npm --prefix frontend run test:e2e -- ui-system.spec.ts business-taxonomy.spec.ts batch3-quality.spec.ts` | 全量通过后收尾报表网格/海外选项；定向 8 PASS / 0 FAIL，1.3 分钟 |
| `npm --prefix frontend run typecheck` | 最终代码 PASS |
| `npm --prefix frontend run build` | 最终代码 PASS |
| 相关文件 `git diff --check` | PASS |

首轮发现资源整卡点击层遮挡标题，以及表格输入框被通用高度覆盖，已分别修复 z-index 和 CSS 选择器优先级，并增加点击回归。首轮为 57 PASS / 3 FAIL / 6 未执行，不作为最终通过证据。

- 两种视口：1366×768、1920×1080。
- 额外只读页面检查：24 页面/状态 × 2 视口，48/48 无页面横向溢出、无页面脚本错误；无写请求。
- 全量浏览器同时回归登录/注册、用户隔离、匹配、任务、Advisor explain/revise、资源发布/撤权和后台业务。
- 未运行 backend pytest：本轮无后端及契约修改，前端全量浏览器已使用临时后端完成相关流程验证。
- 截图与机器证据位于 `artifacts/ui-unification/`。截图均来自临时或浏览器拦截的 synthetic 数据。

## 开发环境与人工复核

- 新版前端：http://localhost:3100；登录页 HTTP 200。
- 新版后端：http://localhost:8100/health，HTTP 200。
- 本地 mock：18180，health HTTP 200。
- 实际数据库：`/home/yuan/project/lingjian-agent-enablement/.isolation/runtime/dev/app.db`。
- 上传目录：同一 `dev` 目录内的 `uploads`；日志仍在新版 `.isolation/logs`。
- 新版前后端和 mock 已恢复并保持运行，未重建数据库、未调整数据、未创建账号。
- 旧版 3000/8000 原进程仍运行，旧版后端匿名 health HTTP 200。
- 旧数据库、新版开发数据库与原隔离快照库三者 SHA-256 均与开始时一致；均为独立路径，链接数为 1。
- 工作区保留既有及本轮未提交修改；没有创建分支或提交。

剩余限制：大列数后台表格允许容器内横向滚动；本轮没有改写既有的原生多选业务控件或其筛选语义。浏览器输出存在 Next.js `allowedDevOrigins` 后续版本提示，不影响本次验证，没有为此扩大框架升级范围。最终观感仍待用户人工确认。

READY FOR VISUAL REVIEW
