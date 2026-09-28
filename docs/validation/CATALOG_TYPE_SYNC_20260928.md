# 伙伴洞察与场景广场卡片字号补齐

用户确认资源中心卡片后，指出伙伴洞察与场景广场未同步。本次继续保留 `feature/coze-ui` 的已有未提交修改，只修改两个应用样式文件：

- `frontend/app/ui-system.css`：既有目录卡片统一读取 catalog token，标题 14px/20px、500，说明 13px/20px、400，标签、状态和底部元信息 12px/18px、400。覆盖资源中心、伙伴洞察、场景广场，以及首页复用的场景卡片。
- `frontend/app/coze-workspace.css`：删除资源卡片独占的字号覆盖，保留颜色与其他外观。管理资料卡片和长篇正文保持原字号。

没有改 TSX、接口、业务内容、筛选与跳转逻辑；没有修改字体组合、颜色、边框、内边距或布局规则。

## 验证

- WSL Chromium：上述 4 个卡片入口 × 1366×768、1920×1080、390×844，共 12 个页面状态前后检查。标题/正文/标签的实际字号、行高、字重符合规范，无横向溢出；内容、颜色、边框、内边距等采样属性前后相同。
- 伙伴搜索、场景分类与关键词筛选通过；伙伴详情、场景入口链接目标保留。所有 API 在浏览器中拦截为合成响应，仅有 GET；不写运行库、不调用模型，0 页面脚本错误、0 字体网络请求。
- Windows Edge 154：两页使用相同实际 DOM/CSS 离线快照和合成内容，在 1366×768、100% 缩放下截图。CDP 确认实际中文为 Microsoft YaHei，标题 14/20/500、正文 13/20/400；卡片内容、边框和内边距相同。该检查不代表 Windows HTTPS 已验证。
- `npm run typecheck` 通过；`BANFEI_BUILD_CPUS=2 npm run build` 通过，31 个静态页面。构建前核对并停止本项目服务，完成后恢复，未并发写 `.next`。
- `git diff --check` 通过。未 commit、push、合并或部署。

对照入口：`artifacts/catalog-type-sync/review.html`。机器结果：`before-results.json`、`after-results.json`、`edge-results.json`；资源中心截图一致性见 `resource-regression.json`。截图不包含真实账号或身份 Key。
