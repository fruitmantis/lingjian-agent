# 新任务提交后的连续转场验证

日期：2026-10-01。工作区：`/home/yuan/project/lingjian-agent-enablement`，分支 `main`。基线 `07e31bb3318ec9aa67a8259fd0dc840b7577afb1`。本轮改动未提交、未推送、未部署。

## 实施范围

- 匹配与发展共用 `frontend/components/task-transition.tsx`，状态放在既有任务导航 Provider 中；没有另建全局状态系统或安装动画库。
- 提交期间按钮显示“提交中”，保留输入；真实创建失败保留可编辑原文。收到真实 ID 后立即沿用 `/tasks/{id}` 和原侧栏选中逻辑。
- 临时视觉层位于既有 AppShell 内，跨路由保留原文；欢迎与示例淡出 180ms。真实详情读取完成后，输入边界与位置收拢 280ms，文字保持原字号，不缩放。进度随后上移 6px、淡入 180ms。
- 进度和业务结果继续来自真实任务快照。后续新保存的区块淡入 180ms，已存在节点不会因轮询重新播放或滚动。
- 刷新、历史任务、普通追问不重播；任务切换丢弃原过渡，迟到回执不能夺回当前路由。减少动效时省略上述动画。
- 改动限前端组件、样式、相关浏览器用例及本文证据。后端、PG、API、创建事务、模型、权限和版本逻辑未改。

## 最终被测源码

[SHA-256 文件清单](evidence/task-transition-20261001/source-manifest.json) 覆盖本轮 13 个前端代码、配置与测试文件；最终回归、实际 IP 专项和构建之后再次核对，无漂移。该清单的 SHA-256：`8f9b8afc8877950f420b228ea1913033b424eaa864abddea036f9d00d6ec2771`。文档与录屏后整理，不属于产品执行路径。

## 实际验证

| 验证 | 最终结果 |
|---|---|
| 相关 Playwright：转场、真实 HTTP 回放、进度、任务导航、失败保护、统一入口 | 51 通过，0 失败，0 跳过，268.1 秒 |
| 实际 IP `http://172.21.208.223` 转场与 HTTP 回放专项 | 16 通过，0 失败，0 跳过，95.7 秒；为前述用例重复验证，去重仍为 51 项 |
| `npm --prefix frontend run typecheck` | 退出码 0 |
| `BANFEI_BUILD_CPUS=2 npm --prefix frontend run build` | 退出码 0，Next.js 生产构建成功 |
| `git diff --check` | 通过 |

[逐用例结果](evidence/task-transition-20261001/browser-results.json) 从最终两份 JUnit XML 提取，仅保留用例名、状态、耗时和汇总；不复制服务日志、令牌或请求材料。[typecheck 输出](evidence/task-transition-20261001/typecheck.txt)、[build 输出](evidence/task-transition-20261001/build.txt)。

执行前私密加载既有 `BANFEI_TEST_DATABASE_URL`，验证入口与主要命令：

```bash
PLAYWRIGHT_MODEL_MODE=replay .venv/bin/python scripts/run_postgres_validation.py browser task-transition task-progress.spec.ts task-navigation.spec.ts task-failure.spec.ts unified-entry.spec.ts --reporter=line,junit
PLAYWRIGHT_MODEL_MODE=replay PLAYWRIGHT_HTTP_ORIGIN=http://172.21.208.223 .venv/bin/python scripts/run_postgres_validation.py browser task-transition --reporter=line,junit
npm --prefix frontend run typecheck
BANFEI_BUILD_CPUS=2 npm --prefix frontend run build
```

覆盖两种任务的正常提交、受控慢回执及慢详情、422 创建失败、刷新、历史切换、提交中离开、详情到达前切换、减少动效；窗口 1366×768、1920×1080、390×844，既有导航回归还覆盖 768/1024 宽度。逐帧采样断言原文没有消失，侧栏与主工作区 DOM 没有重建，文字始终 16px 且未缩放，需求收拢与进度淡入分别为 280ms/180ms，进度不与收拢框重叠。重复轮询断言已存区块节点稳定且不滚动。

真实 HTTP 回放用例通过当前后端与专用 PG 临时 schema 创建两类任务，检查 202、真实任务 ID、当前侧栏、后端持久化进度及 ready 结果；发展任务继续一次普通解释，验证没有重播转场。模型使用现有隔离 replay，未调用真实供应商。

初次适配过程中记录过：一项逐帧测试误选隐藏 Tab 的 textarea（改为选可见且内容匹配的输入）；视频配置放在 describe 中导致采集失败（移至文件顶层）；一项原导航用例依赖已移除的首页临时摘要（改为断言真实详情原文与已选中侧栏，保留单次创建、单条任务及待提交清除断言）。均已修复，并在上述同一最终源码状态完整重跑相关集合，没有 skip、xfail 或削弱业务断言。

## 实际录屏

录制来源为实际 IP 的 Playwright 页面，1366×768、默认缩放；合成伙伴和需求，接口、落库与轮询使用隔离服务，模型为 replay。仅隐藏 Next.js 开发工具浮层；未替换应用内容、插入模拟动画或修改录制速度。视频从浏览器 WebM 转码为 MP4。

- [伙伴匹配：13 秒](../../artifacts/task-transition/match-http-ip.mp4)
- [伙伴发展及普通追问：14.48 秒](../../artifacts/task-transition/development-http-ip.mp4)

## 环境与边界

测试仅使用现有验证器创建的专用 PostgreSQL 临时 schema，没有向正式数据库写测试数据；没有修改私有模型配置、上传资料、身份 Key 或保留备份。按项目脚本停止本机应用后串行运行浏览器、typecheck 和 build，避免共同写 `.next`；完成后按原配置恢复本机服务。未运行全量后端测试（后端无改动），本轮没有 Windows Edge 或 ARM 实测，也没有真实模型质量验证。
