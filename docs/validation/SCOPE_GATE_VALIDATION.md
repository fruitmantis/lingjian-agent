> **阶段验证记录。** 本文的提交状态、HEAD 和测试数字属于当时基线；当前状态见 [2026-09-26 收口记录](GIT_CLOSEOUT_20260926.md)，现行规则见 [README](../../README.md)。

# 独立 Scope Gate 验证

日期：2026-09-25。范围：当前 main 工作区未提交改动；不代表上线或完整业务验收。

## 最小实现

- 项目找伙伴、能力发展在读取伙伴/资源和创建业务任务之前先检查范围。复用各入口已有模型选择；只传当前用户消息和必要的原发展方向，不传伙伴画像、候选伙伴、资源或业务模型回答。
- 分类模型只输出 `{"in_scope": true/false}`，程序严格校验布尔值和唯一字段，不接受字符串、数字、缺失字段、额外回答或代码围栏。不用关键词黑名单。生成模型只处理业务相关部分，不承担范围判断。
- 范围外按可操作的业务拒绝返回 HTTP 422 和固定提示，既有前端直接展示；不执行后续模型，不创建推荐、画像、机会、Plan、Run 或 Version，不写最近错误。
  - 项目找伙伴：“这里仅支持伙伴选择与推荐，请描述项目需求或询问相关推荐结果。”
  - 能力发展：“这里仅支持伙伴能力发展建议，请描述发展方向或询问相关方案。”
- Gate 配置、连接、HTTP、超时或解析失败按既有系统错误处理。真实原因、模型/HTTP/返回片段在可取得时写入脱敏诊断。失败响应标记 `submissionAccepted: false`，前端不会遗留“提交未确认”任务。
- 同步兼容匹配入口、旧任务重试、发展建议修改和追问也覆盖。鉴权和重复提交回放优先，模型调用不持有业务事务；写入前再次校验幂等和版本。追问进入修改时仅判断一次，拒绝不会改变已有版本/采用指针。
- 无 schema、模型配置或场景绑定变更；分类请求临时使用 temperature=0、最多 64 个输出 Token、最多 15 秒，不改变业务生成参数。没有新 Agent、管理页面或范围分类体系。

## 真实模型限定验证

使用当前 `api.deepseek.com / deepseek-v4-flash`，32 次真实分类请求全部通过：

- 天气、旅游行程、直接写代码、写诗：每类在两个入口各连续 3 次，24 次均为 false。
- 业务追问、省略式追问、信息不足、同时包含业务诉求和无关要求的混合请求：8 次均为 true。
- 实际输入 Token 合计 11,797，输出 224，总计 12,021；本轮单次最长约 1.09 秒。没有业务生成调用，不读取伙伴/资源，不写运行库；仅以只读连接解析现有模型绑定。
- 本地证据：`/tmp/banfei-scope-live-20260925.json`。分类抽样不能保证未来所有模型输出；工程侧对每次返回严格校验，调用或解析失败不会继续业务生成。

需要复验时先说明范围和费用，再显式执行限定 32 次的脚本，不覆盖旧证据文件：

```bash
.venv/bin/python scripts/verify_scope_gate.py \
  --environment .isolation/runtime/dev/environment.json \
  --output /tmp/banfei-scope-live-<new-run>.json --execute
```

## 工程回归

实际结果：

- 前端 typecheck、production build 均通过。
- 相关后端回归 205 项通过；随后补充缺失模型 Key 的诊断验证，并复验模型传输和诊断环节 6 项通过，其中 5 项为重复验证。合计 206 个不同用例通过（198 个 PostgreSQL，8 个原有 SQLite 生命周期兼容用例），其中 Scope Gate 专项 51 项。
- Playwright 14 项通过：Scope Gate 专项 4 项、原错误处理 8 项、能力发展完整解释/修改流程两种桌面尺寸 2 项。Scope Gate 两个入口各连续提交 12 次跑题请求，均不增加任务和错误；范围外追问保留版本；明确未受理的 Gate 失败不留下待恢复任务。
- 首轮回归暴露了一个后端测试和一个双尺寸浏览器测试中的旧错误文案断言。仅将断言同步到前一批简化提示，保留原有数据不变和错误不泄漏检查；复验通过。
- 真实分类与工程回放分别记录：回放使用合成模型，32 次真实分类不生成业务内容。没有对 `banfei_agent` 进行测试 seed、故障注入或 E2E 写操作。
- 本地后端证据：`/tmp/banfei-scope-backend-final.xml`、`/tmp/banfei-scope-backend-final-extra.xml`。

自动化后端与浏览器测试只使用 `banfei_agent_test` 临时 schema；兼容 SQLite、上传夹具和故障诊断仅在 `/tmp`。业务生命周期用例默认模拟 Gate 通过，专项用例独立检验 Gate；浏览器 replay 的范围结果为显式合成夹具，不冒充真实模型判断。

本地复验入口（私有验证配置给子进程提供 `BANFEI_TEST_DATABASE_URL`，不打印连接串）：

```bash
.venv/bin/python scripts/run_postgres_validation.py backend -q -k 'test_scope_gate or test_task_creation or test_tasks or test_development_engine or test_development_api or test_development_lifecycle or test_error_diagnostics or test_task_failures or test_recommendations or test_model_errors'
PLAYWRIGHT_MODEL_MODE=replay .venv/bin/python scripts/run_postgres_validation.py browser scope-gate.spec.ts task-failure.spec.ts development-assistant.spec.ts
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

浏览器和 build 与开发服务顺序运行，结束后用 `bash enablement-dev.sh start` 恢复原私有环境。未 commit、push 或 deploy。
