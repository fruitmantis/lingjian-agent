# 原始资料驱动画像及 PostgreSQL 召回验收（2026-10-06）

## 范围与当前状态

经本轮后续指令授权，在原 WSL 项目 /home/yuan/project/lingjian-agent-enablement 的 main 分支实施两项优化。HEAD 仍为 0fda85cd9ab6860c1736007d879f3b8645cf5268；改动未提交、未推送、未部署云端。未访问或修改 AgentArts 工作树及已停云机。原有八处未跟踪产物目录保留。

这是实现者的验证记录；父任务负责独立验收。本轮后续授权聚焦画像溯源及召回，没有将它冒充为早先前端动效的独立验收。

## 最终行为

- profile_sources.py 按来源种类、ID、指纹保存每份原始资料的章节事实贡献。原 Word 本地解析为十章基线；其他资料模型只看该份原始缓存，贡献须逐字来自原文并保留同段及相邻限制。
- 新增、替换、删除在原写事务中同步撤回过期贡献，并从当前有效来源重建。双来源共有事实在删除单一来源后保留；同 ID 替换或删除后的旧异步结果不能恢复旧事实。
- 不以历史合成报告、旧简介或 240 字匹配摘要作事实输入。旧数据保留；公司介绍从第一章派生；标签与其他权限保持。
- 普通用户可见十章及隐藏资料的业务事实；后端过滤来源标识、原件名、链接和附件标识，管理员保留来源状态及错误。原第十章日期、主体、自述及待核实限定保留。
- PostgreSQL 对当前完整贡献/标签进行关键词召回，再调用一次模型评审候选；删除全量伙伴模型初筛及独立摘要。稀有尾部能力可进入十二个候选，软条件不作硬过滤。
- 答案、卡片、依据和供给状态由同一已校验结果形成；被拒绝伙伴不能继续出现在模型原始总述里。普通用户读取历史任务时也过滤现时隐藏来源标识，但不改写任务历史或用户原始需求。
- 失败、待处理及缺失状态明确显示，已撤回事实不作为最新画像。启动中断的来源处理转为失败，可按来源重试。

## 迁移与回退

本地 schema 19 → 20 已完成，采用加表及保留式迁移。私有备份：

/home/yuan/project/lingjian-agent-enablement/.isolation/profile-sources/20261006T082247Z/before.pgdump

pg_restore --list 已验证备份；目录0700、文件0600。迁移结果在同目录 result.json。先备份再在事务中执行DDL和本地 Word 初始化，不调用模型。179条伙伴及其他业务表数量保持，179份旧派生字段归档保存。

最后只读核对：schema20；73个 Word 来源 ready、1个案例描述 ready、3个普通文档 pending。106个伙伴没有可用原 Word，本次不以旧报告补造事实。三份现有普通文档仍待来源分类，未为验收把真实资料发送给模型。这是现有数据覆盖限制，管理员页面如实显示待处理。

回退函数为 backend.app.profile_source_schema.rollback(conn)，在现有数据库事务中调用；它恢复迁移前 ai_profile/intro/profile_materials_revision/profile_updated_at，把版本设回19，保留贡献表、原始材料、任务、标签和归档。回退后须配合恢复 schema19 的上一版应用，不能让当前要求 schema20 的应用连接 schema19。隔离测试已验证回退及再次应用；未对真实库执行回退。不删除业务记录来强行回退。

## 自动检查

相关七个测试文件合计 **109 passed**（119.09秒；仅既有 PyPDF 弃用告警）：

~~~text
backend/tests/test_profile_report.py
backend/tests/test_profile.py
backend/tests/test_partner_match_stages.py
backend/tests/test_partner_materials.py
backend/tests/test_partner_materials_admin.py
backend/tests/test_match_reasoning_budget.py
backend/tests/test_model_config.py
~~~

前端 npm run typecheck 通过。独立 QA 指出的两项问题已修正：隐藏案例标题与能力同名时不得抹除能力；普通用户第十章必须保留原有日期和限定。修正后的 test_profile_report.py 与 test_partner_match_stages.py **19 passed**（32.67秒），另含历史任务隐藏来源过滤回归。没有声称修正后整组109项再次同批运行。

测试复用现有 backend/tests/postgres_support.py 与 backend/tests/support/model_test_boundary.py：本地专用 banfei_agent_test、每次随机 validation_<32hex> schema、合成 Word/文本、临时上传目录；结束只删除自己的 schema。测试默认禁止外部网络。私有测试 DSN 从 .isolation/runtime/dev/validation-environment.json 读入，不打印值。运行方式：在项目虚拟环境中私下装载该测试配置，再执行 pytest -q 后接上述文件；前端在 frontend 目录执行 npm run typecheck。

关键覆盖：Word表格/十章/日期及限定；旧AI/intro/summary不作事实；新增相关章节；隐藏业务事实参与召回；唯一/共有事实删除；同ID替换；替换或删除后的晚到结果；失败撤回及重试；超过十二个干扰伙伴中的稀有能力；相邻否定；可逆迁移；无效伙伴总述/卡片/供给一致；先落库再理解；普通历史任务来源过滤。

最终 git diff --check 通过。最后只有迁移脚本说明及末尾空行修正，无行为变更。

## Windows 浏览器与真实模型

实际使用用户电脑 Windows Edge；所有写交互在临时当前代码快照、隔离 PostgreSQL schema 和合成资料中执行。标准入口始终 HTTP80，临时服务结束通过既有管理脚本恢复原服务；私有配置摘要前后相同。没有在真实业务库种测试数据。

| 检查 | 结论 | 证据 |
| --- | --- | --- |
| 管理员正常登录及 Word 原件上传 | 通过 | isolated-admin-word.png |
| 新增隐藏资料后自动更新第五章，普通用户看到十章及事实，不显示原件名/标题 | 通过 | isolated-user-hidden-facts.png、browser-done.json |
| 同一文件ID替换：旧能力撤回，新能力自动出现 | 通过 | isolated-replacement.png |
| 删除附件：两项旧能力都不恢复；其余Word/案例事实保留 | 通过 | isolated-deletion.png |
| 普通用户创建匹配任务，实际两阶段模型返回；卡片、回答、限制及“部分满足”一致 | 通过 | isolated-real-matching.png、attempt6-runtime-result.json |
| 标准服务恢复后原普通用户会话只读查看十章和第十章日期/免责声明 | 通过 | Windows本地产物 standard-verified-ten-chapters.*、standard-verified-disclaimer.* |
| 全项目测试、全部179伙伴语义人工核验、云端部署验收 | 未验证 | 本轮未扩大范围 |
| 早先前端动效全量验收及能力发展全交互 | 本轮未重新验收 | 本轮后续授权聚焦画像溯源及召回；相关发展投影类型/适用测试已覆盖 |

本轮累计四个逻辑真实模型阶段，仅使用合成材料及需求：首次 Contribution（444输入字符，attempt3）；MatchUnderstanding（1100）及 MatchAnswer（3864，attempt6）；替换 Contribution（449，live-final）。后三阶段记录 retry_count=0；首次阶段未记录重试数，因此不把四个逻辑阶段说成精确四次网络请求。首次Word导入、删除均无需模型。沿用现有模型及安全网络配置。

中间浏览器执行曾因文件标签选择器、首次Key提示、开发SSE的networkidle等测试工具问题失败，保留原始记录；实际真实模型结果已分别成功。匹配结果截图清晰，最终完整资料链浏览器结果通过。最后一次只为补拍清晰证据，模型入口禁止真实调用、使用合成来源贡献回放；source-runtime-result.json 显示零模型请求预算、浏览器通过、原服务恢复及配置未变。不会把回放冒充额外真实模型验证。

合成截图和结果位于本目录 evidence/profile-sources-20261006/，附SHA256清单。真实标准页截图仅保存在用户电脑本地证据目录，未拷入仓库：

C:/Users/juan/Documents/Codex/2026-10-01/task/profile-source-review

## 安全复现与交接

1. 用原Word固定十章的合成测试样本；在专用随机schema创建单一合成伙伴及测试管理员，不动真实伙伴。
2. 管理员导入Word；新增隐藏资料并上传 synthetic-first.txt；普通用户第五章应出现 BrowserQuasar 及“不支持境外交付”，同时原件名/资料标题不可见。
3. 替换同一附件为 synthetic-replacement.txt；第五章应只有 ReplacementQuasar；删除该附件后两者均消失，其余章节原日期和口径保留。
4. 合成需求“用于国内项目交付；不用于境外交付”创建匹配，验证只发生需求理解及候选评审，无全伙伴初筛；回答/卡片/供给一致。真实模型测试需保持已有授权预算；仅UI复查应使用明确标注的贡献回放。
5. 如切换标准服务，用 bash enablement-dev.sh status 核对归属并检查无在途任务，仅用现有 init/start/stop，finally恢复；不得手工杀进程或与其他任务共用 .next。

2026-10-06 08:57UTC最后运行核对：backend/frontend/Caddy均运行且由原管理器拥有，匹配及发展在途数量均为0；/partners 与 /api/health 经HTTP80返回200；3000/8000/5432为127.0.0.1监听、80公开。标准浏览器08:57:56UTC读到全部十章，08:58:07UTC实际滚至第十章并截图，原2026-09-24日期和免责声明保留。

没有未解决的代码测试失败。需要业务后续处理的范围是上述106个无Word伙伴及3份pending文档；父任务可依据本记录继续独立审阅并决定下一步。未提交、未推送、未部署。


## QA收尾与只读补查（09:31UTC）

- 父任务独立最终19/19通过；按其追加要求，仅普通伙伴页区分pending“资料待管理员处理”、processing“资料处理中”。没有启动真实资料处理。npm run typecheck与独立目录npm run build通过，原.next未与构建争用。
- 标准服务PID未变，前端next dev正常热更新；原前端编译产物含两条新文案，正常Edge会话实际读取pending伙伴并显示待管理员处理。09:30UTC健康/伙伴页HTTP80为200、schema20、无在途任务、迁移后新增匹配/发展任务0；三份document pending更新时间仍为08:22:50。
- 旧standard-final-ten-chapters.png被QA识别为Codex窗口，撤销其页面截图证据地位、保留原文件。已新拍standard-verified-ten-chapters.png、standard-verified-pending.png、standard-verified-disclaimer.png；截图前后确认Edge前台句柄，逐张亲自检查像素确为标准IP页面。对应JSON记录十章标题、地址、前台检查和零模型调用。
- 无Word的106个伙伴迁移前ai_profile非空数量0，旧intro非空21；当前全部missing。能力标签非空21、正式行业3、正式区域3；无案例/后续文档/ready贡献。缺失页标明暂无原资料、十章为未提供；名称/标签仍可参加本地召回，不能据此确认能被模型推荐或满足需求。只做聚合计数，未读这106个伙伴业务正文或调用模型评审。
- 三份普通文档的原文缓存均ready且非空、无原生错误；不是原文待提取或解析失败，而是迁移按授权未向模型发真实材料，所以章节贡献待分类。来源状态仍为pending、错误为空、更新时间未变。初始化和启动恢复代码不会自动发这些资料。
- 标准实际证据包含IP的/partners HTML及/api/health 200、正常会话的/partners/{id}与/api/partners/{id}成功（后端access日志为去/api前缀后的/partners/{id} 200）。本次新增pending伙伴的真实标准页面验证；没有把隔离合成匹配截图说成运行库真实伙伴的模型验证。
- 完整只读补查在用户电脑readonly-clarification.json、readonly-runtime-proof.json、status-followup-proof.json。合成清理盘点在SYNTHETIC_CLEANUP_REVIEW_20261006.md及synthetic-cleanup-inventory.json；九个本轮schema已清理，22个合成上传/预览文件待父任务统一确认后清理，历史四个schema有保留记录，第五个归属不明。未执行删除。

## 用户授权收口（永久删除22个合成文件及提交推送）

用户已明确确认永久删除已核准22个合成文件，并提交推送本轮main改动。按原清单复核身份、类型、哈希与正式库引用为0后，仅逐一删除7DOCX、8TXT、7PDF，22个路径均已不存在。没有删除目录、历史验证schema、源码测试夹具、既存证据、真实业务或迁移备份；没有写数据库。

删除结果及逐文件哈希位于用户电脑synthetic-cleanup-preflight.json、synthetic-cleanup-result.json；历史清理清单中的待确认项目继续保留。九个本轮验证schema此前已由测试流程清理，并未重建或再DROP。

本轮提交定向纳入30个源码/相关回归/说明文件；既存未跟踪证据目录及本轮原始截图、合成采集资料仍留本机，不提交私有环境、凭据、真实资料或临时上传。完整提交哈希、远端一致性和CI查验结果将记录在本机git-closeout.json；本验收记录中的早先“未提交”陈述对应当时检查时点。
