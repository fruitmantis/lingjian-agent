# 卡片悬停与按下反馈（2026-09-28）

用户提供 `PixPin_2026-09-28_20-48-59.mp4`，并明确选择“先统一悬停和按下反馈，保留现有详情页”。继续在 `feature/coze-ui` 上保留既有未提交改动。

## 参考与实施

观看 4.46 秒录屏，并在已登录的 Windows Edge / www.coze.cn「数据集」卡片上读取默认、悬停、按下 CSS：默认白色，悬停/按下使用同一浅灰背景，150ms 颜色过渡；transform 为 none、box-shadow 为 none，卡片坐标和尺寸不变。仅查看页面，没有点击“添加”或提交任何内容。实测数据见 `artifacts/card-interaction/coze-reference.json`。

伴飞的 shared `ui-system.css` 统一以下规则：

- 悬停和按下为 `--bg-hover`（#F4F4F3），150ms 背景过渡；不抬升、不缩放，不加重阴影。
- 保留已确认的 1px 卡片边框和静态阴影，以及现有字号、颜色、卡片尺寸与内边距。
- 鼠标点击不再用 `:focus-within` 留下红色外圈。键盘通过 `:focus-visible` / `:has(:focus-visible)` 保留清晰的深灰焦点提示。
- 伙伴、场景、案例卡片继续使用原生链接；课程和实验使用同样的链接伪元素补齐整卡点击范围，目的路由不变。没有新增事件代理、嵌套交互控件或详情弹层。
- `prefers-reduced-motion: reduce` 下无过渡动画。不模仿录屏中的系统忙碌光标或伪造加载过程。

清理 `globals.css` 中旧的导航卡片 lift/focus-within 和伙伴专用阴影，以及 `coze-workspace.css` 中重复的资源卡片 hover 覆盖。没有修改业务 TSX、接口、数据库、模型或详情展示流程。

## 实测结果

- 六类卡片（伙伴、场景、课程、实验、案例、首页场景）× 默认/悬停/按下/点击后/移开/键盘焦点，共 36 个状态：通过。无位移、无尺寸变化，内容与原静态边框一致；鼠标无焦点外圈，键盘有可见轮廓。
- 整卡空白处点击确实命中原链接；减少动画偏好通过。测试取消对应的临时导航以观察点击后的焦点，不改应用事件代码。
- 现有 `ui-system.spec.ts` 两个测试（1366×768、1920×1080）均通过，覆盖共享卡片、原详情跳转及后台控件。断言同步为浅灰背景、静态阴影、指针/键盘焦点区分与整卡点击。`coze-ui.spec.ts` 的键盘焦点步骤相应修正，本轮未重跑该完整业务回放文件。
- Windows Edge 154 / 1366×768 / 100% 缩放：伙伴、场景、课程的实际页面离线快照分别检查修改前后状态，通过。此项不是 Windows HTTPS 证书验证。对照页 `artifacts/card-interaction/review.html` 已打开。
- `npm run typecheck`、`BANFEI_BUILD_CPUS=2 npm run build`、`git diff --check` 通过。构建前核对本项目 PID 并停服，构建后按既有配置恢复，不并发写 `.next`。
- 测试所有 API 都由合成响应拦截，0 写请求、0 模型调用、0 页面脚本错误；不访问业务库。

证据：`artifacts/card-interaction/before-results.json`、`after-results.json`、`edge-results.json`、`ui-test-results.json`，以及对应状态截图。截图使用合成数据，不含身份 Key。未提交、推送、合并或部署。
