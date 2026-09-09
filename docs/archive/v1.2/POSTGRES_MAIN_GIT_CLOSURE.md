> **历史归档，不是当前开发规范。** 保留当时的需求、环境、测试和结论；旧品牌、分支、端口、数据库及授权状态均不代表当前 main。历史命令不可直接用于现有运行库。当前入口：[README](../../../README.md)。

# PostgreSQL 切换后的剩余改动归档

核验日期：2026-09-09。分支：`main`。起点：`88969939d3f339825fbc1aa5e88fccb1e257eadb`。

本轮只归档已有改动与验证证据；开始时的 49 个已跟踪修改文件、5 个未跟踪文件均记录 SHA-256，暂存前逐一核对原始内容。没有新增产品功能、重构、数据库变更或真实模型调用。

## 提交归属

| 提交 | 来源与范围 |
| --- | --- |
| `f4bff4c` | P0：已有画像/证据参与匹配、场景快捷入口、统一任务统计、能力发展状态、README/AGENTS 校准及后端测试。 |
| `737b5a8` | 伙伴删除：管理员操作、业务历史计数阻止、派生数据清理、迟到匹配结果保护及相关后端测试。 |
| `f093a60` | UI：伙伴搜索布局、任务历史字体/状态层级、输入框对齐和纵向调整样式。 |
| 本文所在提交 | 既有 P0、伙伴删除、侧栏 E2E；6 张经目视检查的视觉参考及本记录。 |

`backend/app/routers/match.py` 的 P0 与删除保护混合改动通过暂存区分段提交，工作文件内容未改写。

## 实际验证

验证的功能代码 HEAD：`f093a60006054f08c817fa395da6aab3b00d4f49`。待提交的 3 个 E2E 文件已参与本轮完整运行。

| 检查 | 结果 |
| --- | --- |
| 每组提交前的相关后端 pytest | 99 passed，0 failed / 0 skipped。 |
| 每组提交前的相关 Playwright | 8 passed，0 failed / 0 skipped / 0 flaky；1366×768、1920×1080。 |
| 最终完整 backend pytest | 595 passed；PostgreSQL 292、SQLite 兼容 303；0 failed / 0 skipped；471.75s。 |
| 最终 frontend typecheck | PASS。 |
| 最终 frontend production build | PASS。 |
| 最终完整 Playwright | 72 passed，0 failed / 0 skipped / 0 flaky；505.27s。 |

后端有 13 条既有 pytest JUnit 属性格式 / Starlette 弃用提示；未借本轮归档改动这些代码。

执行入口（测试连接信息由私有环境传入，不包含在本文）：

```sh
.venv/bin/python -m pytest backend/tests/test_p0_closure.py backend/tests/test_system_status.py backend/tests/test_partner_delete.py backend/tests/test_task_creation.py backend/tests/test_tasks.py backend/tests/test_postgres_storage.py backend/tests/test_openapi.py -q
.venv/bin/python scripts/run_postgres_validation.py browser e2e/p0-closure.spec.ts e2e/partner-delete.spec.ts e2e/sidebar-visual.spec.ts e2e/ui-system.spec.ts --reporter=json
.venv/bin/python scripts/run_postgres_validation.py backend -q
cd frontend
npm run typecheck
npm run build
cd ..
.venv/bin/python scripts/run_postgres_validation.py browser --reporter=json
```

PostgreSQL 测试使用专用 `banfei_validation` 临时 schema 与临时低权限账号；SQLite/上传目录使用 `/tmp`。3000/8000 与 mock 在验证期间让给隔离测试，结束后恢复原配置。未登录或向运行库写入测试业务数据。

## 视觉参考的取舍

下列 6 张图片是本轮开始时已有的修改，逐张比较和检查后保留。它们分别记录输入区对齐、任务/版本状态层级、资源卡片与导航样式在两个视口下的效果。

**这些是人工视觉参考，不是 `toHaveScreenshot` 像素断言基线，也不冒充本轮重新生成的截图。** 本轮自动生成的截图写入 `/tmp` 或既有忽略目录，没有覆盖这些原图。布局、溢出、状态语义以 E2E 断言验证。

| 已提交参考 | 像素尺寸（含全页截图高度） | SHA-256 |
| --- | --- | --- |
| `artifacts/enablement-rc/advisor/08-task-list-1366.png` | 1366×1254 | `00db7c976e402ae38a671b9f511ea48c52f3df7c9b294f40fc0d4e637c5a9b47` |
| `artifacts/enablement-rc/advisor/08-task-list-1920.png` | 1920×1446 | `a20538a119f163e34cd05588f7fcfa2367bd38909c76721262f5b199223e7e85` |
| `artifacts/enablement-rc/unified-entry/01-project-match-1366.png` | 1366×1022 | `adc53451aa070e37bd56c54a00de928fd013552b6c4708fe34d3278761bd3c53` |
| `artifacts/enablement-rc/unified-entry/01-project-match-1920.png` | 1920×1080 | `fac141ec8bb5f5f78d3d9cdcafed82735b5e20a9aba613902952cbcfc03cfa0c` |
| `artifacts/enablement-rc/unified-entry/03-resources-1366.png` | 1366×1053 | `c0fcd46ecc5a25410b996d79c255bdf9e25b17d920e5e6233694914c61f39dc2` |
| `artifacts/enablement-rc/unified-entry/03-resources-1920.png` | 1920×1080 | `9f4845bfe56627d7c4b4acff8475639424a2285c7609f89653e666fbc527afa5` |

其余 24 张为重复流程、长页面或带动态运行/版本记录的自动截图，无法确认独立基线价值。它们按用户要求原样保留为未提交修改；没有恢复、删除或重新生成。完整清单：

- `artifacts/enablement-rc/advisor/01-full-advice-1366.png`
- `artifacts/enablement-rc/advisor/01-full-advice-1920.png`
- `artifacts/enablement-rc/advisor/02-exploratory-1366.png`
- `artifacts/enablement-rc/advisor/02-exploratory-1920.png`
- `artifacts/enablement-rc/advisor/03-short-resources-1366.png`
- `artifacts/enablement-rc/advisor/03-short-resources-1920.png`
- `artifacts/enablement-rc/advisor/04-explanation-1366.png`
- `artifacts/enablement-rc/advisor/04-explanation-1920.png`
- `artifacts/enablement-rc/advisor/05-comparison-1366.png`
- `artifacts/enablement-rc/advisor/05-comparison-1920.png`
- `artifacts/enablement-rc/advisor/06-natural-revise-1366.png`
- `artifacts/enablement-rc/advisor/06-natural-revise-1920.png`
- `artifacts/enablement-rc/advisor/07-failed-revise-1366.png`
- `artifacts/enablement-rc/advisor/07-failed-revise-1920.png`
- `artifacts/enablement-rc/unified-entry/02-development-1366.png`
- `artifacts/enablement-rc/unified-entry/02-development-1920.png`
- `artifacts/enablement-rc/unified-entry/04-partner-context-1366.png`
- `artifacts/enablement-rc/unified-entry/04-partner-context-1920.png`
- `artifacts/enablement-rc/unified-entry/05-project-context-1366.png`
- `artifacts/enablement-rc/unified-entry/05-project-context-1920.png`
- `artifacts/enablement-rc/unified-entry/06-advisor-detail-1366.png`
- `artifacts/enablement-rc/unified-entry/06-advisor-detail-1920.png`
- `artifacts/enablement-rc/unified-entry/07-unified-tasks-1366.png`
- `artifacts/enablement-rc/unified-entry/07-unified-tasks-1920.png`

因此归档结束时源码和测试应已提交，`git status` 仍会显示上述 24 张 PNG；不声称整个工作区 clean。
