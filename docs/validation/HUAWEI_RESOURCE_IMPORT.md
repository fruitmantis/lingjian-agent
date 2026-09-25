# 华为云课程 / 实验预置与详情补全

日期：2026-09-25。当前 main 工作区执行；未提交、推送或部署。

## 首次公开目录导入结果

- 入口：https://www.huaweicloud.com/partners/training/course.html 。只取服务伙伴的 7 个岗位学习路径、CodeArts / ModelArts / DataArts / AgentArts 专区，以及实验环境目录；案例不变。
- 本次实时公开页面去重后导入 129 门课程、32 个实验。其中 128 门课程、31 个实验发布；1 门课程、1 个实验保留草稿。先前浏览工具缓存中的 30 个实验不是本次实时目录基线。
- 课程草稿：同一官方课程 ID C101749708981178140 在不同岗位路径分别名为“数据仓库工作级开发者认证（创新中心）”和“大数据工作级开发者认证（创新中心）”；保留同一资源 ID 及两个岗位，不擅自确认名称。
- 实验草稿：“大数据全栈开发实战”（20008179），目录仍列出，但公开详情显示“实验不存在”。不进入普通目录或模型候选。
- 排除独立考试入口；“为什么语言模型用文字接龙，图片生成不用像素接龙呢”的源站 href 拼接两个详情地址，列入未导入清单，不猜测正确目标。
- 21 条新资源关联多个岗位 / 专区，每条仍只有一个 resource_id。课程链接去除源站一次性登录 ticket、跟踪参数及 fragment，保留官方课程 ID 路径。

## 字段与最小适配

- 现有 enablement_resources.draft_json 与 enablement_resource_versions.payload_json 能承接全部公开元数据。仍为 schema 16，没有新表、列、状态、页面或 API。
- 岗位 / 专区按名称匹配当前可维护分类 ID，合并重复出现的分类；不重置现有分类。初级 / 基础映射基础，中级 / 高级 / 进阶映射进阶。专区“通用”按基础目录收纳；已有路径明确层级优先；官方名称明确为中级 / 高级课程时保留进阶。来源原层级保存在本地导入报告。
- 首次公开导入时，课程详情会跳转华为云登录，只使用路径名称、简介、分类和链接。后续已用用户手动登录的浏览器补充详情，结果见下节；源站缺失字段仍留空。
- 31 个实验取得公开详情并按官方 experiment_id 校验，使用详情名称、简介、时长和“实验目标与基本要求”文本（保存到 lab_goals）；未单列的基本要求不推断。不会导入费用、免费名额、评分、评价、人次等旧字段，也不会报名、启动实验或下载教材 / 视频。
- 来源 HTML 转纯文本；导入链接限官方课程 / 实验详情域名和路径，并复用现有 URL / 分类 / 字段校验。
- 唯一运行时代码适配：资源 save / permissions / publish 可复用调用者事务，默认接口行为不变。导入复用现有审计、权限快照、版本与发布规则，不手写另一套发布逻辑。
- 本批用途明确为系统可见、允许模型推荐；伙伴外发权限保持关闭。没有调用真实模型。

## 工具与数据保护

抓取：`node scripts/fetch_huawei_resources.cjs <私有输出目录> [--reuse]`。使用普通未登录浏览器读取公开页面；支持复用页面 / 成功详情缓存。

预演：`.venv/bin/python scripts/import_huawei_resources.py <catalog.json> --report <私有报告路径>`。默认只读数据库。

写入须显式增加 `--apply --actor <现有管理员ID> --backup-dir <新的私有备份目录>`。沿用 `.isolation/runtime/dev/environment.json`，仅允许本机 banfei_agent 的既有 schema 16；先 pg_dump，再整批事务写入。没有 bootstrap / seed / 清库。

- 本次审计复用现有 admin 管理员，记录 create / permissions / publish / import。按来源官方 ID 生成稳定资源 ID；重复导入同时检查草稿和历史发布快照的来源，跳过已有资源，不覆盖管理员修改、下架状态或权限，不产生额外版本。
- 备份：`.isolation/resource-center/huawei-import/backup-20260925T063959Z/before.pgdump`。
- 抓取与报告：同目录下 `live/catalog.json`、`preview.json`、`import-result.json`、`repeat-preview.json`、`before-row-hashes.json`、`verification.json`，均在 Git 忽略目录。
- 导入前后核对原 38 张表的每行摘要，原数据无变更 / 删除。仅新增 enablement_resources 161 行、enablement_resource_versions 159 行、enablement_audit_events 642 行。原 13 条资源、案例、伙伴、用户、任务、方案及历史引用均保留。
- 重复预演跳过 129 门课程、32 个实验，新增 / 发布为零。撤回时优先按本批新增 ID 使用现有下架机制；不能用旧备份覆盖后续运行数据。

## 验证

- 后端 103 个不同用例通过：36 个 PostgreSQL 验证库用例，67 个 /tmp SQLite 兼容用例。其中新增导入专项 18 个，覆盖合并分类、同 ID 去重、来源参数清洗、HTML 文本、层级、冲突 / 失效草稿、权限、AI 候选、来源跳转、管理员修改保护、历史版本去重、失败全批回滚和重复执行。
- Playwright 4 项通过：课程实验目录 / 详情、分类和精简录入、来源跳转、案例交叉入口。使用专用 banfei_agent_test 临时 schema 和显式 replay，运行库没有 E2E 写入。
- 前端 typecheck、抓取脚本语法与 git diff --check 通过。本轮未修改前端代码，不重复 production build。
- 运行库只读核验 159 个发布引用的 system / model 投影与来源链接；模型投影不带 URL。多分类查询只返回同一条资源；新资源已可进入 AI 候选。该检查不调用模型，不新增业务任务。
- 测试证据：`/tmp/banfei-huawei-import-tests-final.xml`、`/tmp/banfei-huawei-import-last.xml`、`/tmp/banfei-huawei-import-browser.log`。
- 验证后通过正式工作区的 enablement-dev.sh 恢复 3000/8000，供人工验收。


## 登录后详情补全（2026-09-25）

- 用户在新开的可见 Chromium 窗口手动登录后，复用该会话逐项读取原导入清单，不导出 Cookie / Token，不读取密码，不点击报名、视频播放或开始实验。
- 129 门课程全部取得详情：111 门有课程目标，112 门有目标学员，105 门有大纲，129 门有专属封面链接；126 门简介得到更新，17 门名称以官方详情为准。页面未提供的目标、大纲和时长不推断，不将教材或视频下载到伴飞。
- 31 个实验再次按官方 experiment_id 核对，其简介、目标与基本要求、时长与首次导入一致，无需改写；“大数据全栈开发实战”（20008179）登录后仍不可用，保持原草稿。
- 原名称冲突课程 C101749708981178140 的详情标题为“数据仓库工作级开发者认证”，据此解决目录名称差异并发布；保留同一个 resource_id 和原有两个岗位分类。此次详情补全后，本批共 129 门课程、31 个实验发布，1 个实验草稿；该失效草稿随后按用户要求删除，见下节。
- 现有 schema 16 和精简 ResourceMetadata 足够容纳内容，没有新增表、字段、页面或接口，也没有改动前端或案例。封面仅保存官方 CDN URL。

工具：`scripts/fetch_huawei_resource_details.cjs` 导出 `captureDetails(context, manifestPath, outputPath)`，接收用户已登录的 Playwright context；按原 resource_id 断点续读，仅保存白名单元数据。兼容独立标题区块和旧富文本详情两种布局。公开目录采集器同时修正 source_page 取值为目录页，避免来源记录误用课程地址及其查询参数。

预演：`.venv/bin/python scripts/enrich_huawei_resources.py <首次 import-result.json> <details.json> --report <私有报告路径>`。

写入仍需显式 `--apply --actor <现有管理员ID> --backup-dir <新私有目录>`：先备份，再复用既有 save / publish / audit 完成整批事务。只允许补全原批次、原官方来源的已有资源；不新增资源、不改分类和权限，不覆盖管理员改动，不重新发布已下架资源。已有未发布人工草稿或被方案 / 运行快照引用的资源仅补草稿，避免推进发布版本使历史引用失效。本次没有命中这些保护分支。

- 本次写入：原有 129 个课程行更新，新增 129 个不可变发布版本、387 条 edit / publish / enrich 审计；资源总数仍为 174。31 个实验内容未变，重复预演对 160 个可用资源均为 unchanged，新增修改 / 发布为零。
- 备份：`.isolation/resource-center/huawei-import/details/backup-20260925-authenticated/before.pgdump`。同目录上层保存 details.json、preview.json、import-result.json、repeat-preview.json、before-row-hashes.json 和 verification.json，全部 Git 忽略。
- 前后摘要核对：35 张其他表完全未变，45 个未更新资源完全未变，原有发布版本和审计未改写 / 删除，所有资源权限与授权 epoch 不变；schema 仍为 16。160 个可用资源的普通展示、模型投影与外跳 URL 校验通过，模型投影不带 URL；现有 AI 候选检索可使用补充内容，未调用真实模型。
- 回退应逐条以旧快照保存新草稿，并经现有发布流程处理；不删除新增版本或用整库备份覆盖后续业务数据。

本轮验证：专用 PostgreSQL 验证库 55 项通过（导入、详情补全、资源中心），Node / Playwright 离线抓取测试 4 项通过（两种 DOM、缺失字段、实验 ID 和字段白名单、凭据链接拒绝）。覆盖重复执行无写入、事务回滚、管理员编辑 / 下架保护、历史引用保护、权限保持和原版本不变。证据：`/tmp/banfei-huawei-details-tests.xml`。无运行库 E2E 写入；运行库只执行上述已授权的详情补全事务，其他验证只读。3000 / 8000 保持运行。


## 按用户要求删除失效实验（2026-09-25）

- 删除“大数据全栈开发实战”（官方实验 ID 20008179，resource_id `f4151533-4e89-5456-a05f-c79eec267837`）。删除前核实仍为未发布草稿，没有发布版本、方案、任务、跳转或其他业务引用。
- 先备份，再在同一事务中删除该 1 条资源并追加 1 条 delete 审计；原 3 条导入审计及全部其他资源、案例、业务历史均保留。事务内逐表摘要核验只发生上述两项变化，提交后确认资源已不存在，schema 仍为 16。
- 当前此批保留 129 门课程、31 个实验，均已发布；全库课程/实验资源总数为 173（含原有 13 条）。原抓取清单和报告保留为历史证据，后续重导不得将该已确认失效的条目重新导入。
- 备份及删除核验：`.isolation/resource-center/huawei-import/delete-unavailable-20260925T092546Z/`。没有新增删除接口或改动功能代码，未 commit / push / deploy。
