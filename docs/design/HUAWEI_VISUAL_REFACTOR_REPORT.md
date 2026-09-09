> **设计参考 / 历史取证。** 视觉与字体原则继续适用；报告中的分支、端口、数据库、品牌更名前名称及测试数字仅记录当时状态。当前产品为伴飞 Agent，环境与运行规范以 [README](../../README.md) 为准。

# 伴飞 Agent 视觉设计来源与验证记录

历史结论：该次视觉改造完成工程验证；该次没有真实模型调用，不代表项目累计调用为零。当前目录卡片与控件以 [后续统一规范](VISUAL_SYSTEM_UNIFICATION.md) 和实际共享 CSS 为准。

## 设计与修改范围

- **Logo**：Git 全历史未找到独立 SVG/PNG/ICO 原资产；在 `5a20d5b` 找到原始 CSS Logo。恢复相同的红色圆角方形与白色 `skew(-18deg)` 几何比例；不是根据截图重画近似图标。Shell 图标为 32px；favicon 将同一几何序列化为 SVG。后续品牌更名后，登录页、侧栏和页面 title 统一为“伴飞 Agent”；图形未重新设计。
- **Token**：`frontend/app/globals.css` 统一品牌 `#C7000B`、hover `#A80008`、light `#FFF2F2`；主/次/辅助文字 `#191919 / #595959 / #8C8C8C`；背景 `#F7F7F7 / #FFFFFF`；灰边 `#E5E5E5 / #D9D9D9`。兼容旧变量的别名，装饰性背景改中性灰，不把蓝底直接替换成红底。
- **蓝色清理**：扫描 app/components/lib 的 CSS、TSX、TS、SVG，清理品牌蓝及蓝灰硬编码；浏览器另外检查实际可见元素的文字、背景、边框、outline。成功、警告、错误保留语义色。
- **品牌强调**：红色只集中于 Logo、主要 CTA、活动 Tab 下划线、导航细线、focus 和操作链接。正文、图标、标签与目录背景以黑白灰为主。
- **Sidebar**：256px；选中项深色字重、浅灰背景与 2px 红色左线。保留全部既定导航与独立滚动任务历史。
- **Tab / Button / Input**：文字 Tab + 2px 红色下划线；红色主按钮，白底灰边次按钮；控件 4px 圆角，灰边白底，红边与轻红 focus ring。
- **Card / List**：当前目录使用白色无边框卡片及统一轻阴影/悬停；输入容器保持静止，表格以分割线组织。Advisor 用标题/分区与只读资源属性；以 [后续统一规范](VISUAL_SYSTEM_UNIFICATION.md) 为准。
- **Typography**：页面标题 26px、二级标题 18px、区块标题 16px；中文沿用系统字体；Latin/数字已按 [字体方案](HUAWEI_CLOUD_FONT_SOURCES.md) 从本地加载官方字体。

**业务边界**：未更改 API、业务路由、数据库/schema、匹配与发展 Agent、Plan/Run/Version、权限、撤权、任务机制、资源数据与共享契约。后端变动仅为 E2E 准备器生成临时认证文件；没有后端产品逻辑改动。此前用户要求的“注册 / 提交”文案与提示间距保留。

## 历史验证（对应 e84a863，不代表当前 HEAD 重跑）

| 实际命令 | 最终结果 |
| --- | --- |
| `.venv/bin/python -m pytest backend/tests -q --tb=short -o junit_family=legacy --junitxml=/tmp/huawei-backend.xml` | 501 通过，0 失败/跳过；2 条既有 Starlette 弃用警告；328.75s |
| `npm run typecheck`（frontend） | 通过；最终冻结代码 2.00s |
| `npm run build`（frontend） | 通过；最终冻结代码 18.61s |
| `npm run test:e2e -- huawei-visual.spec.ts`（frontend） | 2 通过，0 失败；34.48s |
| `ENABLEMENT_EVIDENCE_DIR=/tmp/huawei-final-evidence npm run test:e2e`（frontend） | 全量 62 通过，0 失败/跳过；392.68s |

首轮全量浏览器测试为 60 通过、2 失败：新增测试误选了同名场景分类 Tab，已限定到任务模式 Tab 后重跑通过。生产功能没有因该测试问题改变。Next.js 开发服务器的既有跨域来源提示保留，未借视觉任务扩大启动架构。

回归包含匹配/证据、任务重试与历史、用户审批/首次改密/权限、模型配置与系统状态、资源发布/下架/撤权、Advisor explain/revise、版本冲突与失败保留旧建议。静态品牌蓝扫描为 0；16 个页面/视口的实际渲染颜色检查和横向溢出检查通过。

当时视觉 E2E 首先核验隔离后端进程指向 `/tmp/lingjian-enablement-e2e/app.db`，禁止复用运行服务。测试令牌在隔离 seed 后生成，只存 `/tmp` 的 0600 私有文件，不进入 Git。合成测试任务只写临时库。

## 视觉证据

`artifacts/huawei-visual/` 保存 8 页 × 2 视口，共 16 张截图：1366×768、1920×1080。

| 前缀 | 页面 |
| --- | --- |
| [01-project-match · 1366](../../artifacts/huawei-visual/01-project-match-1366.png) / [1920](../../artifacts/huawei-visual/01-project-match-1920.png) | 开启新任务：项目找伙伴 |
| [02-development · 1366](../../artifacts/huawei-visual/02-development-1366.png) / [1920](../../artifacts/huawei-visual/02-development-1920.png) | 开启新任务：能力发展 |
| [03-advisor · 1366](../../artifacts/huawei-visual/03-advisor-1366.png) / [1920](../../artifacts/huawei-visual/03-advisor-1920.png) | 能力发展建议详情 |
| [04-resources · 1366](../../artifacts/huawei-visual/04-resources-1366.png) / [1920](../../artifacts/huawei-visual/04-resources-1920.png) | 资源中心 |
| [05-scenes · 1366](../../artifacts/huawei-visual/05-scenes-1366.png) / [1920](../../artifacts/huawei-visual/05-scenes-1920.png) | 场景广场 |
| [06-partners · 1366](../../artifacts/huawei-visual/06-partners-1366.png) / [1920](../../artifacts/huawei-visual/06-partners-1920.png) | 伙伴洞察 |
| [07-tasks · 1366](../../artifacts/huawei-visual/07-tasks-1366.png) / [1920](../../artifacts/huawei-visual/07-tasks-1920.png) | 全部任务 |
| [08-admin · 1366](../../artifacts/huawei-visual/08-admin-1366.png) / [1920](../../artifacts/huawei-visual/08-admin-1920.png) | 管理后台首页 |

## 当前使用边界

当前 main 的服务、PostgreSQL 和真实模型配置统一见 [README](../../README.md)，不沿用本次取证时的隔离端口、旧数据库或测试模型启动方式。

视觉代码历史冻结提交为 `e84a8636282cc4198cdb264eb9c648e00e814878`。下列证据只证明当时的实现与测试，后续卡片风格、品牌名和字体已继续收口。

机器证据：[验证结果](../../artifacts/huawei-visual/validation-results.json)、[截图清单](../../artifacts/huawei-visual/screenshot-manifest.json)、[当时保护检查](../../artifacts/huawei-visual/protection-verification.json)。未提交数据库、上传材料、凭据或原始敏感日志。
