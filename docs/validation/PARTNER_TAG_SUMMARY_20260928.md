# 列表能力标签单行汇总（2026-09-28）

用户明确修正此前完整换行方案：列表超过一行的能力标签合并为数量，进入详情再查看全部。继续在 `feature/coze-ui`，保留此前未提交修改，无 commit、push、合并或部署。

## 实施

- `frontend/components/partner-tag-list.tsx` 新增 `compact` 展示模式；按实际字体、标签宽度、间隔及计数药丸宽度保留一行原序前缀，剩余项显示“+N 个能力标签”。全部能放下时不显示计数；第一个标签本身过长时只显示汇总。
- `frontend/app/partners/page.tsx` 仅对列表能力标签启用该模式。行业/区域维持原样，伙伴详情仍完整展示标签。
- `frontend/app/ui-system.css` 给紧凑模式固定单行高度 24px。隐藏标签保留可测量宽度，视觉及辅助技术均隐藏；`ResizeObserver` 和字体加载完成事件触发重算。
- 汇总药丸沿用整卡原生详情链接，不增加行内展开按钮。搜索继续使用完整原始字段，不改变字段内容、顺序、重复项、数据或接口。

## 验证

- `npm run typecheck`、`BANFEI_BUILD_CPUS=2 npm run build`、`git diff --check` 通过。构建生成 31 个静态页面，先停已核验服务，再构建，之后恢复；没有并发写 `.next`。
- Playwright 5 项通过（41.1 秒）：三个窗口 1366×768、1920×1080、390×844 检查单行与准确剩余数、无溢出、少量标签无计数、单个长标签汇总、空值提示、容器缩小和恢复时重新计算、隐藏标签可搜索，以及点击计数进入详情后完整显示。其余两项复核原共享目录、交互和后台控件。
- 同一批 30 个能力标签的合成内容，WSL Chromium 前后各 6 个视图（列表/详情 × 三窗口）；Windows Edge 100% 缩放运行实际 React 组件，同样检查三窗口中的单行与准确计数，以及详情完整展示，0 页面脚本错误。截图等待字体加载完成，无外部字体请求。
- Windows 读取前端资源时，测试请求通过 Node HTTPS 并显式信任项目现有根 CA，未关闭证书校验；所有业务 API 由浏览器拦截返回合成响应。该项验证 Edge 渲染/组件行为，不宣称已验证 Windows 浏览器原生 HTTPS 信任配置。修改前 Edge 对照使用同一内容的静态 DOM/CSS 快照。
- 0 业务模型调用，0 运行库写操作，截图无身份 Key。

证据：`artifacts/partner-tag-summary/review.html`、`before-results.json`、`after-results.json`、`edge-after-results.json`、`ui-test-results.json` 及对应单屏/卡片局部截图；构建日志在 `/tmp/banfei-partner-tag-summary/build.log`。

## 后续：行业与区域同步

用户追加要求将列表“行业经验 / 覆盖区域”简化为“行业 / 区域”，并与能力标签形式一致。`frontend/app/partners/page.tsx` 两个字段复用已有 `compact` 模式，超出一行分别显示“+N 个行业 / 区域”；不改变详情全部展示、底层字段或搜索行为，没有新增 CSS 或计数算法。

- typecheck、build（31 个静态页面）、`git diff --check` 通过。构建与开发服务串行执行，完成后恢复服务。
- 更新既有 `partner-tags.spec.ts` 的合成行业/区域多标签及断言，1366×768、1920×1080、390×844 共 3 项通过（7.2 秒），核验名称、单行、准确剩余数、无溢出和详情完整列表；所有业务 API 全量拦截，无运行库写入、无模型调用。
- 修改前后各 6 个 WSL Chromium 视图（列表/详情 × 三窗口），使用相同合成内容并等待字体加载完成，0 页面脚本错误和外部字体请求。证据位于 `artifacts/partner-fields/`，测试结果 `ui-test-results.json`，构建日志 `/tmp/banfei-partner-fields/build.log`。
- 本次 Windows Edge 调试窗口未运行，未重复 Windows 验证，不将上述 Chromium 结果当作 Windows 结果。
- 保留 `feature/coze-ui` 及全部既有未提交改动，无 commit、push、合并或部署。
