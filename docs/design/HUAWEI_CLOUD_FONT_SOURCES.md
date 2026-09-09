> **设计参考 / 历史取证。** 视觉与字体原则继续适用；报告中的分支、端口、数据库、品牌更名前名称及测试数字仅记录当时状态。当前产品为伴飞 Agent，环境与运行规范以 [README](../../README.md) 为准。

# 华为云字体来源与浏览器取证

页面：<https://www.huaweicloud.com/>。实际访问时间：2026-09-07T14:38:58.353Z；Chromium 131.0.6778.33。
方法：Playwright Network、已加载 CSS、`document.fonts`、CDP `CSS.getPlatformFontsForNode`；访问首页、滚动加载与产品菜单，并分别检查中文/Latin/数字。

## 核心事实与已确认口径

官网 **HuaweiSans Web Font 只覆盖 Latin 等字符，不包含汉字**。本环境中文实际是系统 Microsoft YaHei，英文/数字是下载的 Huawei Sans。用户已确认“与华为云官网方案保持一致”：中文维持官网 fallback，不加入第三方中文字体、不从 Windows 目录复制字体。

官网 computed stack：

```css
-apple-system, HuaweiSans, "Helvetica Neue", Helvetica, Arial, "PingFang SC", "Hiragino Sans GB", STHeiti, "Microsoft YaHei", "Microsoft JhengHei", SimSun, sans-serif
```

## 样本 computed style / Rendered Fonts

| 类别 | 元素/类名标记 | size | weight | line-height | letter-spacing / style | 实际字体 |
| --- | --- | --- | --- | --- | --- | --- |
| 顶部导航 | `a`（顶部导航） | 14px | 400 | 22px | normal / normal | MicrosoftYaHei（系统） |
| 一级视觉标题（官网H5 Hero） | `h5.banner-title.banner-title-enter` | 54px | 700 | 80px | normal / normal | HuaweiSans-Bold（Web）, MicrosoftYaHei-Bold（系统） |
| 二级/区块标题 | `h2.por-section-title.hide-mb` | 40px | 600 | 60px | normal / normal | MicrosoftYaHei-Bold（系统） |
| 普通正文 | `p.event-desc` | 14px | 400 | 22px | normal / normal | HuaweiSans（Web）, MicrosoftYaHei（系统） |
| 产品名称 | `div.card-title.grey` | 24px | 700 | 36px | normal / normal | MicrosoftYaHei-Bold（系统） |
| 产品描述 | `p`（产品描述） | 16px | 400 | 24px | normal / normal | MicrosoftYaHei（系统） |
| 选中Tab | `a.customers-tab-item.active` | 18px | 700 | 28px | normal / normal | MicrosoftYaHei-Bold（系统） |
| Button/CTA | `a.por-btn.por-btn-default.por-btn-md-small.por-btn-primary` | 14px | 400 | 22px | normal / normal | MicrosoftYaHei（系统） |
| Input/Search | `input.search-default` | 14px | 400 | 16.1px | normal / normal | MicrosoftYaHei（系统） |
| 英文字符探针 | `p.probe-latin-400` | 14px | 400 | 21px | normal / normal | HuaweiSans（Web） |
| 数字字符探针 | `p.probe-digits-400` | 14px | 400 | 21px | normal / normal | HuaweiSans（Web） |

各行 font-family 均为上述官方 stack。Hero 是视觉一级标题但实际标签为 H5，不能把其 54px 直接用于业务系统；伴飞保持 26px 页面标题、18px 二级、16px 区块，正文/控件14px与约22px行高。官网600标题实际选到700 Bold文件；伴飞统一采用已存在的400/700字重，按钮400、选中Tab700。

## 官方 UI font-face 与格式选择

CSS：<https://portal.hc-cdn.com/cnpm-baseui/3.0.18/theme-token.css>。

两个规则均为 family=`HuaweiSans`，style=`normal`；weight分别400、700；未声明 unicode-range（CSS默认 `U+0-10FFFF`，不表示文件包含全部字符）；未声明 font-display（默认auto）。它们不是 variable font，没有CJK分片。

官网src按 EOT / SVG / TTF / WOFF / WOFF2列出，当前Chromium Network实际选择TTF；本地优先使用**同一官方CSS明确列出的同版本WOFF2**，未猜测URL。已下载TTF到临时取证目录做比对：两种格式均Version1.00、776glyph、721映射字符、相同400/700权重、0个CJK汉字。TTF不进入应用或Git。

| weight | 官方完整下载URL | 本地文件 | bytes | SHA-256 |
| --- | --- | --- | --- | --- |
| 400 | https://portal.hc-cdn.com/cnpm-baseui/3.0.18/style/core/fonts/HuaweiSans-Regular.woff2 | `frontend/public/fonts/huawei-cloud/huawei-sans-regular.woff2` | 35452 | `6b93fc7b7bf4ebfc6fe2474c049d40a0c435a30d9b36c31a59f4b9af9d687b72` |
| 700 | https://portal.hc-cdn.com/cnpm-baseui/3.0.18/style/core/fonts/HuaweiSans-Bold.woff2 | `frontend/public/fonts/huawei-cloud/huawei-sans-bold.woff2` | 35404 | `3b821b178c999c9e8ca255e87a321751f30789c84de77a233a2935dd5854f47d` |

下载时间（UTC）：400 2026-09-07T14:37:15.238227+00:00, 700 2026-09-07T14:37:15.238444+00:00。Content-Type为`binary/octet-stream`，已额外检查WOFF2魔数、完整长度、表数量及固定SHA-256，不把HTML错误页当字体。

原始实际Network TTF：

- https://portal.hc-cdn.com/cnpm-baseui/3.0.18/style/core/fonts/HuaweiSans-Regular.ttf
- https://portal.hc-cdn.com/cnpm-baseui/3.0.18/style/core/fonts/HuaweiSans-Bold.ttf

所有官方src规则、document.fonts和文件元数据见 [机器取证](../ui/huawei-cloud-font-evidence.json)。`por-icon`/`u-icon`属于官网图标字体，部分以data URL嵌入；`iconFont-product`/`iconFont-solution`本次为unloaded。它们不负责中英文字形，不下载，不替换伴飞现有SVG图标或Logo。

## 本地复现

```bash
python3 scripts/fetch_huawei_cloud_fonts.py
python3 scripts/fetch_huawei_cloud_fonts.py --check
python3 -m unittest discover -s scripts/tests -p test_fetch_huawei_cloud_fonts.py -v
```

仅允许manifest内已取证官方URL；HTTP/Content-Type/格式/size/hash不符立即失败。两个文件均验证成功后才替换本地文件。`--check`不联网。字体二进制通过仓库本地`info/exclude`忽略；换机器需运行下载脚本，不会自动调用CDN或第三方服务。

## 伴飞实际使用位置

`frontend/app/globals.css`以独立别名`HuaweiCloudUI`定义两个本地`@font-face`，只引用`/fonts/huawei-cloud/`，无`local()`、无远程font src。`font-display:swap`；没有虚构500/600字体文件。

`--font-sans` → `--font-heading` / `--font-body`，覆盖正文、标题、Tab、Button、Input、Textarea、Select、Option、Table。为确保本地Web Font优先，移除官网stack最前的`-apple-system`并将HuaweiSans替换为项目别名；其余fallback顺序保持官网一致。已恢复Logo的字标使用单独`--font-logo`保留上一版字形，Logo几何与颜色不变。

英文字母52个、数字10个：两个官方字体完整覆盖；测试中文20个：官方字体均不含对应glyph，按已确认口径落到系统中文字体。这是官网方案本身的边界，**不声称中文完全摆脱系统字体依赖**。
