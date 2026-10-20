# 2026-10-17 全仓只读代码审查

审查对象：`/home/yuan/project/lingjian-agent-enablement`（分支 `main`）。
基线：提交 `27194f5`（2026-10-16 23:40）+ 33 个已修改未提交文件 + 1 个未跟踪新用例 `frontend/e2e/recommendation-labels.spec.ts`。
审查时间：2026-10-17 23:30 至 00:10（Asia/Shanghai）。
方式：**只读**。未修改产品代码，未运行 pytest 或 Playwright，未调用模型，未启停服务，未 commit 或 push。

## 结论

- P0 / P1：**未发现**。
- P2：1 项 UI 缺陷、2 项架构风险。
- P3：4 项改名残留、3 项仓库卫生问题。
- 覆盖方式：精读 12 个文件约 1,800 行，集中在鉴权、存储、启停、前后端契约；其余做全仓静态扫描与抽样。未逐行读完全部 39,860 行。

每条结论均注明 `文件:行号`。未亲自读到或未执行的内容列入「未覆盖范围」，不作推断。

## 一、P2 缺陷与风险

### P2-1 `FailureNotice` 静默丢弃 `title` 与 `stages`

`frontend/components/task-failure.tsx:16` 的参数解构：

```ts
({details,message,operation,impact,partial,children})
```

类型签名里声明了 `stages?:string|null` 和 `title?:string`，函数体中均未使用。而 `frontend/components/task-detail.tsx:188` 同时传入了这两个属性：

```tsx
<FailureNotice ... stages={task.lastErrorStage} partial={task.recommendations.length>0}
  title={task.recommendations.length>0 ? "部分完成 · 伙伴推荐可用" : "本次匹配未完成"}
  impact={...}>
```

影响：任务处于 `partial` 时，页面只显示兜底文案「本次处理失败，请重试。」，`title` 中准备好的「部分完成 · 伙伴推荐可用」从不渲染，`stages` 也不会显示。数据层已按 AGENTS.md 保存并保留可用推荐，展示层却把「部分完成」表达成整体失败。

该缺陷不会让测试变红：`frontend/e2e/task-failure.spec.ts:44` 正把兜底文案断言为期望值。

建议（本次未执行）：补全解构并渲染 `title` / `stages`，增加 partial 状态下标题的断言。`FailureReasons` 同样声明了未使用的 `stages`。

### P2-2 所有已认证请求的身份校验段共用一把排他锁

- `backend/app/auth.py:79`：`require_user` 对所有已认证请求调用 `conn.lock_writer()`。
- `backend/app/postgres_storage.py:69`：该锁是 `pg_advisory_xact_lock`，键为 `database.schema`，单键排他。
- `backend/app/auth.py:98`：每个普通用户请求都会执行 `UPDATE users SET last_active_at`，即每个请求都构成一次写事务。

影响：所有已认证请求在**鉴权段的数据库访问**上串行排队（锁在 `require_user` 退出提交时释放，不覆盖整个业务请求），且每个普通用户请求写一行 `users`。单机 MVP 可以运行，但并发上限由此固定，慢查询会阻塞其他请求的鉴权。

说明：这是既有设计选择，不是 bug。此处记录，便于后续多进程或 ARM 扩容时评估。

### P2-3 后台任务失败只写 stdout，不进入管理员错误面板

`backend/app/routers/match.py`：

```python
952:  print(f"[WARN] demand profile generation failed for task {record_id}", flush=True)
959:  print(f"[WARN] tag suggestion generation failed for task {record_id}", flush=True)
1060: print(f"[WARN] background processing failed for task {record_id}", flush=True)
```

项目已有 `error_diagnostics.record_error` 与 `GET /admin/system/errors`，上述三处未使用。`match.py:949` 的 demand_profile 分支虽然把失败写入 `failures`，异常对象本身同样未进入 `errors.jsonl`。

影响：任务详情可显示失败状态，但后台进程级异常（例如 `_execute_match` 在落库前失败）只存在于服务器 stdout，管理员「任务报错」面板看不到。输出内容仅含 `record_id`，不涉及敏感信息，属可观测性缺口。

## 二、P3 改名残留

本批改名（`智能匹配`→`智能推荐`、`匹配任务`→`伙伴推荐任务`）已提交部分为 33 个跟踪文件，另新增 1 个 124 行用例 `recommendation-labels.spec.ts`（10 个用例），覆盖历史列表、设置归一化、旧场景链接、原文保留、系统状态、删除阻断、scope 模板、推荐分、进度文案、后台统计与来源卡。后端 diff（404 文案、`STAGES`、删除标签、模块名、OpenAPI description）一致。以下为未覆盖处：

| 编号 | 位置 | 内容 | 影响 |
|---|---|---|---|
| P3-1 | `frontend/lib/skills.ts:2,46,48,98,102` | 整份模块全仓无引用（仅自引用 `SKILL_CATEGORIES` / `SKILL_REGISTRY` / `SKILLS_BY_ID`），仍保留 `"智能匹配"`、`name:"伙伴智能匹配"`、`inputDefinition:"项目需求及匹配结果"` | 死代码，误导后续维护 |
| P3-2 | `frontend/components/task-detail.tsx:44-58` | `taskStatusText.partial/failed` 不可达（188 行条件已排除这两态）；`errorStageLabels` 与 `errorStageText` 无调用点，且 `partner_match:"伙伴匹配"` | 死代码 |
| P3-3 | `backend/app/routers/capability_tags.py:321` | 410 文案「标签建议随匹配任务生成，请查看已有建议」 | 调用方可读到旧称谓 |
| P3-4 | `backend/app/storage_defaults.py:47` | 新库 seed 的 `model_usage_configs.scene_name` 仍为「智能匹配」「伙伴能力发展」 | 实际无害：`agent_settings.py:82` 首次启动会删除这些行 |

附带维护风险：失败环节标签存在**三份副本**——`backend/app/task_failures.py:10`、`frontend/components/task-list.tsx:27`、`frontend/components/task-detail.tsx:51`。本批只更新了前两份。

## 三、P3 仓库卫生

| 位置 | 问题 |
|---|---|
| 仓库根 `progress` | 空文件，且未跟踪 |
| `docs/validation/` 下 23 个证据目录 | 未跟踪；`.gitignore` 仅覆盖 `.isolation/` 与部分 `artifacts/`，每次 `git status` 产生 24 条噪音 |
| `.gitignore` 中 `frontend/app/**/page.ts` | 实际页面均为 `.tsx`；若有人新建 `page.ts` 会被静默忽略，疑似笔误 |

另：`docs/validation/README.md` 文首「更新日期：2026-10-13」与文件修改时间 2026-10-15 不一致；`CLOSEOUT_20261015.md` 只在正文中被引用，未进入顶部「当前入口」表。

## 四、已核对且未发现问题的项

以下为实际读取代码后确认的结论，用于界定本次审查的正面范围：

- **进程安全**（`backend/scripts/enablement_environment.py:157-185`）：`owned()` 同时核对 `/proc/<pid>` 的 uid、启动时间、逐字节 `cmdline` 与 `cwd` 是否位于项目根目录；仅对 `getpgid(pid)==pid` 的自有进程组 `killpg`；50 次轮询后仍未退出则报错，不扩大终止范围。
- **测试隔离**（`backend/tests/postgres_support.py`）：随机 schema 名，`CREATE SCHEMA` 不带 `IF NOT EXISTS`，只 `DROP` 本次调用创建的 schema。
- **身份体系**（`backend/app/routers/local_identity.py`、`backend/app/identity_keys.py`）：Origin 严格校验、4 KB body 硬上限、`bf_[A-Za-z0-9_-]{43}` 格式校验、SHA-256 摘要加 Fernet 密文、登录时轮换浏览器凭据、注销后不发放新 Token。
- **同源代理**（`frontend/next.config.*`、`frontend/app/api/[...path]/route.ts`）：目标硬校验必须为 `http://127.0.0.1:8000`，过滤 hop-by-hop 头，处理 abort 与流式响应体。
- **结构校验**（`backend/app/postgres_storage.py:101-123`）：拒绝自动升级，逐项校验 schema 版本、`last_error_details`、`profile_chapter_meta`、`last_active_at` 及已废弃的 `timeout_columns`。
- **迁移幂等**（`backend/app/agent_settings.py:72-84`）：已有配置直接返回；旧名仅在读投影 `_display_settings` 中映射，从不回写。
- **迟到写入保护**（`backend/app/routers/match.py:855`、`900-916`）：`_set_task_state` 以 `expected_run_id` 拦截旧执行结果；`_claim_task_retry` 使用 `UPDATE ... WHERE task_status=?` 加 `rowcount` 判定并发。
- **静态扫描**：`backend/app` 中 50 处 `except Exception` 无一处为 `pass` 或静默 `return None`；未发现 `shell=True`、`os.system`、`pickle`、`verify=False` 或裸 `except:`；`frontend` 未发现 `console.log` 或 `debugger`。
- **占位符转换**（`backend/app/postgres_storage.py:46-58`）：`?` 转 `:pN` 时按引号切分，跳过字符串与引号标识符内容。

## 五、已知但本次不视为缺陷的边界

- `bind_parameters` 未覆盖 PostgreSQL dollar-quoted 字符串（`$$...$$`）与 SQL 注释；一旦出现会因参数个数不匹配抛出 `ValueError`。属 fail-fast，且当前全仓无此类参数化调用。
- `Connection.execute` 依据语句首词判断是否加写锁，`WITH ... INSERT` 可绕过。当前全仓 `WITH` 语句均为只读查询，未构成实际风险。

## 六、运行状态

- 2026-10-17 23:34 的服务重启由用户要求 Codex 执行，非本次审查操作。
- 当前 `127.0.0.1:3000` 为 pid 110221、`127.0.0.1:8000` 为 pid 110170，工作目录均在正式目录内；80 端口由 Caddy 监听。
- 后端源码最后修改为 2026-10-17 11:43，前端为 11:44，均早于 23:34 的服务启动时间，运行实例已加载本批改动。
- 由此，根目录 README 第 7 行「现有后端进程未重启」自 23:34 起不再成立，建议下次更新该句。
- 旧会话记录的 pid 37749、37711 已退出。

## 七、未覆盖范围

| 范围 | 状态 |
|---|---|
| `backend/app/routers/match.py`（1,279 行） | 仅精读 770-1080 与鉴权、状态写入段；召回、详评、来源校验主体未逐行读 |
| `partner_match_context.py`(680)、`profile_sources.py`(637)、`development_engine.py`(392)、`profile_report.py`(129)、`material_files.py`(290) | 未读 |
| 91 个后端测试、52 个 e2e | 未运行。需专用 PG 验证库并停服，本次未获授权 |
| 前端 41 个页面与组件 | 抽查 6 个 |
| 真实模型链路、LibreOffice 转 PDF、Excel 导入导出、十章画像合并 | 未验证 |
| ARM 部署与 systemd 路径 | 仅读代码，未接触环境 |

因此本报告不构成全量通过结论，也不能替代工程验收与业务验收。

## 八、复现用到的命令

```bash
# 基线
git -C /home/yuan/project/lingjian-agent-enablement log -5 --date=format:'%Y-%m-%d %H:%M' --pretty='%h %ad %s'
git status --porcelain | wc -l
git diff --stat

# 改名残留
grep -rn --include=*.py --include=*.ts --include=*.tsx -E "智能匹配|匹配任务|本次匹配|伙伴匹配" \
  backend/app frontend/app frontend/components frontend/lib

# 死代码
grep -rn --include=*.tsx --include=*.ts "SKILL_CATEGORIES\|SKILL_REGISTRY\|SKILLS_BY_ID\|lib/skills" frontend

# 异常与危险调用
grep -rn --include=*.py "except Exception" backend/app | wc -l
grep -rn --include=*.py -E "shell=True|os\.system|verify=False|pickle|\beval\(" backend/app

# 服务归属与时间
ss -lntp | grep -E ':(3000|8000|5432|80) '
stat -c %Y /proc/110221
```

## 九、建议优先级

1. **P2-1**：唯一影响用户可见信息的真实缺陷，改动最小。
2. **P2-3**：补 `record_error`，使后台失败进入管理员面板。
3. **P3-1 / P3-2**：删除或更新死代码，避免下次改名继续漏。
4. **P2-2**：仅记录，扩缩容前再评估。

以上 1 至 4 项本次均未执行任何代码修改。

---

# 第二轮：四步定向审计（2026-10-18 00:10）

范围：文档承诺对账、接口契约对账、伙伴档案拼接、推荐证据链、上传与解析安全。
方式：只读。未修改代码，未运行 pytest 或 Playwright，未调用模型，未启停服务。
方法：AST 解析全部路由的鉴权依赖；正则提取前端调用形态；逐函数精读；未执行任何写操作。

## 2.1 文档承诺对账

抽取 19 条可验证承诺逐条比对代码：

| 文档承诺 | 实现位置 | 结论 |
|---|---|---|
| 数据库 schema 20，拒绝自动升级 | `postgres_storage.py:110` | 一致 |
| 公开入口仅 5 个 | 全量 AST 解析 | 一致，恰好 5 个 |
| `/admin/*` 全部后端校验 | 同上 | 一致，0 例外 |
| 上传仅 6 种格式 | `shared/partner-materials.json` | 一致 |
| 不接 OCR | `doc_extractor.py:1` | 一致，无 OCR 依赖 |
| 3 大类 / 18 二级分类 | 同上字典 | 一致，3 / 18 |
| 12 个行业 | `shared/business-taxonomy.json` | 一致，12 |
| 画像固定十章 | `profile_report.py:6` | 一致 |
| 模型输入上限 25000 字符 | `partner_match_context.py:19` | 一致 |
| 超时 300 秒、重试 3 次 | `agent_settings.py:22` | 一致 |
| Excel 2000 条 / 10 MB | `resource_transfer.py:17` | 一致 |
| Excel 不执行公式 | `resource_transfer.py:113` | 一致，且显式拒绝公式单元格并报行号 |
| 反馈 5000 字 / 5 图 / 5MB / 2500 万像素 | `feedback.py:19-65` | 一致 |
| JWT 至少 32 位、无弱回退 | `config.py:23-27` | 一致 |
| 5 次失败锁 15 分钟 | `users.py:36` | 一致 |
| 错误日志保留 50 条 | `error_diagnostics.py:175` | 一致 |
| 上传上限 20 MiB | `file_storage.py:12` | 一致 |
| 仅 PostgreSQL | `postgres_storage.py:18` | 一致 |
| 章节元数据 1–9 章 | `profile_sources.py:197` | 一致 |

结论：未发现「文档写了但代码未实现」。

## 2.2 接口契约

- 后端共 130 个路由。
- 前端调用但后端不存在的接口：**0 个**。脚本初报的 4 条经逐条核对均为正则解析伪影（`/health` 定义于 `main.py`，其余为模板字符串被截断）。
- 反向的「后端有但前端未调用」初报 61 条，不可信：大量请求路径由变量拼接，正则无法覆盖，故不作为结论。
- AST 审计：无鉴权依赖的路由仅 `POST /auth/identity/session`、`POST /auth/identity/key/login`、`POST /auth/identity/logout`、`POST /auth/admin/login`，加 `main.py` 的 `GET /health`，与 AGENTS.md 的公开入口清单完全一致。

## 2.3 伙伴档案拼接

结论：本仓实现最稳的部分。三道迟到写入保护均存在：

1. 单文件提炼：写回前重新取源并比对指纹，源被替换或删除则丢弃结果（`profile_sources.py:580-583`）。
2. 单章合并：写回前同时比对来源有效性、章节元数据与正文是否被他人修改，任一不符即跳过该章（`profile_sources.py:518-529`）。
3. 补摘要：额外比对 `sections_json` 内容（`profile_sources.py:616-623`）。

「新来源保留旧正文、仅标记待更新」由每章保存的输入指纹实现，不依赖时间戳。

**可议点（P3）**：隐藏来源标题的脱敏为关键词启发式（`profile_sources.py:111-121`），仅当标题出现在 markdown 链接、或紧跟在「来源/资料/文档/附件/案例/依据/参见/参考/根据」之后、或整行即为标题时才替换。裸写在正文中的标题不会被替换。实际风险低：合并输入仅含案例描述、不含标题。

## 2.4 推荐证据链

对号机制本身严格：来源编号必须在本次发送映射内，引用文本与偏移逐字校验，案例与交付物须归属该伙伴且当前 `visible`，保存时再次查库复核（`match.py:548-591`）。

**P2-4 证据字段可为空，校验层不兜底**
（本条修法已在文末《分歧与收敛》第三节修订：改为“四选一”依据规则，勿加 min_length。）

`backend/business/matching_types.py:49-51`：

```python
profileEvidence: list[str] = Field(max_length=5)   # 只有上限，无 min_length
evidenceCases: list[str]
evidenceDeliverables: list[str]
```

空列表可通过全部校验：`_source_assessment` 的循环不执行，`_references_valid([])` 返回 True，`kind` 正常返回，推荐被采纳（`match.py:517-534`）。

同类问题在整体分析上更宽：`matching.py:163` 以「`analysisRefs` 是否为列表」判定分析有效性，**空列表也算有效**；`match.py:664-670` 的 `all(...)` 对空集合返回 True，因此 `gapAnalysis` 可在零引用情况下以 `analysisComplete` 形式返回。

影响：「每条推荐都必须有证据」目前依赖提示词，服务端不拦截。建议（本次未执行）在 `profileEvidence` 与 `analysisRefs` 增加 `min_length=1`，或在 `_source_assessment` 中显式拒绝空引用。

## 2.5 上传与解析

已确认的防护：

- 文件名先剥离目录再入库，落盘名为 UUID，无路径穿越（`material_files.py:60,64`）。
- 非扩展名信任：PDF 校验 `%PDF-`；Office 校验压缩包结构，拒绝宏、拒绝 `..`、拒绝加密条目，限制 10000 条目与 200 MB 解压总量（`file_storage.py:43-69`）。
- 所有 Office XML 经 `defusedxml` 解析，阻断外部实体与实体膨胀（`file_storage.py:61-62`）。
- HTML 清洗使用 bleach，`attributes={}`、`protocols=[]`，链接、图片与事件属性全部剥离（`doc_extractor.py:29`）。
- 预览响应下发 CSP `sandbox; default-src 'none'; img-src 'none'`（`material_files.py:271`）。
- LibreOffice 以参数数组调用（无 shell 注入），独立用户配置，宏安全级别最高、禁用链接更新，120 秒超时（`material_files.py:117-133`）。
- 原件下载强制 `application/octet-stream` 且带 `nosniff`（`material_files.py:257-258`）。

**P3-5 解析无超时**：PDF 与 Office 文本提取在后台线程执行，除 20 MiB 文件大小外无时间或 CPU 上限，异常构造的文件可长时间占用线程池。内网环境下风险有限。

## 2.6 本轮新增问题

| 级别 | 问题 | 位置 |
|---|---|---|
| P2-4 | 证据字段可为空，推荐与分析可在零引用时通过校验 | `matching_types.py:49-51`、`matching.py:163`、`match.py:517-534` |
| P3-5 | PDF/Office 解析无超时 | `material_files.py:146` 等 |

## 2.7 本轮未覆盖

- 91 个后端测试与 52 个 e2e 未运行，需专用 PG 验证库并停服。
- `development_engine.py`、`development_lifecycle.py`、`partner_match_context.py` 的筛选算法仅读入口，未逐行。
- `material_files.py` 后半段、`model_config.py` 未审计。
- 真实模型、LibreOffice 实际转换、Excel 实际导入未执行。

---

# 第三轮：能力发展状态机与模型出口（2026-10-18 00:35）

范围：`development_lifecycle.py`（332 行，全读）、`development_engine.py`（392 行，全读）、`development_deadlines.py`、`development_model.py`、`model_config.py` 的连接保存与测试。
方式：只读。未运行测试，未调用模型。

## 3.1 状态机结论

Plan / Run / Version 的并发与恢复设计完整，未发现可丢失用户成果的路径：

- 版本写入前核对 `current_version_id == based_on_version_id`，乐观并发拒绝旧请求覆盖新版本（`development_lifecycle.py:236`）。
- `complete()` 在版本写入前后各校验一次超时，异常时整个事务回滚，不会留下半写版本（`:257-263`）。
- `save_answer()` 同时校验运行状态、执行令牌、`active_run_id`、`current_version_id` 与超时（`:143`）。
- `retry()` 要求被重试的运行必须是最新一次且状态属于 failed / partial / interrupted（`:318`）。
- `recover()` 先修复指向终态运行的 `active_run_id`，再中断过期运行，不创建新任务（`:278-295`）。
- 放弃能力发展的旧 current 版本仅在成功写入新版本时替换，失败路径不覆盖。

**撤回一条误判**：曾怀疑 `development_engine.py:325` 的看门狗使用当前超时设置而非受理快照。核对后，该调用位于 `agent_settings.execution_scope(run['input_snapshot']['agent_execution'])` 内（`development_engine.py:314`），`current_execution()` 返回的正是受理时快照，行为与 AGENTS.md 一致，不构成缺陷。

## 3.2 P2-5 上下文超预算时静默裁剪，无完成度标记

`development_engine.py:90-114` 在输入超过 60000 字符时按顺序裁剪：先清空画像章节与候选，再逐段落试装，再逐个恢复候选。整个过程不产生任何标记，最终生成的答复与"资料完整"时无法区分。

对照：匹配流程有 `analysisComplete` 与 `inputCoverage` 明示不完整（`match.py:690`），能力发展没有任何对应字段。用户与管理员都无法得知"本次建议是在缺少伙伴画像章节的情况下生成的"。

不影响数据正确性：引用仍限定在已发送范围内（`:116-119`）。属诚实性与可观测性缺口。

## 3.3 P2-6 模型连接 `baseUrl` 无主机校验

`model_config.py:124-134` 与 `:137-158` 在创建和更新连接时直接保存 `baseUrl`，不校验协议与主机。实际发起请求时仅拒绝内嵌用户名密码与非 http(s) 协议（`development_model.py:42-43`）。

后果：管理员可将某条连接的 `baseUrl` 指向任意地址，随后该连接携带 `Authorization: Bearer <key>` 发出请求（`development_model.py:53`）。对于使用环境变量密钥的连接（默认配置 `api_key_source='env'`、`api_key_env_name='LLM_API_KEY'`），管理员虽无法在界面读取该密钥，但可借修改地址把密钥发送到自控服务器。同时构成对内网地址的 SSRF（盲打，响应片段会进入管理员可见的错误诊断）。

已有缓解：`follow_redirects=False`、`trust_env=False`（`development_model.py:52`），阻断了重定向绕过与环境代理。

注：README 第 183 行「网络白名单仍限制为启用模型地址」在全仓无应用层对应实现（检索 `白名单/whitelist/allowlist` 无结果），若该句指应用层校验则不成立；若指部署侧出口策略，建议在文档中写明。

## 3.4 文档对账的补充修正

第二轮结论「19 条代码级承诺全部属实」维持不变。新增说明：README 的「网络白名单」一句无应用层实现，列入 3.3。

## 3.5 本轮新增问题

| 级别 | 问题 | 位置 |
|---|---|---|
| P2-5 | 能力发展上下文超预算静默裁剪，无完成度标记 | `development_engine.py:90-114` |
| P2-6 | 模型连接 `baseUrl` 无主机校验，可外发环境变量密钥并访问内网 | `model_config.py:124-158`、`development_model.py:53` |
| P3-6 | 开发检索与生成共用 60000 字符预算，与匹配的 25000 分属两套口径，文档未说明 | `development_engine.py:84` |

## 3.6 覆盖更新

- `development_lifecycle.py`、`development_engine.py` 本轮已全读，第一轮的「未覆盖」条目对本轮不再适用。
- `development_views.py`、`development_context.py`（102 行）、`enablement.py` 仍未逐行。

## 3.7 本轮未覆盖

91 个后端测试与 52 个 e2e 仍未运行；真实模型调用、LibreOffice 转换、Excel 导入未执行。

---

## 基线变更记录

审查期间仓库提交状态发生变化，记录如下，结论不因此改变：

- 2026-10-17 23:49 `ddf2236 fix: align partner recommendation labels and documentation`（34 个文件）提交了第一轮所称的「33 个已修改未提交文件 + 1 个未跟踪用例 `recommendation-labels.spec.ts`」。提交内容与审查时读到的工作区一致。
- 2026-10-17 23:51 `40e043c docs: reflect verified WSL recommendation status`（README.md 1 行）。
- 因此第一轮「基线：27194f5 + 未提交改动」应理解为 `ddf2236` 的父提交状态。第一轮列出的改名残留（skills.ts、task-detail 死代码、capability_tags 410 文案、storage_defaults 场景名）现已进入已提交树。
- 本文件（`docs/validation/INDEPENDENT_CODE_REVIEW_20261017.md`）为新增未跟踪文件，`docs/validation/README.md` 为修改，二者均未提交。

---

# 第四轮：召回、资源授权与账号删除（2026-10-18 01:05）

范围：`partner_match_context.py` 的召回与摘录选择（`recall_candidates`、`detailed_candidate`、`passage_selection`、`_normalized_spans`）、`enablement.py` 的三维权限、`user_cleanup.py` 的账号删除事务。
方式：只读。

## 4.1 召回与摘录选择

机制：PG 内用归一化后的词项做 TF-IDF 式排序取前 12 家（`recall_candidates`），命中位置映射回**未改动的原始字符串偏移**（`_normalized_spans`），再按原文段落组扩展、合并重叠区间，最后受 25000 字符预算约束（`assemble_details`）。

确认正确的点：

- 命中偏移回映射到原文，不复制、不改写原文，引用恢复不依赖模型复述。
- 预算不足时会记录 `omissions`（含具体原因）并写入 `inputCoverage` 与 `evidenceState`，最终体现为 `analysisComplete=false`。**推荐流程对「资料没给全」是有标记的**，这一点与第三轮 P2-5 形成对照。
- 只有标题、目录、页眉页脚类区段被标记为 `ancillary`，排在候选之后而不是删除。
- 案例按与需求的词项相关度排序，交付物按文件名相关度排序。

## 4.2 P3-7 若干未被使用的参数

| 位置 | 未被使用的参数 | 说明 |
|---|---|---|
| `partner_match_context.py:367` | `profile_budget: int = 900`、`case_count: int = 3` | 函数体未引用，实际预算由 `DETAIL_CHAR_LIMIT` 与 `assemble_details` 控制 |
| `partner_match_context.py:224` | `limit` | `passage_selection` 内部改用常量 `DETAIL_CHAR_LIMIT`，形参无效 |

不影响行为，但会误导后续按参数调优的人。

## 4.3 记录项：`file_path` 进入服务端快照

`detailed_candidate` 的交付物查询带出 `file_path`（`partner_match_context.py:474`），该字段随 `detail_rows` 存入任务快照并参与保存时的复核（`match.py:588-590`）。当前没有任何响应投影把它返回给前端，`provider_context` 与 `_public_source_aliases` 也只输出文件名。属内部留痕，非泄漏，建议后续确认快照清理策略。

## 4.4 资源三维权限

设计正确，且比文档描述更严：

- 发布时把 `system_visible` / `model_allowed` / `partner_allowed` 三个标志**冻结进版本元数据**（`enablement.py:226`），此后再授予权限不会让旧版本突然可见。
- 撤权时 `authorization_epoch` 自增（`enablement.py:204-208`），旧引用因 epoch 不匹配立即失效。
- 读取时同时要求**当前行的标志**与**版本冻结的标志**都为真，且按用途只检查对应维度（`enablement.py:266-268`），三个维度互不推导。

## 4.5 账号删除事务

单事务内完成：确认令牌校验（用途、目标、操作者）→ 在工作锁内复核操作者仍为有效管理员且 `token_version` 未变 → 复检"非本人、非最后一个可用管理员、无运行中任务" → 校验确认令牌中的版本号 → 将 Key 摘要转入 `revoked_identity_keys` → 删除浏览器凭据、challenge 与 Key 记录 → 置 `status='deleted'` 并自增 `token_version` → 写审计（`user_cleanup.py:68-100`）。

没有"删了一半"的中间态；业务数据与归属保持不变。

## 4.6 本轮新增问题

| 级别 | 问题 | 位置 |
|---|---|---|
| P3-7 | 三个函数参数未被使用，易误导调优 | `partner_match_context.py:224,367` |

## 4.7 覆盖更新

- `partner_match_context.py` 的召回、摘录、预算与排序已读；`_source_layout`、`_intro_ranges` 等版式判定函数未逐行。
- `enablement.py`、`user_cleanup.py` 已读。
- 仍未读：`development_views.py`、`development_context.py`、`enablement_catalog.py`、`case_content.py`、`partners.py`、`profile.py`、`feedback.py` 及全部前端组件。
- 测试仍未运行。

---

# 第五轮：读取路径与案例可见性（2026-10-18 01:30）

范围：`development_views.py`（186 行，全读）、`development_context.py`（102 行，全读）、`case_content.py`（29 行）。
方式：只读。

## 5.1 历史快照的活权限

`readable_payload` 在每次读取时重新校验依赖：来源撤权、`authorization_epoch` 变化、`system_visible` 关闭、画像来源失效，任一成立即整份方案隐藏并返回固定提示（`development_views.py:17-37,85`）。被隐藏时同时清空对话与原始需求，只保留目标伙伴与目标列表（`:105`）。符合「历史版本兼容、权限按当前状态判定」的约定。

`transferable`（伙伴可传递视图）逐项按 `partner` 用途解析，未获 `partner_allowed` 的资源直接跳过而非报错；生成文本再过一次外发校验（`:166-179`）。

## 5.2 继续追问的上下文边界

`development_context.load` 严格实现「只保留最近一组可授权读取的完整问答」：倒序找到第一条可读的交换后 `break`（`:82-86`），与当前正文相同的答复改为引用而非重复发送（`:85`）。资源顺序与身份以当前 Version 为准；`item_id` 缺失时按 `development_version_items` 的 ordinal 回填（`:10-15`）。

理解与生成共用同一份 `load` 结果，且用 `request_stamp` 在提交前后各校验一次，上下文或权限变化时拒绝保存（`development_engine.py:384-389`、`development_lifecycle.py:137,147`）。

## 5.3 案例可见性

三层一致：`visible_case` 要求案例 `visible` 且伙伴 `active`（`case_content.py:7-10`），`case_projection` 二次校验（`:19`），`projection` 对非模型用途附文件时使用 `public_file(..., False)`，不输出内部路径（`:14-16`）。

已保存方案中的案例文字在撤下后仍可读，文件与链接按当前可见性判定——与 README「已有任务文字保留可读，链接仍检查当前可见性」一致。

## 5.4 本轮结论

未发现新增缺陷。以下三处记录为观察项，不构成问题：

- `identified_payload` 依赖 `development_version_items` 的行数与 `stages` 结构完全对应；若存在无 `stages` 或条目数不匹配的历史版本，会抛异常。现有写入路径保证一致，未发现此类数据。
- `development_context.load` 每轮为计算 `stamp` 而全量读取 `enablement_resources` 与 `cases` 行（`:89-93`）。资源规模增长后是明显开销，属性能观察项。
- `detail` 中对话过滤依赖 `version_row` 必然存在；版本不删除，该假设当前成立。

## 5.5 覆盖更新

后端已读：鉴权与身份、存储层、匹配核心、画像来源、能力发展状态机与引擎、召回与摘录、资源三维权限、账号删除、读取路径、案例可见性。
后端仍未读：`partners.py`、`profile.py`、`feedback.py`、`enablement_catalog.py`、`material_files.py` 后半段、`resource_transfer.py` 解析后段、`user_cleanup.py` 前 68 行。
前端：仅抽查 6 个文件。
测试：仍未运行。

---

# 第六轮：前端身份与会话（2026-10-18 01:50）

范围：`frontend/components/auth-provider.tsx` 前 80 行（令牌、401 处理、身份创建），以及全仓 XSS 面与安全响应头检索。
方式：只读。

## 6.1 已确认

- 长期身份 Key 不写入浏览器存储；`localStorage` 只有 24 小时有效的 JWT、用户摘要与「已退出」标记（`auth-provider.tsx:24-38`），与 README「不把长期 Key 写入浏览器存储」一致。
- `apiFetch` 遇 401 会清除对应作用域的会话并跳转登录页，用户与管理员两个作用域互不覆盖（`:39-50`）。
- 并发创建身份时使用单一 Promise 去重（`browserCreation`），避免同一浏览器重复建号（`:72-80`）。
- 全仓无 `dangerouslySetInnerHTML`，React 默认转义，富文本注入面小。

## 6.2 P3-8 主应用未下发 CSP，令牌在 localStorage

应用页面没有任何 `Content-Security-Policy` 或同类安全响应头；CSP 只出现在文件预览响应上（`material_files.py:271`）。JWT 存于 `localStorage`，任何脚本都能读取，有效期为 24 小时。

当前风险有限：没有 `dangerouslySetInnerHTML`，前端不渲染用户提供的 HTML。但这是一条「一旦引入富文本就立即变成令牌泄露」的路径。属加固项，不是现存漏洞。

## 6.3 覆盖更新

前端 41 个页面/组件中，已读 `auth-provider.tsx`（80/291 行）、`api-request.ts`、`task-failure.tsx`、`task-detail.tsx`（部分）、`admin-panels.tsx`（片段）、`scenes.ts`、`skills.ts`。
其余组件未读：`development-assistant.tsx`、`enablement-workspace.tsx`、`partner-materials-manager.tsx`、`admin-demand-panels.tsx`、`task-list.tsx`、`task-navigation.tsx`、`task-progress.tsx` 等。

## 6.4 累计问题清单（截至本文件末尾）

| 编号 | 级别 | 问题 | 位置 |
|---|---|---|---|
| P2-1 | P2 | `FailureNotice` 丢弃 `title`/`stages`，部分完成显示为处理失败 | `task-failure.tsx:16` |
| P2-2 | P2 | 已认证请求的鉴权段共用一把排他锁，且每请求写一行 `users` | `auth.py:79,98` |
| P2-3 | P2 | 后台任务失败只写 stdout，不进管理员错误面板 | `match.py:952,959,1060` |
| P2-4 | P2 | 证据字段可为空，推荐与分析可在零引用时通过校验 | `matching_types.py:49-51` |
| P2-5 | P2 | 能力发展上下文超预算静默裁剪，无完成度标记 | `development_engine.py:90-114` |
| P2-6 | P2 | 模型连接 `baseUrl` 无主机校验，可外发环境变量密钥并访问内网 | `model_config.py:124-158` |
| P3-1 | P3 | `skills.ts` 整份死代码且称谓未更新 | `frontend/lib/skills.ts` |
| P3-2 | P3 | `task-detail.tsx` 状态文案与失败环节标签为死代码并含旧称谓 | `task-detail.tsx:44-58` |
| P3-3 | P3 | 410 文案仍写「匹配任务」 | `capability_tags.py:321` |
| P3-4 | P3 | 新库 seed 的场景名仍为旧称谓 | `storage_defaults.py:47` |
| P3-5 | P3 | PDF/Office 解析无超时 | `material_files.py:146` 等 |
| P3-6 | P3 | 发展检索与生成 60000 字符预算与匹配的 25000 分属两套口径，文档未说明 | `development_engine.py:84` |
| P3-7 | P3 | 三个函数参数未被使用 | `partner_match_context.py:224,367` |
| P3-8 | P3 | 主应用未下发 CSP，JWT 存 `localStorage` | 全局 |

## 6.5 尚未覆盖（累计）

- 后端未读：`partners.py`、`profile.py`、`feedback.py`、`enablement_catalog.py`、`material_files.py` 后半段、`resource_transfer.py` 解析后段、`user_cleanup.py` 前 68 行。
- 前端 41 个组件中约 34 个未读。
- 91 个后端测试与 52 个 e2e 未运行；真实模型、LibreOffice 转换、Excel 导入未执行。

---

# 第七轮：反馈上传与目录投影（2026-10-18 02:10）

范围：`routers/feedback.py` 的提交与图片校验、`enablement_catalog.py` 的候选池与公开投影。
方式：只读。

## 7.1 反馈截图上传

- 请求体在解析前即限制文件数、字段数与单段大小（`feedback.py:61`）。
- 文件名先剥离目录并截断，落盘名为 UUID 加白名单后缀，无路径穿越（`:75-82`）。
- 图片校验同时比对真实格式与声明的 `content-type`，限制 2500 万像素，并把 `DecompressionBombWarning` 提升为错误（`:40-49`）。
- 任一步失败会删除本次已写入的文件；数据库记录与附件在同一事务内写入（`:92-104`）。

## 7.2 目录候选池

`POOL` 在 SQL 层就镜像了授权门：已发布、`system_visible=1`、当前 `authorization_epoch` 与版本一致、且版本冻结的 `_permissions.system_visible` 为真（`enablement_catalog.py:12-24`）。`resolve_reference` 仍是最终投影与授权门，二者在同一读事务内。

`public_detail` 对资源只允许当前发布版本（旧版本会被 404 拦截），案例走 `case_content.projection`。

## 7.3 本轮结论

未发现新增缺陷。

## 7.4 覆盖更新

后端已读：鉴权与身份、存储层、匹配核心、画像来源、能力发展状态机与引擎、召回与摘录、资源三维权限、账号删除、读取路径、案例可见性、反馈上传、目录投影。

后端仍未读：`partners.py`（218 行）、`profile.py`、`material_files.py` 后半段、`resource_transfer.py` 解析后段、`user_cleanup.py` 前 68 行。

前端 41 个组件中约 34 个未读。测试仍未运行。

---

# 第八轮：伙伴目录与画像接口（2026-10-18 02:25）

范围：`routers/partners.py`（218 行，全读）、`routers/profile.py`（75 行，全读）。
方式：只读。

## 8.1 已确认

- 路由级统一挂 `require_active_user`，写操作再叠加 `require_admin`；`include_disabled` 仅管理员可用（`partners.py:27,89-90`）。
- 非管理员读取停用伙伴一律 404，不泄露存在性（`:125-126`）。
- 伙伴硬删除在同一写锁内统计全部引用，包含对 `match_records.recommendations_json` 的逐条解析；无法解析的历史被单独计为「无法核验关联的推荐历史」并阻止删除（`:189-215`）。不存在用 ID 子串误判的路径。
- 行业/区域更新经 `preserve_pending` 保留待确认分类，不猜测旧值（`:155-157`）。
- 批量画像接口只做本地 `sync`，不派发模型调用，与「批量入口 0 次模型」一致（`profile.py:48-70`）。

## 8.2 P3-9 目录接口的 N+1 查询

`GET /partners` 与 `GET /partners/profiles` 对每个伙伴分别调用 `profile_sources.view`，后者内部又逐伙伴查询来源、章节与状态；`/profiles` 另加两次计数查询（`partners.py:79-83,94`）。

按 500 家伙伴估算，一次列表请求会产生数千次查询。当前数据量下可用，伙伴规模上升后是明显的响应瓶颈。属性能项，不影响正确性。

## 8.3 观察项：健康度评分的对外呈现

`calculate_partner_health` 依据画像、能力标签、行业、区域、案例与交付物算出 0–100 分并给出文字理由（`partners.py:46-70`），`GET /partners/profiles` 对所有已登录用户返回该分数。

AGENTS.md 与 README 均表述健康度为「临时实现、等待外部平台」。代码未新增维度（属既有实现），但与「不根据资料、案例、交付物或画像推导正式健康度」的表述存在张力。属产品口径问题，建议确认用户是否会把该分数当作正式结论。

## 8.4 本轮新增问题

| 级别 | 问题 | 位置 |
|---|---|---|
| P3-9 | 伙伴列表与画像列表存在 N+1 查询 | `partners.py:79-83,94` |

## 8.5 覆盖更新

后端仍未读：`material_files.py` 后半段（146-222 的处理流水线）、`resource_transfer.py` 解析后段、`user_cleanup.py` 前 68 行。
前端 41 个组件中约 34 个未读。测试仍未运行。

---

# 第九轮：文件处理流水线与 Excel 导入（2026-10-18 02:40）

范围：`material_files.py:146-220`（`process` / `process_contribution`）、`resource_transfer.py:158-262`（`import_workbook` / `batch_action`）。
方式：只读。

## 9.1 文件处理流水线

- 全流程由模块级 `PROCESS_LOCK` 串行化（`material_files.py:148`），同一进程内不会并行解析多个文件。
- 持久化前重新读取 `file_path`，与本次处理的路径不一致则删除刚生成的预览并放弃写入，避免替换竞态把旧结果写回新文件（`:180-183`）。
- 提取失败、预览失败、结果保存失败分别记录，且失败写入都带 `file_path` 或指纹条件（`:196-197,217-218`）。
- 结构校验（画像导入的 DOCX）在入库前执行，失败即置为 failed 并记录（`:168-176`）。

## 9.2 对 P3-5 的补充

`PROCESS_LOCK` 使解析串行化。好处是并发上传不会把线程池打满；代价是**一个异常构造的 PDF 或 DOCX 会阻塞其后所有文件处理**，直到超时或完成。结合「解析无超时」，P3-5 的影响面应从「占用一个线程」修正为「阻塞整条文件处理流水线」。仍属内网可用性风险，不是数据或越权问题。

## 9.3 Excel 导入

- 解析在事务外完成，写入在单个 `write_transaction` 内；任一行 `fail` 直接抛错，整批回滚并带上行号与列名（`resource_transfer.py:163,239-243`）。
- 逐行校验覆盖：资源 ID 格式、导出时状态、三项用途授权必须为是/否、类型与层级映射、岗位/专区名称必须存在、课程不得填写实验时长、重复 ID、按类型加链接匹配到多条时要求显式 ID（`:192-229`）。
- 未变化的行计入 `unchanged` 而不写入，重复导入不会产生新修订（`:231-234`）。
- 分类在同一事务内新增，超过 500 个时拒绝（`:182-186`）。

满足「任一行无效整批回滚并提示行号」「不执行公式」「最多 2000 条 / 10 MB」三条文档承诺。

## 9.4 本轮结论

未发现新增缺陷。P3-5 的表述按 9.2 修正。

## 9.5 覆盖更新

后端剩余未读：`user_cleanup.py` 前 68 行（`usable_admin`、`inspect_cleanup` 已在上文间接读过部分）、`partner_transfer.py`、`documents.py`、`cases.py`、`demand.py`、`enablement.py` 的发布/导入分支。
前端 41 个组件中约 34 个未读。
测试仍未运行。

---

# 第十轮：案例与资料访问、需求运营、伙伴导入（2026-10-18 02:55）

范围：`routers/cases.py`（127 行，全读）、`routers/documents.py`（全读）、`routers/demand.py` 的路由与鉴权、`partner_transfer.py` 的导入事务。
方式：只读。

## 10.1 案例与文件访问

- 案例路由整体要求已登录；所有读路径（详情、按伙伴列表、交付物列表、原件下载、预览）都先经过 `visible_case`，非管理员在停用伙伴下得到 404（`cases.py:13-105`）。
- 资料路由整体要求管理员，原件、完整提取文本与预览均不向普通用户开放（`documents.py:8`），与文件头注释一致。
- 删除案例时同时删除交付物行、清理磁盘文件，并对原伙伴执行 `sync`，孤儿贡献会被删掉（`cases.py:107-117`）。
- 案例改挂到另一伙伴时，只把仍有效的 ready 贡献重新键控到新伙伴，pending/failed 不搬运（`cases.py:45-62`）。

## 10.2 更正：关于「静默吞异常」的结论

第一轮写下的「50 处 `except Exception` 无一处为 `pass` 或静默 `return None`」**过强，需要更正**。

当时的检索只匹配了异常行之后的下一行，遗漏了行内写法。实际存在：

- **1 处宽泛静默**：`cases.py:127` `except Exception: pass`，位于后台任务包装函数 `_process_profile`。该函数只负责调用 `process_source`，失败状态已由被调方写入数据库，并有注释说明；不掩盖任务状态，但确实不再向上报错。
- **8 处行内静默**，异常类型均为窄类型（`HTTPException`、`InvalidOutput`、`ValueError`、`RecursionError`），属控制流而非吞错：`development_views.py:98,167`、`development_engine.py:150,156,180`、`task_failures.py:72`、`error_diagnostics.py:108`、`opportunity_extraction.py:58,63`。

更正后的结论：**唯一宽泛静默有注释、不掩盖已持久化的失败状态，但应作为已知例外记录**；其余静默均限定异常类型。

## 10.3 需求运营与伙伴导入

- `/admin/*` 需求运营接口由路由级 `require_admin` 统一保护；用户侧机会更新在函数内校验 `match_records.owner_user_id`（`demand.py:463-469`）。
- 伙伴 Excel 导入使用单个写事务并加写锁，逐行校验 ID 与名称，失败整批回滚（`partner_transfer.py:122-134`）。

## 10.4 本轮结论

未发现新增缺陷；新增一条对既有结论的更正（10.2）。

## 10.5 覆盖更新

后端剩余未读：`user_cleanup.py` 前 68 行、`enablement.py` 的发布/导入分支、`profile_report.py` 的 DOCX 解析细节、`ai_client.py` 的重试实现。
前端 41 个组件中约 34 个未读。
测试仍未运行。

---

# 第十一轮：能力发展前端交互（2026-10-18 03:10）

范围：`frontend/components/development-assistant.tsx` 的加载、轮询、提交与失败重试路径（97-172 行）。
方式：只读。

## 11.1 已确认

- 轮询按 `id` 与所选版本重建，卸载时清定时器并递增序号，避免竞态回写（`development-assistant.tsx:112-123`）。
- 提交标识存于 `sessionStorage`，刷新后仍能识别「已提交但结果未知」的状态（`:109-111`）。
- 失败提示区分「结果不确定」与「确定失败」：不确定只提供刷新，确定失败才提供重试（`:150-154`）。
- 运行中、待确认、已归档、查看历史版本时统一锁定写操作（`:137`）。
- 可传递视图预览带十秒刷新与窗口聚焦刷新，方案版本变更时清空旧预览（`:124-125`）。

## 11.2 一处细节

`action()` 的异常分支在「结果不确定且本地无待确认标识」时直接 `return`，不设置错误提示（`:132`）。该分支需要 `pendingRef` 已被清空才会进入，当前调用顺序下很难触发；不构成缺陷，记录备查。

## 11.3 覆盖更新

前端已读：`auth-provider.tsx`、`api-request.ts`、`task-failure.tsx`、`task-detail.tsx`（部分）、`development-assistant.tsx`（核心段）、`admin-panels.tsx`（片段）、`scenes.ts`、`skills.ts`。
前端未读：约 33 个组件，含 `enablement-workspace.tsx`、`partner-materials-manager.tsx`、`admin-demand-panels.tsx`、`task-list.tsx`、`task-navigation.tsx`、`task-progress.tsx`、`admin-panels.tsx` 其余部分。
后端未读：`user_cleanup.py` 前 68 行、`enablement.py` 发布/导入分支、`profile_report.py` 的 DOCX 解析、`ai_client.py` 重试实现。
测试：91 个后端与 52 个 e2e 仍未运行。

---

# 第十二轮：前端作用域、账号删除全貌、模型调用重试（2026-10-18 03:30）

范围：前端组件的 API 作用域使用、`user_cleanup.py:1-67`、`ai_client.py:100-192`。
方式：只读。

## 12.1 前端作用域一致性

逐组件统计 `adminApiFetch` / `userApiFetch` / `apiFetch` 的使用：调用 `/admin` 接口的组件仅限后台组件（`admin-panels`、`admin-demand-panels`、`enablement-admin`、`material-files`、`model-timeout-settings`、`partner-materials-manager`、`recent-errors`、`user-delete-button`）。用户区组件（`task-detail`、`task-list`、`task-navigation`、`account-panel`、`enablement-workspace`、`development-assistant`）没有调用 admin 接口的路径。

后台页面没有前端角色守卫，普通用户直接访问 `/admin/*` 会拿到 401 并被重定向到 `/admin/login`。由于后端逐路由强制校验（第一轮 AST 审计已确认 0 例外），这不构成越权，只是首屏会短暂渲染。

## 12.2 账号删除（补全前半段）

`usable_admin` 要求管理员同时满足：角色为 admin、状态 active、有密码、且未被锁定（锁定已过期视为可用）（`user_cleanup.py:15-26`）。`inspect_cleanup` 统计「以该用户为方案所有者或运行所有者」的进行中运行，以及进行中的推荐任务（`:29-47`）。

删除预览签发 10 分钟有效的确认令牌，绑定用途、目标用户、操作者与目标当前 `token_version`（`:50-60`）。删除时再核对一次，任一不符即拒绝（`:68-86`）。这套「预检 + 短时确认令牌 + 执行时复核」的组合，避免了「预览时合法、执行时状态已变」的窗口。

## 12.3 模型调用重试

`retry_model_timeout` 只重试 `TimeoutError` 与 `httpx.TimeoutException`，最多 `timeoutRetries + 1` 次；每次重试前调用 `before_retry` 重新解析模型配置，配置变化即中止（`ai_client.py:136-156,185-188`）。每次超时都写入错误诊断，保留原始异常类、消息与堆栈（`:150-154`）。

`_completion_content` 拒绝 `finish_reason` 为 `length` 或 `content_filter` 的响应、空内容，以及包含 `<think>` 的推理内容（`:111-133`）。与「不向用户展示模型内部过程」一致。

## 12.4 P3-10 已无调用方的旧同步入口

`ai_client.chat_completion` 在全仓已无调用点（`grep` 无结果），属死代码。若将来重新启用需注意：它使用 `httpx.Client(timeout=...)`，未设置 `trust_env=False`，也没有新路径那样的墙钟上限（`development_model.py:52` 已用 `asyncio.timeout` 处理慢速分块响应）。当前无影响。

## 12.5 本轮新增问题

| 级别 | 问题 | 位置 |
|---|---|---|
| P3-10 | `chat_completion` 已无调用方，属死代码；若复用则缺少代理隔离与墙钟上限 | `ai_client.py:159-192` |

## 12.6 覆盖更新

后端未读只剩：`enablement.py` 的发布/导入分支、`profile_report.py` 的 DOCX 解析细节、`documents.py` 之外的少量工具函数。
前端未读：约 30 个组件。
测试仍未运行。

---

# 第十三轮：测试映射与数据库索引（2026-10-18 03:45）

范围：后端模块的测试引用分布、`storage_models.py` 的索引定义。
方式：只读，静态统计。

## 13.1 模块与测试的对应

按模块名在后端测试目录中被引用的文件数统计（**引用数不等于覆盖率**，仅用于发现完全无测试的模块）：

| 模块 | 引用文件数 |
|---|---|
| `match` | 59 |
| `development_lifecycle` | 31 |
| `development_engine` | 29 |
| `enablement` | 26 |
| `profile_report` / `ai_client` | 18 / 18 |
| `profile_sources` | 17 |
| `model_resolver` | 14 |
| `partner_match_context` | 12 |
| `agent_settings` / `error_diagnostics` / `task_failures` | 6 / 6 / 6 |
| `material_files` | 5 |
| `user_cleanup` | 2 |
| `resource_transfer` | 2 |
| `partner_transfer` | 1 |

未发现零引用的后端模块。引用数最少的三个（`partner_transfer`、`user_cleanup`、`resource_transfer`）恰好也是本轮读到的、逻辑较独立的模块，建议确认其分支覆盖是否足够（本次未运行测试，无法判断）。

## 13.2 数据库层的一道硬保证

`development_runs` 上存在部分唯一索引 `(plan_id) WHERE status IN ('pending','running')`（`storage_models.py:208`）。这意味着**同一方案在任何时刻最多只能有一个进行中的运行**，由数据库而非应用逻辑保证。应用层的 `writable` 检查与它是双保险。

## 13.3 P3-11 常用外键列缺少索引

以下列有外键约束但**没有索引**，PostgreSQL 不会为外键自动建索引：

| 列 | 用途 | 位置 |
|---|---|---|
| `cases.partner_id` | 按伙伴列案例、配对召回取值 | `storage_models.py:72-84` |
| `deliverables.case_id` | 按案例列交付物 | `:85` 起 |
| `partner_documents.partner_id` | 资料列表与贡献同步 | `:340` 起 |

`partner_profile_sources` 的主键以 `partner_id` 打头，天然带索引，不受影响。

影响：`SELECT * FROM cases WHERE partner_id=?` 一类查询会走全表扫描。当前规模（数百家伙伴）可以接受，伙伴与案例数量增长后，叠加第十三轮之前记录的 N+1 查询（P3-9），列表页会明显变慢。

补索引属于结构变更，需走迁移流程，本次未执行。

## 13.4 本轮新增问题

| 级别 | 问题 | 位置 |
|---|---|---|
| P3-11 | `cases.partner_id`、`deliverables.case_id`、`partner_documents.partner_id` 无索引 | `storage_models.py:72,85,340` |

## 13.5 覆盖更新

后端未读只剩 `enablement.py` 的发布/导入分支与 `profile_report.py` 的 DOCX 解析细节。
前端未读：约 30 个组件。
测试仍未运行（本轮只做静态映射，未执行任何用例）。

---

# 第十四轮：DOCX 画像解析、资源保存与后台次级加载（2026-10-18 04:00）

范围：`profile_report.py:83-129`（`from_docx`、`baseline`、`validate_body`）、`enablement.py:160-208`（`write_transaction`、`save`、`permissions`）、前端后台组件的次级加载错误处理。
方式：只读。

## 14.1 DOCX 画像解析

- 只按原生段落与表格结构整理：识别章号转为固定十章标题，非章号标题降为三级标题，表格转 Markdown，其余段落原样保留（`profile_report.py:88-106`）。
- 目录在正文前被截断，不进入报告正文（`:109`）。
- `validate_body` 拒绝空正文、JSON 或代码块开头、以及正文中再出现一级/二级标题，避免一份文档覆盖成多级结构（`:125-129`）。
- `baseline` 在原 Word 不可用时抛错并保留原画像，不会退化成空报告（`:114-122`）。

与 AGENTS.md「DOCX 首次采用不调用 AI 改写；章节无法可靠识别时明确失败，保留仍有效旧正文」一致。

## 14.2 资源保存与授权

- `write_transaction` 在外层事务存在时复用连接，使 Excel 导入成为单事务（`enablement.py:165-173`）。
- `save` 在事务内校验分类、阻止已建资源更改类型、用 `base_revision` 做乐观并发；**忽略调用方传入的能力标签，始终沿用原有值**（`:183-190`），避免编辑表单顺带改写正式标签。
- `permissions` 仅在撤权时自增 `authorization_epoch`（`:204-208`），与第十四轮之前记录的「授予不追溯、撤权即时生效」一致。

## 14.3 P3-12 后台次级加载失败被静默忽略

后台能力标签页的分类下拉（`admin-panels.tsx:49-55`）与智能体名称加载（`agent-settings.tsx:18`）在请求失败时既不设置错误也不提示，界面表现为空列表。

主列表本身有错误处理（`admin-panels.tsx:44` 会显示加载失败），因此影响局限于筛选控件与名称展示：管理员会看到「没有可选项」而不是「加载失败」。属可用性缺陷，不影响权限或数据。

## 14.4 本轮新增问题

| 级别 | 问题 | 位置 |
|---|---|---|
| P3-12 | 后台分类下拉与智能体名称加载失败无任何提示 | `admin-panels.tsx:49-55`、`agent-settings.tsx:18` |

## 14.5 覆盖更新

后端除 `ai_client.py:1-99` 的辅助函数外，主要模块均已读过。
前端未读：约 28 个组件（含 `enablement-workspace.tsx`、`partner-materials-manager.tsx`、`admin-demand-panels.tsx`、`task-list.tsx`、`task-navigation.tsx`、`task-progress.tsx`）。
测试仍未运行。

---

# 第十五轮：前端组件引用关系与状态文案（2026-10-18 04:15）

范围：`frontend/components` 全量引用关系、任务状态文案的跨组件一致性。
方式：只读，静态检索。

## 15.1 P3-13 两个已无引用的组件

| 组件 | 导出 | 引用情况 |
|---|---|---|
| `health-status.tsx` | `HealthStatus`（`:16`） | 全仓无任何导入，也不被 e2e 引用 |
| `model-timeout-settings.tsx` | `ModelTimeoutSettings`（`:12`） | 全仓无导入；实际的超时输入在 `agent-settings.tsx:52` |

连同第一轮记录的 `frontend/lib/skills.ts`，前端共有三处死模块。`model-timeout-settings.spec.ts` 仍在默认 Playwright 名单中，但它测的是页面行为，不依赖该组件，因此该用例不会因为组件已死而失效——同时也说明它可能已与实际界面脱节，建议核对。

## 15.2 P3-14 任务状态文案在不同位置不一致

| 状态 | 任务列表 `task-list.tsx:24` | 侧栏 `task-navigation.tsx:12` |
|---|---|---|
| failed | 失败 | 生成失败，可重试 |
| partial | 部分完成 | 部分完成 |

侧栏对能力发展任务优先使用 `PlanStatus`（生成中 / 已生成 / 生成失败 / 已归档），符合约定；当 `planPresentation` 缺失时会退回通用文案，此时 `ready` 显示「已完成」、`partial` 显示「部分完成」，不在约定的四态之内。

该兜底分支目前不可达：后端对所有 `development_plan` 行都会返回 `planPresentation`（`match.py:227-233`）。属潜在不一致，不构成现存缺陷。

## 15.3 本轮新增问题

| 级别 | 问题 | 位置 |
|---|---|---|
| P3-13 | `health-status.tsx`、`model-timeout-settings.tsx` 已无引用 | 前端组件 |
| P3-14 | 任务状态文案在列表与侧栏不一致；能力发展兜底文案超出约定四态 | `task-list.tsx:24`、`task-navigation.tsx:12,264` |

## 15.4 覆盖更新

前端已读：`auth-provider`、`api-request`、`task-failure`、`task-detail`（部分）、`task-navigation`、`task-list`（部分）、`development-assistant`（核心段）、`admin-panels`（片段）、`agent-settings`（片段）、`scenes`、`skills`。
前端未读：约 26 个组件，含 `enablement-workspace.tsx`、`partner-materials-manager.tsx`、`admin-demand-panels.tsx`、`task-progress.tsx`、`opportunity-ui.tsx` 等。
后端：主要模块已读；`ai_client.py:1-99` 的辅助函数未逐行。
测试仍未运行。

---

# 第十六轮：前端安全模式全量扫描（2026-10-18 04:30）

范围：全部前端文件的安全模式检索，不逐个组件精读。
方式：只读。

## 16.1 检索结果

| 检查项 | 结果 |
|---|---|
| `dangerouslySetInnerHTML` | 无 |
| 直接读取 JWT 的位置 | 仅 `auth-provider.tsx` 的 `getToken`，其余组件通过 `apiFetch`/`adminApiFetch` 间接取用 |
| 用户区组件调用 `/admin` 接口 | 无（第十二轮已确认） |
| 外链 `target="_blank"` | 仅反馈截图预览一处，已带 `rel="noopener noreferrer"`（`app/admin/feedback/[id]/page.tsx:24`） |
| `window.open` | 仅资源跳转记录一处，打开后立即置 `opener=null`（`enablement-workspace.tsx:108`） |
| Blob URL | 反馈缩略图在卸载时 `revokeObjectURL`（同文件 `:22`） |
| 硬编码外部地址 | 未发现（命中项均为模型供应商名称文本） |

## 16.2 结论

前端未发现安全类问题。

---

# 附录：审计总览（截至 2026-10-18 04:30）

## A. 覆盖声明

| 范围 | 深度 |
|---|---|
| 后端 `backend/app` 约 11,000 行 | **约 95%** 逐行或逐函数读过；未读为 `ai_client.py` 前 99 行的少量辅助函数 |
| 后端测试 91 个、e2e 52 个 | **0 个执行**；仅做了模块与测试文件的静态映射 |
| 前端 41 个组件 | **精读 15 个**；其余 26 个做全量模式扫描（作用域、危险 HTML、令牌、外链、死代码、错误处理） |
| 真实模型链路、LibreOffice 转换、Excel 实际导入 | **未执行** |
| ARM 部署、systemd | 仅读代码 |

本报告不构成工程验收或业务验收结论，也不能替代实际运行测试。

## B. 风险登记册

（本节 P2-4 的修法已在文末《分歧与收敛》第三节修订：改为“四选一”依据规则，勿加 min_length。）
### P2（6 条）

| 编号 | 问题 | 位置 | 影响 |
|---|---|---|---|
| P2-1 | `FailureNotice` 丢弃 `title`/`stages` | `task-failure.tsx:16` | 部分完成被展示为整体失败 |
| P2-2 | 鉴权段共用一把排他锁，每请求写一行 `users` | `auth.py:79,98` | 并发上限固定为串行 |
| P2-3 | 后台任务失败只写 stdout | `match.py:952,959,1060` | 管理员错误面板看不到后台异常 |
| P2-4 | 证据字段可为空 | `matching_types.py:49-51` | 推荐可在零证据下通过校验 |
| P2-5 | 能力发展上下文超预算静默裁剪 | `development_engine.py:90-114` | 答复可能基于不完整资料且无提示 |
| P2-6 | 模型连接 `baseUrl` 无主机校验 | `model_config.py:124-158` | 管理员可外发环境密钥、可访问内网 |

### P3（14 条）

| 编号 | 问题 | 位置 |
|---|---|---|
| P3-1 | `skills.ts` 死代码且称谓未更新 | `frontend/lib/skills.ts` |
| P3-2 | `task-detail.tsx` 死文案与第三份标签副本 | `task-detail.tsx:44-58` |
| P3-3 | 410 文案仍写「匹配任务」 | `capability_tags.py:321` |
| P3-4 | 新库 seed 场景名仍为旧称谓 | `storage_defaults.py:47` |
| P3-5 | PDF/Office 解析无超时，且串行阻塞流水线 | `material_files.py:146` |
| P3-6 | 发展 60000 与匹配 25000 两套预算口径未写入文档 | `development_engine.py:84` |
| P3-7 | 三个函数参数未被使用 | `partner_match_context.py:224,367` |
| P3-8 | 主应用无 CSP，JWT 在 `localStorage` | 全局 |
| P3-9 | 伙伴列表与画像列表 N+1 查询 | `partners.py:79-83,94` |
| P3-10 | `chat_completion` 死代码，若复用缺少加固 | `ai_client.py:159-192` |
| P3-11 | 三个常用外键列无索引 | `storage_models.py:72,85,340` |
| P3-12 | 后台次级加载失败无提示 | `admin-panels.tsx:49-55`、`agent-settings.tsx:18` |
| P3-13 | 两个前端组件已无引用 | `health-status.tsx`、`model-timeout-settings.tsx` |
| P3-14 | 任务状态文案跨组件不一致 | `task-list.tsx:24`、`task-navigation.tsx:12,264` |

## C. 建议顺序

1. **P2-1**：唯一影响用户所见信息的缺陷，改动最小。
2. **P2-6**：唯一涉及密钥外发的权限越界。
3. **P2-4**：直接关系产品承诺「每条推荐都有证据」。
4. **P2-3**：补 `record_error`，后台失败可见。
5. **P2-5**：给能力发展补一个完成度标记，与推荐对齐。
6. P3 中优先 P3-1/2/13（删死代码）、P3-11/P3-9（性能）、P3-5（解析超时）。
7. **P2-2** 仅记录，扩缩容前再评估。

## D. 本次审计的边界

- 未修改任何功能代码；仓库内只新增本文件并修改 `docs/validation/README.md` 一行索引。
- 未提交、未推送。
- 未运行测试、未调用真实模型、未启停服务。

## E. 主要正面结论

按 AGENTS.md 的约束逐条核对，以下机制实现正确且经过代码级验证：

- 公开接口恰好 5 个，`/admin/*` 鉴权 0 例外。
- 19 条可验证的文档承诺全部与代码一致（另 1 条「网络白名单」无应用层实现）。
- 匹配的来源编号恢复、保存前二次复核、迟到写入保护、证据脱敏均为完整链路。
- 画像的按章指纹、迟到章保护、Word 首次采用不调模型均正确。
- 能力发展的 Plan/Run/Version 状态机与数据库唯一部分索引形成双保险。
- 资源的三维权限在发布时冻结、撤权时失效，互不推导。
- 文件上传的类型、结构、实体、宏、路径、像素与解压体积均有校验。

---

# 更正：P3-1 的措辞（2026-10-18 05:05）

编写回归哨兵时发现第一轮与附录中的 P3-1 表述不准确，特此更正。

**原表述**：`frontend/lib/skills.ts`「整份模块全仓无引用」。

**实际**：`frontend/lib/scenes.ts:1` 存在

```ts
import type { SkillId } from "./skills";
```

即该模块的 **类型 `SkillId` 被真实引用**，模块不能直接删除。第一轮的检索模式为 `from .*lib/skills`，未匹配 `from "./skills"` 这种相对路径写法，因此漏判。

**更正后的结论**：

- 模块本身仍在使用，**不应整份删除**。
- 无任何外部引用的是三个运行时导出：`SKILL_CATEGORIES`、`SKILL_REGISTRY`、`SKILLS_BY_ID`；旧称谓（「智能匹配」「伙伴智能匹配」）正位于这些导出中。
- 修复方式应为：更新或删除这三个导出及其中的旧称谓，保留 `SkillId` 类型。

**影响**：P3-1 的严重度不变（仍是清理项），但修复方式从「删除文件」改为「删除未使用的导出」。附录 B 中 P3-1 的表述以本节为准。

同类提示：`health-status.tsx` 与 `model-timeout-settings.tsx` 经同样的 import 检索确认为 0 引用，判定不变。

---

# 分歧与收敛（2026-10-18 22:45）

Codex 对本报告「复杂度」一节提出反驳，经过四轮往返，结论如下。原则是：先证明存在具体问题，再讨论最小改动。

## 一、我撤回的判断（六条）

| 原判断 | 更正 |
|---|---|
| P2-4 应给 `profileEvidence` 加 `min_length=1` | **修法错误。** 认证能力标签本身是经材料与人工审核的依据，强制要求引用会挡掉标签型推荐 |
| 「能从上一层推出即视为视图、不构成复杂度」 | **判据不成立。** 同一金额复制五处仍可推导，但更新要维护五处 |
| `P2-S1` 是多余的一层身份重建 | **误读。** 它是请求内别名，不落库；用于避免不同伙伴的 `S1` 冲突 |
| 「解释不应该产生 Run」 | **表述错误。** 应为「解释不应产生 Version」。现有实现（`finish_without_version`）已正确 |
| 「撤权即时生效」 | **过度概括。** 准确说法是拦住后续访问；已下载或复制出去的内容无法追回 |
| 「两份文档没写 = 产品未确认」 | **越界。** 只能表述为「未在 README 与 AGENTS 中找到确认依据」 |

## 二、我保留的判断

- **零依据推荐可通过校验**：当 `matchedCapabilities` 为空（模型提出的能力标签全部未通过校验）且三类引用全空时，该推荐仍会被采纳。这不是「标签型推荐」，而是「什么都没对上」。
- **锁的边界**：`Connection.execute` 按语句首词决定是否加 advisory lock，`WITH ... INSERT` 一类写入不会触发。当前全仓无此路径，属维护边界，不是现存缺陷。
- **身份传递待查**：证据标识在不同层之间是否重复维护，需要逐段核对代码，不能用层数推断。

## 三、决定一：证据充分性规则

由本次审计代行产品决定，理由与边界如下。

**规则**：一条推荐至少满足其一，否则不予采纳。

1. 通过校验的认证能力标签匹配（`matchedCapabilities` 非空）
2. 画像原文引用（`profileEvidence` 非空）
3. 案例引用（`evidenceCases` 非空）
4. 交付物引用（`evidenceDeliverables` 非空）

**依据**：AGENTS.md 明确 `partners.capabilities` 来自项目材料与严格人工审核，是重要能力依据，因此标签匹配构成充分依据。行业与区域属软条件，不计入充分依据。四类全空意味着没有任何可核验的来源，应拒绝。

**不采用**「必须有原文引用」：会误伤基于认证标签成立的推荐。

**实现位置建议**：`_validated_outcome` 的采纳循环内，在 `_source_assessment` 返回后判断；不改 `matching_types` 的字段约束。预计三行左右。

**`analysisRefs` 为空不视为缺陷**：供给缺口分析针对「没有合适供应商」，本来就没有可引用的伙伴来源。此项不改。

## 四、决定二：保留「发布时冻结授权」

**决定**：保留现有实现，即发布时把三个授权标志写入版本，之后再授予权限不会让旧版本可见；撤权通过 `authorization_epoch` 使旧引用失效。

**依据**：

- 对外分享场景下，「事后授权追溯放行旧内容」的代价高于「重新发布一次」的成本。
- 失败模式是可见的：内容显示不可用，管理员会重新发布；不是静默错误。
- 两个机制方向相反：冻结管「授予不追溯」，epoch 管「撤权即失效」，缺一不可。

**代价与要求**：管理员授予权限后，旧版本仍需重新发布才可用。这一点必须写进管理员操作说明，否则会被当成故障。

**保留意见**：该规则未在 README 与 AGENTS 中写明，属实现层约定。建议补进文档，使后续维护者知道这是有意为之。

## 五、待查：证据身份传递表

按以下三问逐项核对，**允许「现有实现合理，无需修改」作为结论**：

1. 每个编号指向什么对象、哪个版本；
2. 是临时换名，还是独立保存了一套关系；
3. 来源变化时，有几处需要分别维护。

初步观察（待验证，不作结论）：`stamp()` 是唯一指纹来源，被 `put`、`_ready_sources`、`matching_values`、`_current_reference_valid`、`profile_dependency_valid` 共用；若核对确认所有身份最终都受 `stamp()` 约束，则应判定「无需修改」。

## 六、给实现方的最小改动

1. 在推荐采纳处增加「四选一」依据判断（第三节）。
2. 其余 P2/P3 按原报告处理。

不因本次评审新增任何「四块各加一层检查」的改动。
