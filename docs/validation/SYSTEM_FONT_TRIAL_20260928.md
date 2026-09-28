# 系统字体与资源卡片字号验证（2026-09-28）

分支 `feature/coze-ui`，基线 HEAD `9296aecf105b81eb550c5cf6c52ae46c69fa849b`。沿用并保留所有已有未提交修改；未切换分支、提交、推送或部署。

## 实施范围

用户先要求只改字体组合和字重，随后明确追加“对比 Coze 卡片字号再优化”。本次仅改字体组合、字重，以及资源目录卡片的字号和对应行高；不改信息结构、内容、颜色、边框、圆角、间距、布局规则、业务逻辑或接口。

- Windows 英文/数字：Segoe UI；中文：Microsoft YaHei（微软雅黑）。macOS 和其他系统按现有系统字体回退。没有复制或打包系统字体，没有字体服务依赖；既有 Noto 文件和许可证保留，但不再注册或请求。
- 正文、说明、普通控件 400；页面和卡片标题 500；Logo 的独立字体与 700 字重保持原样。保留 `font-synthesis:none`。
- 资源中心课程/实验/案例共用目录卡片规则：标题 14px/20px，摘要 13px/20px，标签与元信息 12px/18px。长篇顾问正文原字号保留。

## Coze 实际页面对比

本机 Windows Edge 154.0.4258.37，已登录 `www.coze.cn` 的「扩展 → 技能」页面；非宣传页、非 code.coze.cn。读取实际元素 CSS，并用 CDP `CSS.getPlatformFontsForNode` 检查中文、英文和数字。

| 元素 | Coze 实测 | 伴飞修改前 | 伴飞最终版 |
|---|---|---|---|
| 卡片标题 | 14px/20px，500 | 17px/26px，600 | 14px/20px，500 |
| 卡片说明 | 13px/20px，400 | 16px/26px，400 | 13px/20px，400 |
| 小标签 | 11px/16.5px，500 | 13px/20px，400 | 12px/18px，400 |

Coze 数据集和技能包标题的实测结果一致；标签保留 12px 以兼顾伴飞业务分类名称的阅读。证据：`artifacts/system-font-trial/coze-cards.json`。未保存 Coze Cookie、Token 或会话正文。

## Windows 字体与截图验收

- Edge 独立窗口对本地 HTTPS 返回 `ERR_CERT_AUTHORITY_INVALID`。没有关闭证书验证或导入根证书；改用实际资源中心 DOM 和全部 CSS 的离线快照做字体及视觉验收。快照由当前前端加载合成数据后导出，不能当作 Windows HTTPS 或真实业务流程验证。
- 同一浏览器、同一 1366×768 视口、DPR=1；CDP `cssVisualViewport.zoom=1` 和 `visualViewport.scale=1`，等待 `document.fonts.ready` 后截图。调整前、中间字体版、最终字号版均保留。
- 实际可见标题、摘要和元信息及独立语言探针均验证：400 中文 MicrosoftYaHei、英文/数字 SegoeUI；500 中文仍 MicrosoftYaHei Regular、英文/数字 SegoeUI-Semibold。没有虚构中文 Medium，也没有合成粗体。
- 外部网络全部阻断仍能显示，最终字体网络请求 0。正文内容相同，无横向溢出；Logo 的全部采样样式和实际字体一致。颜色、边框、间距等非本次授权的采样样式一致。字体尺寸变化会自然改变换行与卡片实际高度，未改布局规则或限制内容。
- 前后单屏及卡片局部：`artifacts/system-font-trial/review.html`；详细证据 `before.json`、`font-only.json`、`after.json`。

## 工程与 UI 检查

- `npm run typecheck`：通过。
- `BANFEI_BUILD_CPUS=2 npm run build`：通过，31 个静态页面生成成功。构建前核对当前项目 PID 并停止开发服务，构建完成后恢复，未并发写 `.next`。
- WSL Chromium 资源中心 UI：标题 500、正文/控件 400，岗位/专区、层级、搜索操作通过；所有 API 均由浏览器合成响应拦截，0 字体请求、0 页面脚本错误。证据 `resource-ui.json`。没有连接测试数据库、运行库或模型；没有真实业务写操作。
- CSS 声明及组件源码对照：除字体、字重和资源卡片字号/行高外，其他声明及组件逻辑保持一致；`git diff --check` 通过。
- 本轮按用户要求只验收资源中心一页；不宣称重跑全站、真实模型、Windows HTTPS 或 ARM 验证。

## 修改文件

应用：`frontend/app/globals.css`（字体与字重 token）、`ui-system.css`、`coze-workspace.css`（共用控件与资源卡片）；组件中原显式字重同步调整：`material-files.module.css`、`opportunity-ui.module.css`、`recent-errors.module.css`、`admin-demand-panels.tsx`、`admin-panels.tsx`、`app/page.tsx`。这些组件没有结构或逻辑改动。

字体相关测试断言同步为系统字体：`e2e/font-verification.ts`、`coze-polish.spec.ts`、`coze-global-controls.spec.ts`。设计规范同步于 `docs/design/COZE_VISUAL_REFINEMENT_20260928.md`。既有修改和用户图片 `banfei.png`、`coze.png` 保留。
