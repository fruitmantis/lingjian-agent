# 伙伴筛选精修与 Edge 崩溃排查（2026-09-28）

> 以下保留第一轮排查结果。后续已在 Windows 无障碍模式下复现并替换原生展开控件，用户确认原窗口鼠标勾选正常；最新结论与证据见 [Edge 原生崩溃修复](PARTNER_FILTER_EDGE_CRASH_20260928.md)。

## 用户反馈与处理

用户指出首版筛选区外观笨重，并反馈勾选标签会出现浏览器 `STATUS_BREAKPOINT`。已查看用户提供的截图：重复标题、长标签挤成两列，清除按钮继承了红色主按钮样式。

- 前台筛选使用 32px 紧凑入口，去掉重复标题和整排表单样式；选中数量以中性灰小标记显示。
- 下拉选项改成单列 13px 文字；清除为灰色文字操作，搜索框和清除固定在滚动选项外。窄屏菜单对齐筛选栏，不覆盖相邻入口。
- 复用现有多选组件的 `compact` 变体，后台仍使用原变体。
- 标签列表采用 memo/useMemo 保持未变化数据稳定，字体/宽度变化通过 requestAnimationFrame 合并测量；ResizeObserver 只对宽度变化重测，卸载时取消回调。
- 修复精修过程中发现的“清除后禁用当前焦点按钮导致 Escape 无法收起菜单”：清除按钮保持可聚焦，相关测试通过。

筛选组合规则、数据权限、详情入口和业务流程均保留，无后端或数据库变更。

## 崩溃排查边界

`STATUS_BREAKPOINT` 是用户提供的 Edge 标签页进程崩溃代码。原始崩溃未能稳定复现，不能把减小布局开销等同于已确定根因或已根治。

为补足首版仅少量合成数据的验证，使用 PostgreSQL 只读事务读取 178 家启用伙伴的能力、行业、区域组合。查询不包含伙伴名称、ID、资料正文、身份或凭据；测试使用生成的名称与 ID，原组合样本仅保存 `/tmp/banfei-partner-filters/anonymized-fixture.json`（0600）。浏览器所有业务 API 都由测试拦截，无运行库写入或模型调用。

- 修改前：WSL Chromium 与 Windows Edge 无头进程，对 63 种能力逐项勾选/取消，均未出现脚本错误或崩溃。
- 修改后：Windows Edge **154.0.4258.37 可见测试窗口**，DPR 1 与 DPR 2 各完成 63 种能力的勾选/取消（各 126 次，合计 252 次），无 pageerror、无 renderer crash。
- Windows 两种 DPI 都检查了 1366×768、1920×1080、390×844 截图及页面横向溢出；均正常。测试使用独立临时浏览器环境，不等同于用户原窗口的扩展、GPU 状态及完整环境。
- 前端资源由 Node HTTPS 使用项目根证书转发，未关闭证书校验；全部业务接口被拦截。
- 同一匿名样本第一次能力筛选的 WSL 测量：标签几何读取 **348 → 97**，ResizeObserver 创建 **14 → 0**。仅表示该测量样例的重复开销下降。
- 尝试读取 Windows 最近 Edge 应用错误事件的 PowerShell 脚本被本机签名执行策略阻止；未放宽策略、未读取内存转储，没有据此得出原生崩溃模块结论。

## 回归验证

- `npm run typecheck`：通过。
- Playwright：**11 passed，32.3 秒**，无跳过、无重试。伙伴组合筛选/加载失败 4 项、180 张合成卡片反复筛选 1 项、伙伴标签与详情导航 3 项、后台原筛选控件 3 项。
- `git diff --check`：通过。
- `BANFEI_BUILD_CPUS=2 npm run build`：通过，31 个静态页面生成完成。生产构建与预览恢复按本项目服务脚本串行执行，不与开发服务同时写 `.next`。

工作分支仍为 `feature/coze-ui`，既有修改保留；未 commit、push、合并或部署。

## 证据

- [Windows 新版筛选](../../artifacts/partner-filter-fix/edge-capabilities.png)
- [Windows 页面总览](../../artifacts/partner-filter-fix/edge-overview.png)
- [Windows DPR 1 结果](../../artifacts/partner-filter-fix/edge-result.json)
- [Windows DPR 2 结果](../../artifacts/partner-filter-fix/edge-dpr2/edge-result.json)
- [布局测量](../../artifacts/partner-filter-fix/measurement.json)
- [11 项回归报告](../../artifacts/partner-filter-fix/ui-test-results.json)
