> **设计参考 / 历史取证。** 视觉与字体原则继续适用；报告中的分支、端口、数据库、品牌更名前名称及测试数字仅记录当时状态。当前产品为伴飞 Agent，环境与运行规范以 [README](../../README.md) 为准。

# 华为云 Typography 收口

结论：**READY FOR TYPOGRAPHY REVIEW**。

字体取证起点为 `d331941`。下文测试只记录该次 Typography 收口；当前 main 与环境见 README，不能用这里的历史结论替代最新回归。

## 官网取证与已确认边界

实际访问 [华为云中国站](https://www.huaweicloud.com/)，使用 Chromium、Network、CSS、document.fonts 和 CDP `CSS.getPlatformFontsForNode`，抽样顶部导航、标题、正文、产品、Tab、按钮、搜索框及英文/数字。完整数据见 [来源清单](HUAWEI_CLOUD_FONT_SOURCES.md) 和 [浏览器证据](../ui/huawei-cloud-font-evidence.json)。

Computed stack 以 `-apple-system, HuaweiSans, Helvetica Neue, Helvetica, Arial` 开始，随后为官网中文系统回退字体。**computed 候选列表不等同于实际字体**：本环境中文正文/标题实际分别为 MicrosoftYaHei / MicrosoftYaHei-Bold（系统字体），英文与数字实际为 HuaweiSans / HuaweiSans-Bold（Web Font）。

官网 UI 字体只有 400 / 700 两个静态 face；600 标题映射到 Bold，不存在独立600文件。两个字体均不含CJK汉字，没有 variable axis 或 unicode-range 分片。用户已确认“与华为云官网方案保持一致”：**中文沿用系统 fallback，英文/数字本地加载官方字体**。不声称中文完全不依赖系统预装字体。

## 官方文件与本地使用

官方下载源为官网实际 CSS `https://portal.hc-cdn.com/cnpm-baseui/3.0.18/theme-token.css` 中列出的同版本 WOFF2。官网 Chromium 因 src 顺序实际请求 TTF；已比对其与 WOFF2 字体版本、字重和字符覆盖。本地按要求优先 WOFF2，未使用第三方来源。

| 文件（`frontend/public/fonts/huawei-cloud/`） | 字重 | 大小 | SHA-256 |
| --- | --- | --- | --- |
| huawei-sans-regular.woff2 | 400 | 35,452 bytes | `6b93fc7b7bf4ebfc6fe2474c049d40a0c435a30d9b36c31a59f4b9af9d687b72` |
| huawei-sans-bold.woff2 | 700 | 35,404 bytes | `3b821b178c999c9e8ca255e87a321751f30789c84de77a233a2935dd5854f47d` |

完整 URL、下载时间、style、unicode-range 与本地映射在来源清单和 `docs/ui/huawei-cloud-font-manifest.json`。字体二进制通过仓库本地 `info/exclude` 忽略，未加入 Git；换机器执行 `python3 scripts/fetch_huawei_cloud_fonts.py`。脚本验证 HTTP、Content-Type、WOFF2 格式/长度和固定 SHA-256，失败即报错；`--check` 完全离线。

`@font-face` 使用项目别名 `HuaweiCloudUI`，400/700 normal、`font-display:swap`，仅引用 `/fonts/huawei-cloud/`，无 `local()`、无 CDN hotlink。

最终 UI stack：

```css
"HuaweiCloudUI", "Helvetica Neue", Helvetica, Arial, "PingFang SC",
"Hiragino Sans GB", STHeiti, "Microsoft YaHei", "Microsoft JhengHei", SimSun, sans-serif
```

`--font-sans`、`--font-heading`、`--font-body` 统一应用；原 Logo 字标保留独立 `--font-logo`，不重新绘制。页面标题26px、二级18px、区块16px、正文/控件14px、辅助12px；正文约22px行高，标题1.5。正文/按钮400、标题/选中Tab700；统一文字间距及表格/输入控件字体。未照搬官网54px营销Hero。

## 实际加载与视觉验证

8个关键页面 × 1366×768 / 1920×1080，共16张合成数据截图，见 [清单](../../artifacts/huawei-typography/screenshot-manifest.json)。覆盖新任务两个模式、发展建议详情、资源中心、场景广场、伙伴洞察、全部任务、管理后台。

每页同时检查实际控件和 CDP Rendered Fonts；52个英文字母、10个数字在400/700均由本地自定义 Huawei Sans 渲染，20个指定汉字由系统中文字体渲染。两份字体当时均从应用自身地址返回200，document.fonts均loaded。测试禁用缓存、拦截所有非本机网络，官网字体CDN不可访问时仍通过；无 Windows Fonts 目录依赖来提供 Huawei Sans。

16组页面检查未见横向溢出；截图抽查新任务、详情和资源列表的标题、输入框、按钮、长文本与对齐正常。Next.js 开发调试浮层使用独立 shadow DOM，不属于业务 UI，不将其字体误判成业务控件。

## 历史验证结果（不是当前 HEAD 的重新执行）

| 命令 | 结果 |
| --- | --- |
| `python3 -m py_compile scripts/fetch_huawei_cloud_fonts.py` | PASS |
| `python3 scripts/fetch_huawei_cloud_fonts.py --check` | 2份字体校验PASS |
| `python3 -m unittest discover -s scripts/tests -p test_fetch_huawei_cloud_fonts.py -v` | 5 passed |
| `npm run typecheck`（frontend） | PASS |
| `npm run build`（frontend） | PASS |
| `npm run test:e2e -- huawei-visual.spec.ts` | 2 passed |
| `npm run test:e2e`（frontend全量） | 62 passed，0 failed，0 skipped |
| backend pytest | NOT RUN：未修改后端或前后端契约 |

测试使用 `/tmp/lingjian-enablement-e2e/` 数据库/上传目录及本地mock；旧版和人工开发数据库不作为测试库。原始运行日志留在 `/tmp`，不提交。命令耗时、源码hash、字体CDP及截图证据位于 `artifacts/huawei-typography/`。

## 环境与改动范围

当前应用使用 main / 3000 / 8000 / PostgreSQL，详见 [README](../../README.md)。本节只说明字体改动范围，不提供历史环境启动指令。

产品代码只修改 `frontend/app/globals.css` 的 Typography。其余改动为字体下载工具、测试、来源清单和证据；未修改业务TSX逻辑、API、schema、模型配置、权限、Task/Plan/Run/Version、路由或信息架构。颜色、华为红、Logo资产及导航布局不变。

该次字体验证没有调用真实模型；当前日常业务已使用获授权的真实模型。

## 已知边界

- 中文与官网一样依赖可用系统中文字体，不保证各操作系统中文逐像素一致；这是用户已确认的处理方式。
- 字体二进制不随Git分发；新环境必须运行拉取脚本或使用已校验的本地资产，离线部署前需准备文件。本轮不部署。
- 工程与浏览器验证完成，跨平台字体观感仍需按目标机器检查，不声称中文逐像素一致。
