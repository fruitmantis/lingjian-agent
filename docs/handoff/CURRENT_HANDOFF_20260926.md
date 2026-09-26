# 伴飞 Agent 当前项目交接（2026-09-26）

用于同一正式工作区的新对话接续。先读本文件、根目录 AGENTS.md 和 README.md，再根据新任务读相关代码与 docs/validation。用户最新指示、实际代码和实时核验优先；不要因历史对话很长而重新实施已完成事项。

## 1. 当前基线与执行边界

- 唯一工作区：`/home/yuan/project/lingjian-agent-enablement`。禁止访问、修改或启动旧工作区。
- 分支 `main`；本轮收口前基线为 `c7454be16b37b94cde49a92d90e3ba326ebc0974`。本批代码已分为 `157c8d5`、`dbbdad2`、`43555ad` 三个提交，文档随收口单独提交；提交范围和最终验证见 `docs/validation/GIT_CLOSEOUT_20260926.md`。新对话必须实时核对 HEAD、origin/main 与工作区。
- 伙伴资料、画像、统一管理、UI 及文档属于本轮授权提交范围；不要根据旧阶段报告的“未提交”断言当前仍为脏工作区。若发现新增修改，先检查来源，不得 reset、clean、丢弃、切分支或另建 worktree。
- 本轮用户明确授权 commit 和普通 push，未授权 deploy。私有名单、数据、备份和一次性脚本不提交。授权不自动延伸到下一轮新开发或部署。
- 前端 Next.js 15 / React 19 / TypeScript，localhost:3000；后端 FastAPI / Python，localhost:8000。
- PostgreSQL 16，正式库 `banfei_agent`，应用用户 `banfei_app`，**当前 schema 17**。不要按早期 schema 16 文档回退。
- 私有运行配置：`.isolation/runtime/dev/environment.json`。原件：`.isolation/runtime/dev/uploads`；日志：`.isolation/logs`。不能输出连接串、密码、Token、身份 Key。
- 验证期间通过项目脚本停服以避免端口/构建冲突，验证后恢复 3000/8000；最新健康结果见收口记录。PID 不作为持久基线，操作前重新核对。
- 服务只用 `bash enablement-dev.sh status|start|stop` 管理。运行服务、build、Playwright 不得同时写同一 `.next`。
- 用户偏好：最小设计；不要另造平台、审批、共享版本、设备管理、OCR 或复杂架构。授权实施后直接完成，按影响范围验证，保持环境可验收。

## 2. 当前业务规则（无需重复开发）

- 普通用户：浏览器自动登录 + 每人一个长期身份 Key；本人可复制/下载/在个人中心重新查看，支持粘贴或导入 `.txt` 登录。没有普通注册、审批、密码登录、首次改密或 Passkey。
- 主动退出保留可恢复的浏览器身份；停留身份入口，点击继续恢复，不立即自动创建新用户。管理员独立 `/admin/login`，两种会话互不覆盖。
- 账号删除是逻辑删除、保留业务数据，撤销全部凭据会话；阻止删自己、最后一个可用管理员及有运行中任务的账号。不要恢复旧 90 天/凭据类型删除规则。
- 管理员用户页显示鉴权方式及 Key 脱敏标识：`bf_` + 随机部分前 2 位 + `…` + 最后 5 位。绝不返回管理员完整 Key。
- 两条任务入口：资源匹配、能力发展；前置 Scope Gate 单独判定范围，范围外不生成业务数据、不计系统错误。
- 能力发展保留 Plan/Run/Version/current；最新成功版本自动成为 current，失败保留旧 current；confirmed 只保留历史字段，不参与业务。
- 解释/讨论追问只追加回答，明确修改才生成新版本；回答按“结论 + 动态主题”展示。
- 普通错误提示简化；真实错误脱敏追加到现有日志，后台系统状态提供最近错误和复制详情。
- 课程/实验共用可维护岗位/专区多选，层级基础/进阶；课程没有时长，实验保留时长。已有课程/实验导入和详情补全已经完成，不重新抓取或导入。
- 行业/区域唯一字典：`shared/business-taxonomy.json`，未知分类保留待确认，不猜测。

## 3. 本批实现：伙伴资料、案例与画像

### 六类文档

- 接受 PDF、TXT、Markdown（md/markdown）、DOCX、PPTX、HTML（html/htm）。前后端共用 `shared/partner-materials.json`，服务端检查真实结构。
- 完整保存原件；提取原生文字及普通表格，全文缓存到 PostgreSQL。
- **无 OCR、图片识别、旧 DOC/PPT 支持；图片不进入画像输入。** 原件不删图、不重写。
- PDF 预览原文件；DOCX/PPTX 经本机 LibreOffice 转 PDF 并缓存；TXT、Markdown、HTML 安全只读展示，不加载外部图片或运行脚本。
- 处理失败保留原件，支持重试；预览失败不抹掉成功提取文字；打开页面不重复解析。
- 本机已准备 LibreOffice Writer/Impress、中文字体及 Python 依赖；新机器仍需按 README 准备。不安装 OCR 模型。

### 案例精简

- 一条案例必须归属伙伴；表单为伙伴、标题、两级分类、多份文件、可选简介。
- **只有 visible 展示开关**，默认关闭。展示则读取当前内容和全部当前附件；隐藏后目录、详情和旧附件链接不可访问。
- 已移除案例共享版本、发布/核验、绑定和独立三维授权。课程/实验的草稿/发布、用途授权保持原样。
- 历史任务文字保留；案例链接检查当前展示状态，已删除/隐藏的来源不可继续访问。
- 三大类/18 个二级分类唯一来源为 `shared/partner-materials.json`：
  - 营销与宣传：客户开发与线索、销售与产品物料、市场活动、客户成功案例、案例制作与规范、内容与传播活动。
  - 交付管理：项目管理、交付流程与质量标准、方案实施与割接、运维保障、工具与脚本、复盘与经验教训。
  - 技术案例：架构设计、云迁移与云原生、数据与AI、安全与合规、平台与运维工具、最佳实践与官方文档。

### 伙伴画像

- 导入 DOCX 后完整提取，直接作为当前画像采用，不调用 AI 重写；失败不覆盖旧画像。
- 原件和完整画像仅管理员可见。
- 案例/资料变化只标记待更新，由用户手动点击更新；不自动调用模型。
- 更新使用已缓存的完整文字，不再保存时截断 30000 字/模型输入每份只取 5000 字。
- 当前输入预算默认 60000 字；超限明确拒绝并保留原画像，不做复杂分段摘要流水线。
- 并发材料/画像变化、处理未完成或生成失败都不能覆盖有效画像。

### 一个页面、两个入口

- 全局：`/admin/partner-materials`，侧栏“伙伴资料”。
- 伙伴详情：`/admin/partners/{id}` → “管理资料”，进入同一页并带 `partner_id` 筛选；新增自动带入伙伴。
- 按一级分类横线分组，桌面每行 3 张卡片；一个案例多个附件仍只有一张卡片。
- 伙伴/两级分类/名称筛选，12 条分页，沿用页数和跳转能力。
- 可编辑、补充/替换附件、查看、下载、删除、切换展示；附件替换先校验再生效，保留原文件 ID，失败不破坏旧文件。
- 旧独立资料列在“待分类资料”；管理员显式归类时复用原文件 ID、路径、缓存，不复制原件、不自动迁移。
- 画像导入原件仅在伙伴详情的画像区域，不进入案例分类目录。
- 旧案例共享入口仅跳转到统一资料页，不恢复旧界面。

### 主要代码位置

- 契约：`shared/partner-materials.json`、`backend/app/material_contract.py`。
- 文件链路：`backend/app/doc_extractor.py`、`file_storage.py`、`material_files.py`，`routers/documents.py`、`routers/cases.py`、`routers/profile.py`。
- 当前案例读取：`backend/app/case_content.py`，以及 enablement/development 相关适配。
- 统一后台接口：`backend/app/routers/partner_materials.py`（目录聚合及旧资料归类）；注册在 `backend/app/main.py`。
- schema：`backend/app/partner_materials_schema.py`、`storage_models.py`、`postgres_storage.py`；显式迁移 `scripts/migrate_partner_materials.py`。
- 前端：`frontend/components/partner-materials-manager.tsx` 和同名 CSS module；`material-files.tsx` 和同名 CSS module；`frontend/app/admin/partner-materials/page.tsx`；伙伴详情和侧栏相应入口。
- 验证：`backend/tests/test_partner_materials*.py`、`frontend/e2e/partner-materials.spec.ts`；更多回归文件已有相应适配。

## 4. 已执行的数据库操作：不要重复

### schema 16 → 17（已完成）

- 保留 partners/cases/partner_documents/deliverables 的原 ID、原件、原文，增加必要分类/展示/处理/预览/画像待更新字段。
- 已移除 `case_share_configs`、`case_share_versions`、`enablement_reviews`；不是待执行脚本。
- 当时 4 个旧案例设为不展示、待分类，避免把旧摘要授权扩大到内部全文；不同旧公开摘要留存于审计及完整备份。
- 当时 3 份 PPTX 已提取全文并生成缓存 PDF，3 ready / 0 error。
- 迁移备份：`.isolation/partner-materials-migration/20260925T154746Z/before.pgdump`。
- **上面是迁移当时的数据状态；最新伙伴数量/案例数量以后一节名单整理为准。**

### 用户指定的 178 家伙伴名单整理（已完成）

这是一轮用户明确授权的一次性数据整理，不是日常“删除伙伴”业务规则修改。后台日常删除仍受业务引用保护；没有新增批量强删接口。

- 原 36 家伙伴，完整名单 178 家（无重复）。
- 按精确公司名称保留已有 9 家，新增 169 家；新建仅公司名称，状态启用，不猜能力、行业、区域或画像。
- 清单外 26 家硬删除；另删除“佳杰云星”别名记录，合并到已有“重庆伟仕宏翔科技发展有限公司”。因此 partners 表实际删除 27 行、更新 1 行、插入 169 行。
- 重庆伟仕宏翔保留原 ID；佳杰云星原文档迁入该 ID，画像补入，标签取并集，保留原有发展方案。原文件、预览和缓存文字不改写。具体 ID 仅在私有操作记录中核对。
- 名单外专属清理：3 条案例、13 份发展方案、13 个请求、16 个 Run、15 个 Version、66 条版本资源项、17 条诊断、46 条方案审计子记录。
- 54 条匹配任务全部保留；49 条任务的推荐及对应需求画像/机会推荐字段有整理。共移除 108 个失效推荐项（包括原有 10 个悬空引用），合并 8 个别名推荐。任务本身及其他伙伴推荐保留。
- 名单内其他伙伴行不变，3 份原始文档及 3 份预览哈希不变；课程/实验、账号、配置不变。
- 先在专用测试库临时 schema 演练；再停止本项目服务、pg_dump 完整备份、单事务执行、检查约束和数据对账，最后恢复服务。
- 现有 user_audit_logs 新增一次名单整理审计，操作者记录为系统执行并注明当前会话用户授权；未冒充某个具体管理员。
- **操作脚本按旧 36 家基线编写，不是可重跑的初始化脚本。不要再次运行，不要重新 seed。**

私有记录（全部 Git 忽略，不提交）：

- 名单：`.isolation/partner-roster/20260926/roster.txt`
- 一次性脚本：`.isolation/partner-roster/20260926/reconcile.py`
- 演练：`.isolation/partner-roster/20260926/rehearsal.json`
- 结果：`.isolation/partner-roster/20260926/result.json`
- 只读验证：`.isolation/partner-roster/20260926/verification.json`
- 执行前完整备份：`.isolation/partner-roster/20260926/backup-20260925T175544Z/before.pgdump`（文件名用 UTC，业务日期为北京时间 9 月 26 日）。

整理完成时主要数量：partners 178，cases 1，partner_documents 3，development_plans 1，development_versions 1，match_records 54，demand_profiles 53，project_opportunities 53，enablement_resources 173，enablement_resource_versions 301，users 3。此为操作完成时对账数，之后用户操作可能变化。

保留方案中的旧案例来源按现有逻辑标为不可用，历史方案文字仍可读；未重写保留的 Version 快照。伙伴目录、合并画像、合并资料和保留任务的实际 API 已核验 HTTP 200。

## 5. 最新 UI 调整（已完成，纳入本轮提交）

- 普通“伙伴洞察”卡片桌面每行 3 张，长名称换行，窄屏自适应。
- 后台伙伴上下文条“返回伙伴详情 / 查看全部伙伴资料”统一等高按钮、图标、间距。
- 运营报表：时间范围、行业、区域、能力标签桌面一行四项，40px 等高；行业/区域复用下拉多选。
- 上一版新 CSS module 未在用户页面正常体现，已改接全局 `frontend/app/ui-system.css` 的 `report-filter-*` 样式，删除临时 `report-filters.module.css`，不要恢复它。
- 报表更新时筛选控件持续挂载，连续输入不失焦；请求序号避免旧响应覆盖新条件。
- 后台资料卡片使用 `.ui-catalog-card`，课程/实验现用 `.learning-card` 已在收口验证中补齐共享选择器，与前台伙伴卡片共用静止阴影、hover 上移 2px 和增强阴影；键盘焦点及 reduced-motion 保留。
- 后台按钮、表格行、summary 使用统一悬浮反馈；标签/分类/模型表格去掉遮挡 hover 的行内 transparent 背景。表单、阅读面板不做整体上浮。
- 主要文件：`frontend/app/ui-system.css`、`globals.css`、`components/admin-demand-panels.tsx`、`admin-panels.tsx`、`partner-materials-manager.tsx` 及其 CSS module。
- 没有修改接口、数据库 schema、统计逻辑、模型配置或权限。

## 6. 最新验证与口径（2026-09-26 Git 收口）

最新整体验证见 [本次收口记录](../validation/GIT_CLOSEOUT_20260926.md)，历史各阶段数字不相加。

1. 后端本轮全量 **810 passed / 0 failed / 0 skipped**；635 项 PostgreSQL，175 项既有 `/tmp` SQLite 兼容/迁移/进程测试。88 项 archived Pilot 默认不收集，不计入通过数。
2. 前端最终 **typecheck / production build 均通过**。
3. 选定 Playwright 本轮最终 **25 passed / 0 failed / 0 skipped**，覆盖资料、课程实验、伙伴维护和共同视觉。首轮测试定位竞态与旧夹具已修正；课程/实验新卡片漏接的共享悬停选择器已补齐。不新增业务功能。
4. 此前 API 模拟审查另覆盖 22 个后台页面/状态、报表筛选焦点/乱序响应、键盘及减少动画、桌面同排和移动端无溢出；属于此前专项证据，不混入本轮 25 项计数。
5. 名单整理此前已完成专用库演练、事务对账及只读 API 验证。本轮不重跑名单操作或迁移。
6. 本轮测试前后正式库 35 表内容摘要、6 个原件/预览 SHA-256 一致；测试只写专用验证库和 `/tmp`。运行库仍为 178 家伙伴。
7. 3000/8000 已恢复，管理页面和 `/health` HTTP 200；本轮执行用户授权的分组 commit 与普通 push，未 deploy、未调用真实模型。Git 最终状态必须以本轮最终回复和实时核对为准。

正式验证入口：

```bash
npm --prefix frontend run typecheck
# build 前协调 .next 使用，不能与 dev/Playwright 同时写同一目录
npm --prefix frontend run build
# 私有 BANFEI_TEST_DATABASE_URL 只能指向 banfei_agent_test 或 banfei_validation
.venv/bin/python scripts/run_postgres_validation.py backend -q
.venv/bin/python scripts/run_postgres_validation.py browser <选定用例>
```

验证私有配置：`.isolation/runtime/dev/validation-environment.json`。不要打印值。模型回放仅在隔离验证环境显式启用；普通 UI 检查不调用模型。

主要记录：`docs/validation/PARTNER_MATERIALS_VALIDATION.md`、`RESOURCE_CENTER_VALIDATION.md`；其他认证/范围门/错误/Pilot 文档按实际任务查阅。早期 788 / 801 / 803 passed 都属于历史阶段，不是当前 810 项结果。schema 17 默认收集不导入旧 Pilot 模块，也不保证历史显式收集命令可运行。

临时 UI 证据（位于 /tmp，可能被清理）：`banfei-admin-visual-results.json`、`banfei-admin-visual-check.cjs`、`banfei-report-filters-check.cjs`、`banfei-admin-report-inline.png`、`banfei-admin-material-hover.png`。

## 7. 新对话如何接续

- 本批开发与工程验证已完成，代码和文档按组提交。接续新需求前先核对实时 Git 和服务状态，不重复已有开发和数据操作。
- 若做新 UI 调整，先读取截图。Windows 路径在 WSL 通常映射为 `/mnt/c/Users/juan/AppData/Local/Temp/<文件名>`，不要看到 `C:\\...` 读取失败就直接猜图。
- 本批分组提交见收口记录，最终 HEAD 与远端状态以实时 Git 为准。后续若出现新改动，先检查 diff/未跟踪文件，新的 commit/push/deploy 仍需用户明确授权；绝不 force push。
- 当前数据已是 schema 17 + 整理后的 178 家伙伴。不要重跑 schema 迁移或名单脚本，不清上传/备份，不恢复旧测试伙伴，不为旧历史工具恢复 V1.2 业务。
- 本轮名单强制清理授权已完成；不能据此继续删除其他现有数据或改后台日常删除保护。
- 本机工具曾因 bubblewrap `/mnt/wslg/distro` 挂载别名导致默认 sandbox 命令失败；允许后用带理由的 require_escalated 执行。不是项目代码问题，不应修改项目来规避。
- 保持当前服务供人工验收；不得启动 legacy 服务，不增加后台自动任务或调用模型来“验证 UI”。
