# 伙伴筛选 Edge 原生崩溃修复（2026-09-28）

## 结论与范围

用户反馈 Microsoft Edge 在能力标签、行业、区域任一维度勾选后出现 `STATUS_BREAKPOINT`，并指出真实鼠标点击比自动点击更容易触发。最终将共享筛选器的原生 `details/summary` 替换为普通按钮控制的同级弹层后，**用户已在原来的 Edge 窗口刷新并确认真实鼠标勾选正常**。

这确定了应用侧的触发路径与有效规避方式；未解析 Edge 符号，不能断言具体的浏览器内部函数或上游缺陷编号。没有要求用户关闭无障碍功能、硬件加速或扩展，也没有清理身份、Cookie、缓存或变更浏览器设置。

本次只改前端展示组件、共享样式及回归测试。筛选规则、标准分类、数据来源、授权、业务接口与数据库保持原状。工作分支 `feature/coze-ui`，基线 `9296aecf105b81eb550c5cf6c52ae46c69fa849b`；既有未提交修改保留，未提交、推送、合并或部署。

## 定位证据

1. 原窗口多次崩溃均为 Edge `154.0.4258.37` / Chromium `154.0.8037.58`，renderer 进程 `msedge.dll`，异常 `0x80000003`，模块相对偏移 `0xd3a8c8c`。崩溃记录包含 `ax_mode = kNativeAPIs | kWebContents` 和 `device-scale-factor=2`。
2. 在独立 Windows Edge 测试窗口加入 `--force-renderer-accessibility=basic` 或 `complete` 后复现 renderer crash。此前普通自动化没有覆盖这个条件，因此先前通过的结果不足以证明修复。
3. 曾尝试分离卡片标签的测量与展示节点：DPR 1 的两种模式各完成 126 次操作，但用户反馈仍崩；DPR 2 再次复现。该优化不能单独解释或解决根因。
4. 隐藏整个结果列表仍在能力选项序号 9 崩溃；隐藏摘要计数仍在序号 3 崩溃。排除了“只是卡片太多”或“只是计数徽标”的解释。
5. 将原生展开控件换为普通按钮及同级弹层后，匹配原窗口的 basic 无障碍模式 + DPR 2，178 条匿名伙伴数据的 **63 个能力、12 个行业、40 个区域全部勾选/取消，230 次操作通过**，无 pageerror 或 renderer crash。用户的原窗口真实鼠标操作也确认恢复正常。

崩溃转储仅在本机读取限定元数据，未复制或上传原始转储。匿名测试夹具沿用此前只读取得的分类组合，姓名/ID 全部合成，夹具仅留在 `/tmp`。本轮浏览器测试拦截全部业务 API，无运行库写入、账号创建或模型调用；前端资源由 Node HTTPS 使用项目根证书验证后转发，未关闭证书验证。

## 修改

- `frontend/components/opportunity-ui.tsx`：共享多选组件使用按钮、`aria-expanded`、`aria-controls` 与条件弹层；保留原生复选框、多选、选项搜索、清除、Escape 回焦和焦点移出关闭。
- `frontend/components/opportunity-ui.module.css`、`frontend/app/ui-system.css`：将原 summary 样式绑定到按钮，保留尺寸、颜色和窄屏弹层定位；后台仍使用原尺寸变体。
- `frontend/components/partner-tag-list.tsx`、共享样式：测量节点固定隐藏并与可访问列表分离，显示区只呈现实际可见项，避免同一节点重复切换可访问状态。超长标签、单行计数、窗口变化及详情全量标签仍通过测试。此项属于稳定性调整，单独不足以修复原生崩溃。
- `frontend/e2e/partner-filters.spec.ts`：检查按钮语义和真实展开状态，覆盖三维组合、键盘、焦点、清除、空结果及大列表更新。

## 验证

- Windows Edge 154：上述 230 次操作通过；1366×768、1920×1080、390×844，无页面横向溢出。截图使用合成身份，不包含身份 Key。
- UI 回归：**11 passed，33.1 秒，无跳过、无重试**。覆盖伙伴筛选、标签计数/超长标签/详情跳转、后台项目机会筛选。
- `npm run typecheck`：通过。
- `BANFEI_BUILD_CPUS=2 npm run build`：通过，31 个静态页面生成完成。构建前按项目脚本核验并停止开发服务，构建后恢复，未同时写 `.next`。
- `git diff --check`：通过。
- 未验证 ARM，不把 WSL Chromium 测试等同于 Windows 或部署验证。

## 证据文件

- [脱敏诊断与对照结果](../../artifacts/partner-filter-fix/edge-crash-investigation.json)
- [Windows Edge 无障碍模式 / DPR 2 验证](../../artifacts/partner-filter-fix/edge-button-basic-dpr2/edge-result.json)
- [Windows 1920 筛选截图](../../artifacts/partner-filter-fix/edge-button-basic-dpr2/edge-capabilities-1920.png)
- [Windows 窄屏筛选截图](../../artifacts/partner-filter-fix/edge-button-basic-dpr2/edge-capabilities-390.png)
- [11 项回归结果](../../artifacts/partner-filter-fix/button-popup/ui-test-results.json)

## 复测入口

保存了 [Windows Edge 诊断脚本](../../artifacts/partner-filter-fix/verify-edge-filters.cjs)。在 Windows Node 下传入当前 HTTPS Origin 和匿名夹具 JSON 的 Windows/UNC 路径：`node verify-edge-filters.cjs HTTPS_ORIGIN ANONYMIZED_FIXTURE_JSON [PLAYWRIGHT_MODULE]`。默认从项目 frontend/node_modules 读取 Playwright，也可用第三个参数或 `BANFEI_PLAYWRIGHT_MODULE` 指定现有安装路径；WSL 调起 Windows Node 时优先使用显式第三个参数，避免环境变量未传递导致加载旧版本。脚本固定独立 Edge、basic 无障碍模式、DPR 2，拦截所有业务接口，验证 HTTPS 证书；不使用原浏览器账号或设置。夹具没有收入仓库。脚本只用于诊断，不是日常运行入口。

## 后续修复：点击文字时误关闭

用户随后反馈只点复选框有效，点击选项文字会收起菜单。新增直接点击 label 文字的回归用例，修改前在“菜单应保持可见”断言处稳定失败。原因是点击 label 文字时，焦点先从按钮/输入框离开，随后浏览器才将点击转交给关联复选框；原 `onBlur` 将这一中间状态当作离开筛选器，提前卸载了弹层。

共享组件改为在打开期间监听外部 `pointerdown` 和实际外部 `focusin`，不因中间失焦关闭。保留 label 与原生 checkbox 的默认关联，不用阻止默认事件或手动二次切换。点击文字、行内留白、方框都能切换一次且保持菜单展开；点击外部非输入元素、切换筛选器、键盘移出和 Escape 仍正常关闭。未改样式、分类、接口或数据。

- 新用例覆盖三类筛选的文字、留白、复选框、菜单内提示文字、外部标题、Space、清除和 Escape；修复后全部 UI 回归 **12 passed，39.4 秒**。
- `npm run typecheck`、`git diff --check` 通过。
- Windows Edge 154 / basic 无障碍模式 / DPR 2：63 个能力、12 个行业、40 个区域，共 **230 次文字及行内留白点击**，每次断言选中状态与菜单保持展开，全部通过，无 pageerror 或 renderer crash。
- 首轮完整交互结束后，项目内旧 Playwright 1.49 在关闭浏览器阶段出现 `TargetClosedError`，进程返回 1；这不是页面崩溃。改用本机新版 Playwright 对三个维度补测 12 次文字/留白操作及三种视口，验证通过且进程正常返回 0。
- `BANFEI_BUILD_CPUS=2 npm run build`：通过，31 个静态页面生成完成。按项目脚本停止开发服务后构建，再恢复预览，未并行写 `.next`。
- [Windows 完整交互结果](../../artifacts/partner-filter-fix/edge-label-click/edge-result.json)、[新版工具补测](../../artifacts/partner-filter-fix/edge-label-smoke/edge-result.json)。
- [本轮 UI 测试结果](../../artifacts/partner-filter-fix/label-click/ui-test-results.json)

Windows 诊断脚本同时改为直接点击文字及行内留白并断言勾选状态与展开状态；去掉了之前菜单关闭后自动重开的处理，避免掩盖这个交互问题。
