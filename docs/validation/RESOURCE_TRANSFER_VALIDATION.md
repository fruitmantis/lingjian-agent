# 课程与实验 Excel 导入导出及批量上下架

日期：2026-09-26。基于 main / `5132b93003e818b699909137de1f01483fbdf434` 的后续增量；本次未 commit、push 或 deploy。此前 Git 收口数字不计入本记录。

## 范围与操作

- `/admin/resources` 增加导出全部 Excel、导入 Excel、类型/状态筛选、勾选与批量上下架，复用现有页面和发布服务。
- 新增管理员接口：`GET /admin/enablement/resources/export`、`POST /admin/enablement/resources/import`（multipart file）、`POST /admin/enablement/resources/batch`。匿名 401、普通用户 403。
- `.xlsx` 包含课程/实验全部当前业务编辑字段、三项独立用途授权、导出时状态参考列，以及岗位/专区分类表。可直接把导出文件作为维护模板；内网需先运行包含本功能的代码及依赖。
- 同 ID 更新当前草稿；空 ID 按类型与跳转链接匹配，避免重复新增；无变化不增加修订。类别按类型和名称复用或补充，保留已有分类、排序和关联。旧内部能力标签在同环境更新时保留，不跨环境创建标签。
- 导入不自动发布，导出时状态不用于自动上下架或撤权。授权按三列分别更新，减少授权继续触发既有撤权保护；已发布内容仍来自原快照。管理员批量上架时发布选中资源的当前草稿，按现有校验创建版本；批量下架仅处理已发布资源，不删除版本。
- 导入、批量上下架各在单一事务中执行，任何一条错误整批回滚；导入提示工作表/行号，批量操作检查列表中的修订号。没有新增数据库表、异步任务、模型调用或数据迁移。
- 单文件最大 10 MB、2000 条资源；Excel 解压体积和分类数量有界，不执行公式，导出文本不会变成公式。继续校验资源类型、层级、分类、字段长度、URL和独立授权。
- 迁移的是当前业务编辑资料，历史版本、审计、账号和任务引用保留在各自环境。来源链接/封面链接原样保留，不抓取或下载外部文件。正式库没有执行导入、上下架或测试写操作。

## 本次验证

- 首轮相关后端回归：**45 passed**，其中 34 项专用 PostgreSQL 临时 schema、11 项既有 `/tmp` SQLite 兼容用例。覆盖资源中心、独立授权、发布/撤权、字段往返、分类跨环境映射、重复/并发导入、错误回滚、批量修订冲突。
- 收紧资源 ID 格式后，最终导入导出专项 **18 passed**，全部使用专用 PostgreSQL 临时 schema。该组与首轮重叠，不累加通过数。只有既有 PyPDF2 弃用警告。
- Playwright **3 passed**：筛选与勾选、取消与批量提交的 ID/修订号、上架/下架反馈、Excel 下载与 multipart 上传、导入成功/错误行提示、390px 页面无溢出和键盘选择。所有后端请求由浏览器拦截为合成响应，无运行库写入。首轮补齐 `/health` 拦截并将错误断言限定到业务提示，避免与 Next.js 路由播报器冲突后复验通过。
- `npm --prefix frontend run typecheck`、`git diff --check` 通过。production build 在 `/tmp/banfei-resource-build-*` 的独立前端源码副本通过，未与开发服务共用 `.next`。
- 正式资源只读检查：136 门课程、37 个实验，当前元数据均通过现行模型校验；内存中生成并解析 Excel 为 **173 条资源、11 个分类、63871 字节**。不落盘真实资料、不调用导入、不回填数据。
- 通过项目脚本核验归属、短暂重启并恢复当前工作区服务；3000 `/admin/resources` 和 8000 `/health` 均 HTTP 200。未访问旧工作区，未重跑 schema 17 迁移或 178 家名单整理。

本机临时证据：`/tmp/banfei-resource-transfer-backend.xml`、`/tmp/banfei-resource-transfer-final.xml`、`/tmp/banfei-resource-transfer-ui/`。UI 临时配置 `/tmp/banfei-resource-transfer-playwright.cjs` 无 webServer，只使用现有页面并拦截业务接口；可能随 `/tmp` 清理。

后续复验可沿用正式验证入口（先私密加载验证库配置；浏览器入口会启动专用测试服务，按 README 协调端口）：

```bash
.venv/bin/python scripts/run_postgres_validation.py backend -q -k resource_transfer
.venv/bin/python scripts/run_postgres_validation.py browser resource-transfer.spec.ts
```

公司内网的实际导入与外部链接可访问性尚未验证；本轮不包含内网部署或业务验收。

## 伙伴导入导出与空白模板增量（2026-09-26）

- 伙伴管理新增 `/partners/export`、`/partners/template`、`/partners/import`，均仅管理员可用。包括启用/停用伙伴的基础字段、标准及待确认分类、完整画像、画像待更新状态；时间列作参考。案例、文件和任务不随表格迁移，既有删除保护保持原样。
- 按 ID 优先、唯一完整名称后备匹配，新建或更新同一行，不合并/删除伙伴。导入单事务，失败提示行号并回滚；无变化的重复导入不更新时间。直接采用画像，不调用模型；更新画像时间使生成中的旧请求遵循既有冲突保护。
- Excel 单元格长度有限，超过 32000 字的文本自动拆入“长文本续文”表，导入按关联及连续段号完整拼接，不静默截断。空白模板包含表头、行业/区域参考及填写说明，不包含现有伙伴资料。
- 课程/实验新增 `/admin/enablement/resources/template` 和“下载导入模板”按钮，提供空白资源表、当前分类及使用说明；原导出/导入和批量上下架保持原流程。
- 仅执行 **4 项后端 PostgreSQL 定向测试、1 项页面入口测试**，全部通过；另做 typecheck 和 diff 检查，未重跑全量套件或 production build。覆盖长画像往返、旧分类与案例保留、按名称去重、整批回滚、权限、两种模板及模板填写后导入；页面业务请求全部拦截，不写运行库。
- 现有 **178 家伙伴**仅在内存中导出并重新解析，全部完整画像逐项一致；Excel 37479 字节。不保存真实资料副本、不向正式库执行导入，不重跑任何历史数据整理。
- 通过项目脚本恢复 3000/8000，伙伴页和健康接口 HTTP 200。保持 main，包含上一轮未提交改动；未 commit、push 或 deploy，无 schema 变更。

本次后端证据：`/tmp/banfei-partner-transfer.xml`。可用正式验证入口的 `backend -q -k test_partner_transfer` 复验；页面增量位于 `resource-transfer.spec.ts` 的 `partner Excel and resource template download entries` 用例。
