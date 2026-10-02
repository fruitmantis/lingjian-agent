# 首页与转场独立复核缺陷修复

日期：2026-10-02（本机 +08:00；UTC 2026-10-01）。同一正式工作区 `/home/yuan/project/lingjian-agent-enablement`、`main`、HEAD `07e31bb3318ec9aa67a8259fd0dc840b7577afb1`。本轮未提交、未推送、未部署。

结论：三处 P2 缺陷已修复，实施侧完整 76 项回归通过，交回独立复核。Windows 用户现有浏览器会话完整交互仍未验证，不据此宣称最终独立验收完成。

## 缺陷、修复与复现

| 缺陷与安全复现 | 修复结果 |
|---|---|
| 发展创建延迟 → 切匹配 → 422 拒绝 → 返回发展，原文被锁住 | 在丢弃旧 UI 回执之前，仅清理匹配原 submission ID 的存储锁；重挂载表单同步对应通知。拒绝在离开期间或返回之后到达均恢复编辑、保留原文、允许重试；不把不确定结果或查询 404 当确定拒绝 |
| 两种模式输入 24 行并滚到底 → 提交 → 等待详情，末尾文字跳回首行 | 过渡层继承 textarea 的 scrollTop，并裁切到原输入可见区域；原独立断言验证两模式文字原点位移均 ≤2px，动画结束后完整 24 行原文保留 |
| 匹配创建未回执 → 切发展 → 切回匹配 → 再点同一草稿，产生两个 requestId | 使用已有 pending 列表保护相同原文，切回仍只创建一次；允许不同匹配草稿及发展模式独立提交。交叉模式回归验证两个不同匹配 ID 和一个发展请求完成，旧回执不抢当前导航 |

复现仅在项目隔离合成流程内操作。针对性用例还覆盖先返回再收到拒绝、原文重试获得新 submission ID、不同模式草稿保留以及长文本最终完整展示。

## 修改范围

本次修复仅改 `frontend/app/page.tsx`、`frontend/components/development-assistant.tsx`、`frontend/components/task-transition.tsx`；新增 `frontend/e2e/home-scenes-boundaries.spec.ts`，在现有 Playwright UI 子集登记。首页六项场景、模板、确认行为、伙伴选择及来源上下文沿用[初次交付说明](HOME_SCENES_20261001.md)。

后端、API、PostgreSQL schema、模型配置、认证与部署配置均未改，继续先落库再模型判断。原有未提交工作完整保留。最终源码清单覆盖首页和继承转场的 17 个源码/测试文件；原转场本轮未涉及的 8 个文件哈希不变。

原独立文件 `/tmp/banfei-independent-review-20261002/audit-boundaries.spec.ts` 的 9 项断言完整纳入仓库，仅把绝对 Playwright 包导入改为 `@playwright/test`，另在末尾追加 4 项。[断言完整性核对](evidence/home-scenes-20261001/independent-assertion-integrity.json)。

## 验证结果

| 检查 | 状态 |
|---|---|
| 独立原 9 项 + 新增针对性 4 项，实际 IP HTTP | 13 通过，0 失败，0 跳过 |
| 原首页六场景专项，实际 IP HTTP | 12 通过，0 失败，0 跳过 |
| 原转场、HTTP 回放、进度、导航、失败保护、统一入口 | 51 通过，0 失败，0 跳过 |
| TypeScript、Next.js 生产构建、git diff --check | 通过，退出码 0 |
| 两模式长文本截图、桌面及窄屏合成 Chromium | 通过自动化断言与目视复核 |
| Windows 用户现有浏览器会话 | 未验证：当前任务没有可调用的 Computer Use 工具绑定 |
| ARM、付费真实模型、全量后端回归 | 未执行，本次前端修复不包含这些检查 |

最终合计 **76 项通过**。初交付的 63 项通过是历史结果；随后独立补充发现 4 个失败用例（三类缺陷），本报告以修复后的完整回归为准。

本轮测试迭代记录：原独立 9 项从第一次修复运行起均通过。新增交叉模式用例先因伙伴选项尚未加载而未选中，再因假定 mode 是首个查询参数而失败；补上选项加载与选中断言，按路径及查询参数判断。一次类型检查发现本项目 Playwright 不支持函数式 toHaveURL，改用已有 expect.poll。以上只调整新增用例，没有弱化原独立断言或为通过测试另改产品行为。三次尝试证据保留在本轮 /tmp 的 first-attempt、second-attempt、type-compatibility-attempt。

[逐用例结果](evidence/home-scenes-20261001/browser-results.json)、[退出码与耗时](evidence/home-scenes-20261001/execution-summary.json)、[最终源码 SHA-256](evidence/home-scenes-20261001/source-manifest.json)、[类型检查](evidence/home-scenes-20261001/typecheck.txt)、[构建](evidence/home-scenes-20261001/build.txt)。初交付清单与测试摘要以 initial-* 名称保留。

## 测试安全与下次检查

本轮目录 `/tmp/banfei-home-fixes-vivn6abp/` 含运行器、原始 JUnit、日志和截图。先私密加载 `.isolation/runtime/dev/validation-environment.json`，不输出连接串；服务与构建串行，通过原 enablement-dev.sh 停止及 finally 恢复。测试前只读统计正式库运行中的匹配和发展任务均为 0。

```bash
npm --prefix frontend run typecheck -- --incremental false
PLAYWRIGHT_MODEL_MODE=ui PLAYWRIGHT_HTTP_ORIGIN=http://172.21.208.223 .venv/bin/python scripts/run_postgres_validation.py browser home-scenes-boundaries.spec.ts --reporter=line,junit
PLAYWRIGHT_MODEL_MODE=ui PLAYWRIGHT_HTTP_ORIGIN=http://172.21.208.223 .venv/bin/python scripts/run_postgres_validation.py browser home-scenes.spec.ts --reporter=line,junit
PLAYWRIGHT_MODEL_MODE=replay .venv/bin/python scripts/run_postgres_validation.py browser task-transition task-progress.spec.ts task-navigation.spec.ts task-failure.spec.ts unified-entry.spec.ts --reporter=line,junit
BANFEI_BUILD_CPUS=2 npm --prefix frontend run build
git diff --check
```

验证器仅在专用本地 PostgreSQL 验证库创建随机临时 schema，测试上传使用独立 /tmp。UI 用例全为合成接口，真实 HTTP 用例使用隔离 PG 和本地模型回放；未向正式库写测试数据、未调用付费模型、未传输真实伙伴资料、未读取身份凭据文件。

独立复核应先核对最终源码哈希，再复核上述三个缺陷和原用例；Windows 浏览器需在具备受支持工具绑定的任务继续，不能以本轮 WSL Chromium 代替用户现有会话验收。

服务恢复后 `/login` 与 `/api/health` 均为 HTTP 200，无 HTTPS 跳转；80 对外，3000/8000 仅回环监听，18180 回放服务已退出。[恢复检查](evidence/home-scenes-20261001/restored-service.json)。

## 截图证据

以下为 WSL Chromium 隔离合成页面原始截图，未改图。

- 匹配长文本：[提交前](evidence/home-scenes-20261001/match-scrolled-input-before.png)、[等待详情](evidence/home-scenes-20261001/match-scrolled-input-after.png)
- 发展长文本：[提交前](evidence/home-scenes-20261001/development-scrolled-input-before.png)、[等待详情](evidence/home-scenes-20261001/development-scrolled-input-after.png)
- [拒绝后返回发展](evidence/home-scenes-20261001/returned-after-rejected-create.png)、[切回匹配时防重复](evidence/home-scenes-20261001/duplicate-after-mode-roundtrip.png)、[320px 键盘操作](evidence/home-scenes-20261001/keyboard-short-viewport.png)
- 首页：[匹配桌面](evidence/home-scenes-20261001/home-scenes-1366.png)、[匹配窄屏](evidence/home-scenes-20261001/home-scenes-390.png)、[发展桌面](evidence/home-scenes-20261001/development-scenes-1366.png)、[发展窄屏](evidence/home-scenes-20261001/development-scenes-390.png)
