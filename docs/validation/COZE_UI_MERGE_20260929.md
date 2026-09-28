# Coze UI 合并验证（2026-09-29）

用户确认本轮改版，授权提交 `feature/coze-ui`、合并回本地 `main`，验证通过后推送 `origin main`；不部署。

## 提交范围与边界

- 源分支开发基线：`9296aecf105b81eb550c5cf6c52ae46c69fa849b`。提交共享样式、全站外壳、卡片/标签/详情入口、伙伴三维筛选及 Edge 鼠标交互修复、后台标题栏对齐、相关测试和设计记录。
- Windows 字体为 Segoe UI / Microsoft YaHei，其他平台使用系统回退；正文与控件 400、标题 500，Logo 保留。Noto Sans SC 试验资产、来源校验值及 OFL 许可证随本轮保存，当前应用不注册或请求它；不包含 Windows 系统字体。
- 后端、接口、数据库、登录权限、模型配置/提示词和任务版本机制均未改动。伙伴筛选只操作接口已允许读取的数据。
- 原始参考截图及本轮浏览器证据保留本地，按明确目录加入 Git 忽略，避免上传账户/任务信息和大量生成文件。历史文档中的 `artifacts/` 链接指向本机证据，不保证远端仓库可访问；历史通过数字与“未提交”描述保留其时间边界。
- 全站及字体回归支持指定 `/tmp` 证据目录。历史正文对比改为显式提供 `COZE_ALL_BASELINE_DIR` / `COZE_POLISH_BASELINE_DIR`；指定后仍严格比对，未指定时执行当前布局、字体、交互和请求边界断言，不依赖未提交的旧截图。统一 UI 子集纳入伙伴筛选和标签用例。

## 首次合并验证（已按后续授权退出）

以下记录首次验证的失败现场。用户后续确认是测试误判，授权退出合并、仅修字体测试并重新验证；实际最新结果见下一节。

- 源分支提交：`973cf22966db19a703e380bf8bac2307e4116dd5`。
- `git fetch origin` 成功；本地 `main` 与 `origin/main` 一致，均为 `9296aecf105b81eb550c5cf6c52ae46c69fa849b`，无须快进。此值为合并前 main。
- 工作区干净后切换到 `main`，执行 `git merge --no-ff --no-commit feature/coze-ui`，无冲突。**因下列测试失败，保留合并现场，未提交合并、未 push、未部署；main HEAD 仍为合并前 commit。**
- `npm run typecheck`：通过。
- `BANFEI_BUILD_CPUS=2 npm run build`：通过，31/31 静态页面生成；日志 `/tmp/banfei-coze-merge-build.log`。
- 既有私有验证配置加载到测试进程后执行 `.venv/bin/python scripts/run_postgres_validation.py browser --config=playwright.unified-ui.config.ts`：**39 通过、3 失败，约 7 分钟，退出码 1**。使用专用 PostgreSQL 临时 schema，上传及诊断只在 `/tmp`；不写运行库，不调用业务模型。开发服务、build、Playwright 顺序执行，未并行写 `.next`。
- 通过范围包括首页、两类任务详情、资源中心、后台等 33 个路由及 5 个弹层/展开状态，1366×768、1920×1080、390×844，100% 缩放；另有三维筛选、标签文字及行留白点击、键盘、多次筛选、标签汇总、卡片交互、后台筛选、反馈和失败提示用例。查看了首页、任务正文、资源中心和后台的桌面/窄屏截图，未见明显遮挡。此次浏览器是 WSL Chromium，未复测 Windows Edge 或 ARM。
- 3 个失败均为 `coze-global-controls.spec.ts` 在三个尺寸调用 `font-verification.ts:29` 时，断言 `document.fonts` 应为空，实际包含 4 条未加载的 Next.js 开发工具字体（`__nextjs-Geist` / `__nextjs-Geist Mono`）。已在当前安装的 `next/dist/compiled/next-devtools/index.js` 核对其来源。该断言未区分开发工具字体和应用字体；尚未修改，后续字体/弹窗断言因此未执行，不能报告整套验证通过。
- 完整结果与新截图：`/tmp/banfei-coze-merge-20260929/ui-results.json`、`ui.log`、`all-pages/after/`。失败截图和 trace 保留在 Git 忽略的 `frontend/test-results/`。旧 `artifacts/` 文件未覆盖。

## 字体测试修复与分支复验

- 先将未提交验证报告和补丁保存到 `/tmp/banfei-coze-final-20260929/`，再执行 `git merge --abort`，核实 main 仍为 `9296aecf105b81eb550c5cf6c52ae46c69fa849b`，切回已有 `feature/coze-ui`。未 stash、重写历史或新建分支/worktree，旧报告已恢复到本文件。
- 唯一代码修改为 `frontend/e2e/font-verification.ts`：在字体注册断言中排除 Next.js DevTools 的 `__nextjs-*` family，仍将全部注册字体、被排除项和应用字体分开留证。增加 request 事件检查，字体请求即使被阻断或失败也不能漏过；原有响应、实际字形和共享控件检查保留。产品 CSS、字体配置、UI、后端和数据库均未调整。
- `npm run typecheck`、`BANFEI_BUILD_CPUS=2 npm run build` 均通过，31/31 静态页面。
- 完整统一 UI：**42/42 通过，0 失败、0 跳过、0 flaky，551.7 秒**。命令仍为专用 PostgreSQL 验证入口加 `--config=playwright.unified-ui.config.ts`，UI 模式，无业务模型调用。1366×768、1920×1080、390×844 的共享字体证据均为应用注册 0、请求 0、响应 0，另记录 4 条 DevTools 注册。
- 独立临时合成页面的 3 项边界检查通过：只注册 DevTools 字体可通过；注册应用字体会失败；下载被阻断且随后删除的应用字体仍因 request 记录而失败。临时检查脚本对空白页面补齐绘制等待，并按实际断言内容识别预期失败；不改变项目测试逻辑。
- Windows Edge **154.0.4258.37** 有界面模式、DPR 2、强制 basic accessibility：三类筛选各执行方框、文字、行内空白、键盘切换，共 **12 次**；另检查 1366×768、1920×1080、390×844 弹层，无崩溃、页面错误、意外 API 请求或横向溢出，运行退出码 0。仅合成伙伴，全部业务 API 拦截。
- Windows 范围说明：独立 Edge 配置直接访问本机 HTTPS 首次报 `ERR_CERT_AUTHORITY_INVALID`，未改系统证书。随后沿用既有 Edge 隔离脚本的静态资源通道：Node HTTPS 显式信任项目公开 CA 并验证主机名，资源再交给 Edge 渲染；没有 ignoreHTTPSErrors、关闭证书/吊销检查或修改 Origin。此次证明 Windows Edge UI 交互通过，不代表 Windows 证书信任配置已通过，也未验证 ARM。
- 本轮证据根目录 `/tmp/banfei-coze-final-20260929/`：`feature-build.log`、`feature/ui-results.json`、`feature/all-pages/extra/fonts-*.json`、`font-guard-results.json`、`edge/result.json` 和 Edge 截图。旧失败报告仍留在 `/tmp/banfei-coze-merge-20260929/`，本轮测试重建了 Git 忽略的 `frontend/test-results/`，不再把它当作旧失败证据的长期副本。
