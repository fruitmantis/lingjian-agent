# 灵鉴 Agent 全局视觉统一

结论：**READY FOR VISUAL REVIEW**。仅视觉设计系统收口，真实模型调用 **0**。

## 设计与修改范围

- **Logo**：Git 全历史未找到独立 SVG/PNG/ICO 原资产；在 `5a20d5b` 找到原始 CSS Logo。恢复相同的红色圆角方形与白色 `skew(-18deg)` 几何比例；不是根据截图重画近似图标。Shell 图标为 32px；favicon 将同一几何序列化为 SVG。登录页、侧栏和页面 title 统一“灵鉴 Agent”。
- **Token**：`frontend/app/globals.css` 统一品牌 `#C7000B`、hover `#A80008`、light `#FFF2F2`；主/次/辅助文字 `#191919 / #595959 / #8C8C8C`；背景 `#F7F7F7 / #FFFFFF`；灰边 `#E5E5E5 / #D9D9D9`。兼容旧变量的别名，装饰性背景改中性灰，不把蓝底直接替换成红底。
- **蓝色清理**：扫描 app/components/lib 的 CSS、TSX、TS、SVG，清理品牌蓝及蓝灰硬编码；浏览器另外检查实际可见元素的文字、背景、边框、outline。成功、警告、错误保留语义色。
- **品牌强调**：红色只集中于 Logo、主要 CTA、活动 Tab 下划线、导航细线、focus 和操作链接。正文、图标、标签与目录背景以黑白灰为主。
- **Sidebar**：256px；选中项深色字重、浅灰背景与 2px 红色左线。保留全部既定导航与独立滚动任务历史。
- **Tab / Button / Input**：文字 Tab + 2px 红色下划线；红色主按钮，白底灰边次按钮；控件 4px 圆角，灰边白底，红边与轻红 focus ring。
- **Card / List**：普通圆角 4–8px，取消重阴影与渐变；Advisor 用标题/分割线分区，资源使用小图标、紧凑行与只读属性；资源中心两列紧凑目录；场景、伙伴、任务、管理后台统一边框、字重和中性色。
- **Typography**：页面标题 26px、二级标题 18px、区块标题 16px；继续系统中文字体，不加载外部字体。

**业务边界**：未更改 API、业务路由、数据库/schema、匹配与发展 Agent、Plan/Run/Version、权限、撤权、任务机制、资源数据与共享契约。后端变动仅为 E2E 准备器生成临时认证文件；没有后端产品逻辑改动。此前用户要求的“注册 / 提交”文案与提示间距保留。

## 验证

| 实际命令 | 最终结果 |
| --- | --- |
| `.venv/bin/python -m pytest backend/tests -q --tb=short -o junit_family=legacy --junitxml=/tmp/huawei-backend.xml` | 501 通过，0 失败/跳过；2 条既有 Starlette 弃用警告；328.75s |
| `npm run typecheck`（frontend） | 通过；最终冻结代码 2.00s |
| `npm run build`（frontend） | 通过；最终冻结代码 18.61s |
| `npm run test:e2e -- huawei-visual.spec.ts`（frontend） | 2 通过，0 失败；34.48s |
| `ENABLEMENT_EVIDENCE_DIR=/tmp/huawei-final-evidence npm run test:e2e`（frontend） | 全量 62 通过，0 失败/跳过；392.68s |

首轮全量浏览器测试为 60 通过、2 失败：新增测试误选了同名场景分类 Tab，已限定到任务模式 Tab 后重跑通过。生产功能没有因该测试问题改变。Next.js 开发服务器的既有跨域来源提示保留，未借视觉任务扩大启动架构。

回归包含匹配/证据、任务重试与历史、用户审批/首次改密/权限、模型配置与系统状态、资源发布/下架/撤权、Advisor explain/revise、版本冲突与失败保留旧建议。静态品牌蓝扫描为 0；16 个页面/视口的实际渲染颜色检查和横向溢出检查通过。

新增视觉 E2E 首先核验 8100 进程指向 `/tmp/lingjian-enablement-e2e/app.db`，禁止复用运行服务。测试令牌在隔离 seed 后生成，只存 `/tmp` 的 0600 私有文件，不进入 Git。合成测试任务只写临时库。

## 视觉证据

`artifacts/huawei-visual/` 保存 8 页 × 2 视口，共 16 张截图：1366×768、1920×1080。

| 前缀 | 页面 |
| --- | --- |
| [01-project-match · 1366](artifacts/huawei-visual/01-project-match-1366.png) / [1920](artifacts/huawei-visual/01-project-match-1920.png) | 开启新任务：项目找伙伴 |
| [02-development · 1366](artifacts/huawei-visual/02-development-1366.png) / [1920](artifacts/huawei-visual/02-development-1920.png) | 开启新任务：能力发展 |
| [03-advisor · 1366](artifacts/huawei-visual/03-advisor-1366.png) / [1920](artifacts/huawei-visual/03-advisor-1920.png) | 能力发展建议详情 |
| [04-resources · 1366](artifacts/huawei-visual/04-resources-1366.png) / [1920](artifacts/huawei-visual/04-resources-1920.png) | 资源中心 |
| [05-scenes · 1366](artifacts/huawei-visual/05-scenes-1366.png) / [1920](artifacts/huawei-visual/05-scenes-1920.png) | 场景广场 |
| [06-partners · 1366](artifacts/huawei-visual/06-partners-1366.png) / [1920](artifacts/huawei-visual/06-partners-1920.png) | 伙伴洞察 |
| [07-tasks · 1366](artifacts/huawei-visual/07-tasks-1366.png) / [1920](artifacts/huawei-visual/07-tasks-1920.png) | 全部任务 |
| [08-admin · 1366](artifacts/huawei-visual/08-admin-1366.png) / [1920](artifacts/huawei-visual/08-admin-1920.png) | 管理后台首页 |

## 环境与保护

新版地址：<http://localhost:3100>；后端：<http://localhost:8100/health>。
新版数据库：`/home/yuan/project/lingjian-agent-enablement/.isolation/runtime/dev/app.db`。
本地 mock：18180，`local-development-mock`。真实模型调用 0。

视觉代码冻结提交：`e84a8636282cc4198cdb264eb9c648e00e814878`；分支：`feature/partner-enablement-v1.1`。报告、16 张截图与脱敏机器证据作为后续独立文档提交归档。

新版登录、双任务入口、伙伴上下文、课程/实验/案例、旧路由兼容及已有失败调整后的建议可用性冒烟通过，0 页面错误。新版 3100/8100/local mock 保持运行。

旧 main 仍为 `f79cbb29ec7b3ad70c88e618e3161211f211c06a`；旧 3000/8000 原进程保留，8000 匿名 health=200；受保护的 167 个旧版文件 hash、原 runtime 源库 hash 未变化。新版数据库与旧库不是同一文件，无软/硬链接。schema 仍为 12，integrity=ok，2 条既有外键异常保留、新增 0。未修改或修复业务数据，未 merge/push/部署。

## 已知限制

截图使用合成数据，不代表真实业务验收。桌面两档视口已按本轮要求验证；其他设备与浏览器不宣称完成验收。参考提供的录屏视觉语言，未复制营销首页布局。

机器证据：[验证结果](artifacts/huawei-visual/validation-results.json)、[截图清单与 SHA-256](artifacts/huawei-visual/screenshot-manifest.json)、[稳定版保护](artifacts/huawei-visual/protection-verification.json)。未提交数据库、上传材料、凭据、私有快照或原始运行日志。
