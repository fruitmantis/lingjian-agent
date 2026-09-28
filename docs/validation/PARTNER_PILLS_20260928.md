# 伙伴标签与目录细边框（2026-09-28）

在 `feature/coze-ui` 上继续，基线 HEAD 为 `9296aecf105b81eb550c5cf6c52ae46c69fa849b`；保留此前全部未提交修改。本轮依据用户提供的三张截图，以及追加的“场景广场、伙伴洞察、资源中心都按此方向修改”。

## 修改范围

- 新增纯展示组件 `frontend/components/partner-tag-list.tsx`，伙伴列表和详情能力概览复用。能力、行业和区域按现有分隔符展示为独立药丸，保留顺序、重复项、英文内部空格和斜杠。空值保留原提示；长标签完整换行，不截断，不增加折叠或筛选功能。
- `frontend/app/ui-system.css` 共用一套药丸样式，覆盖伙伴标签、场景标签、资源课程/实验岗位专区和案例分类。12px/18px/400、3px 9px 内边距、6px 间隔、999px 圆角、浅灰底；悬停/按下时药丸底色随卡片略加深。状态和风险语义色保留。
- `frontend/app/globals.css` 中卡片边框从 1px #D4D4D0 调整为共享 0.5px #E4E4E7。`ui-system.css`、`coze-workspace.css`、资料管理及附件预览两个 CSS Module 中既有中性卡片/面板读取同一宽度 token。控件、分割线、风险边框继续使用各自 token。
- 移除 `coze-workspace.css` 单独覆盖资源标签的规则。字体组合、正文和标题字号、布局、字段、接口、登录、权限、业务状态、数据库和模型配置未改；只改变标签展示及共享中性边框。

## 实际验证

1. `npm run typecheck`：通过。
2. `BANFEI_BUILD_CPUS=2 npm run build`：通过，31 个静态页面生成完成。先核对服务 PID 和归属，再用 `enablement-dev.sh stop` 停服，构建后用 `start` 恢复；没有与 dev 并行写 `.next`。
3. Playwright：5 项通过（40.3 秒）。新增 `partner-tags.spec.ts` 在 1366×768、1920×1080、390×844 验证分隔符、重复值、英文空格、TCP/IP、长标签、空提示、无横向溢出、搜索与点击药丸位置后原详情跳转；详情保留待确认分类提示。原 `ui-system.spec.ts` 两项覆盖场景、伙伴、课程、实验、案例卡片，悬停/按下/键盘反馈及后台伙伴、模型、报表控件。
4. 修改前后分别以相同合成内容捕获伙伴列表、伙伴详情、场景广场、资源中心；三个窗口共 12 组视图，无横向页面溢出、页面脚本错误或字体网络请求。全部 API 拦截返回合成响应，没有运行库读写、外部字体或业务模型调用。
5. Windows Edge 154.0.4258.37：1366×768、100% 浏览器缩放，等待 `document.fonts.ready` 后捕获四页前后单屏及完整卡片局部。药丸样式一致；DPR 1、2 均实测 0.5px 卡片边框。当前 WSL Chromium 的 DPR 1 将其对齐为 1px，颜色仍为 #E4E4E7，不宣称所有浏览器都能显示半个设备像素。
6. Windows 对照使用实际页面 DOM/CSS 的离线快照，不是 Windows HTTPS、React 交互或 ARM 验证。页面交互由上述 WSL 隔离 UI 测试完成；未关闭 TLS 校验。
7. `git diff --check`：通过。无 commit、push、合并或部署。

首次新测试对非交互 `li` 直接使用 locator.click，被原整卡链接的伪元素拦截而超时；已改为在药丸实际坐标点击并断言原详情路由，随后 5 项全部通过。应用没有新增点击事件或修改跳转行为。

## 证据

- `artifacts/partner-pills/review.html`：本机 Edge 对照页，可切换伙伴洞察、伙伴详情、场景广场、资源中心，以及单屏/完整卡片和修改前/后。
- `artifacts/partner-pills/before-results.json`、`after-results.json`：WSL 三窗口截图与 API 拦截记录。
- `artifacts/partner-pills/edge-results.json`：Edge 实际边框、药丸与缩放信息。
- `artifacts/partner-pills/ui-test-results.json`：5 项 UI 回归结果。
- 构建记录 `/tmp/banfei-partner-pills/build.log`；所有截图只包含合成数据，没有身份 Key。
