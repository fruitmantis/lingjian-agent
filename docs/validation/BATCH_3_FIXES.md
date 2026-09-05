# 第三批修复与验证记录

日期：2026-09-05。范围：推荐结果与证据约束、系统状态只读化、模型错误展示、相关浏览器与页面验证。保留前两批修改，第四批历史数据处理尚未开始。

## 1. 修改文件及关键变化

| 文件 | 关键变化 |
| --- | --- |
| `backend/app/routers/match.py` | 新推荐过滤无效身份、冲突名称、非有限值/越界分数和空理由；按分数排序、按 ID 去重，最多 5 家。匹配属性只保留伙伴资料中已有项。模型上下文补充案例 ID、交付物 ID 和文件名；返回的证据只展示通过伙伴归属校验的标题/文件名，缺失时明确提示。 |
| `backend/app/database.py` | 增加 `mode=ro` 连接，无法写入，也不创建缺失数据库；用于状态检查。 |
| `backend/app/model_resolver.py` | 增加内部只读解析选项；业务调用的选择优先级和现有配置保持不变。 |
| `backend/app/routers/system.py` | 删除建表、插入、删除和隐式模型调用；通过只读查询判断数据库读取，通过实际场景解析判断模型配置。没有验证的写入、模型调用和独立服务探测标为未知。异常信息不含原始路径、URL 凭据或异常文本。 |
| `backend/app/ai_client.py` | 使用固定的分类错误提示；验证响应结构、非空正文和完成状态，拒绝截断、内容过滤结果和内嵌思考标签；不把 reasoning 内容块拼入用户正文。 |
| `backend/app/routers/model_config.py` | 手动连接测试检查有效正文，HTTP 200 且空内容不再显示成功；不返回上游响应正文或原始异常。 |
| `backend/app/routers/profile.py` | 单个与批量画像失败不输出底层异常；画像正文为空或意外返回结构化内容时拒绝保存，保留原资料。 |
| `backend/app/routers/capability_tags.py` | 配置错误使用固定提示，避免直接转发异常文本。 |
| `frontend/components/admin-panels.tsx` | 系统状态说明只读检查范围及未验证状态；保留模型配置加载失败后的重试入口；模型表格局部横向滚动，解决 1024 宽度下页面溢出。 |
| `frontend/app/admin/system/page.tsx` | 页面说明区分读取/配置检查与实际运行验证。 |
| `frontend/app/tasks/[id]/page.tsx` | 供给状态显示中文，待补充问题显示为可读文本，避免直接呈现存储的 JSON 数组；业务字段和保存行为不变。 |
| `backend/tests/test_recommendations.py` | 覆盖数量、排序、去重、分数、身份、证据归属、旧格式兼容、持久化和历史记录保护。 |
| `backend/tests/test_system_status.py` | 覆盖反复刷新无写入、缺库不创建、场景配置、旧异常参数、地址脱敏与管理员权限。 |
| `backend/tests/test_model_errors.py` | 覆盖空/截断/无效响应、认证和网络错误脱敏、画像失败保护、结构化画像及内部思考内容阻断。 |
| `frontend/e2e/batch3-quality.spec.ts` | 覆盖状态刷新不改变测试库、新推荐与详情的证据/缺口展示、模型和状态页面布局。 |
| `frontend/e2e/release-validation.spec.ts` | 故障提示断言适配第二批中文提示；允许将本次截图写到独立临时目录，保留此前验证产物。 |
| `README.md` | 更新实际推荐规则、场景选择、只读检查、错误展示和验证记录链接。 |

## 2. 接口、路由、数据结构与业务影响

- 没有新增/删除路由，没有数据库结构迁移；现有角色、鉴权和任务所有权规则保留。
- 对外推荐字段仍是原有字段和字符串类型。内部模型证据优先使用 ID 数组；兼容唯一且完全匹配的案例标题/文件名，兼容已有蛇形字段名及 recommendations 包装。
- 推荐结果的数量、排序、去重、字段验证和证据显示行为改变。全部候选无效时仍返回可重试的处理失败，不回显模型原文。
- 系统状态响应字段不变，条目及状态语义纠正：配置具备不等于实际调用成功。管理员仍可在模型配置页手动测试连接。
- 没有更改真实模型 API 地址、模型名、密钥、默认标记或场景绑定；没有发起真实模型调用。
- 仅约束新生成或重新匹配的推荐。历史推荐及部分完成任务重试时复用的旧结果不自动回写，留待第四批核对。

## 3. 验证和结果

- 后端累计覆盖 **140 个不同用例**：首轮相关回归 **131/131** 通过（53.43 秒）；补充 4 个旧异常参数用例后，系统状态 **15/15** 通过（7.02 秒）；补充 5 个正文/思考内容用例后，受影响的模型与画像回归 **74/74** 通过（31.91 秒）。计数去除了重跑的重复用例。
- 浏览器 **16 项**全部通过：既有 **12 项**核心流程与四种宽度检查通过；本批 **4 项**专项验证在修复模型表格溢出和定位器歧义后全部通过（23.7 秒）。
- 截图复核后补充了任务详情中文状态与问题文本展示，并定向重跑新匹配/任务详情用例，1/1 通过（13.7 秒）。
- TypeScript 类型检查与 `git diff --check` 通过。
- 视觉检查包括 1920、1440、1366、1024 宽度的核心页面，以及 1440/1024 的系统和模型页面。检查页面级溢出；模型表格使用局部滚动。人工复核系统页、模型页及新任务详情截图。
- 所有自动化使用 pytest 临时目录或 `/tmp/lingjian-agent-e2e` 数据库/上传目录，使用模拟模型；没有全量构建、真实库迁移或历史数据修复。

本轮复现命令（浏览器验证前停用同项目日常前端）：

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider backend/tests/test_recommendations.py backend/tests/test_system_status.py backend/tests/test_model_errors.py backend/tests/test_model_config.py backend/tests/test_profile.py backend/tests/test_tasks.py backend/tests/test_authorization.py backend/tests/test_openapi.py
cd frontend
npm run typecheck -- --incremental false
VALIDATION_SCREENSHOT_DIR=/tmp/lingjian-batch3/core-screenshots npm run test:e2e -- e2e/release-validation.spec.ts e2e/batch3-quality.spec.ts
```

本次截图：`/tmp/lingjian-batch3/core-screenshots`（32 张）、`/tmp/lingjian-batch3/screenshots`（5 张）。这些是合成测试数据截图，未覆盖以往验证截图。

## 4. 剩余风险与未确认事项

- 证据校验确认已登记材料及其伙伴归属，不等于审阅文件内容或确认所有推荐理由的业务真实性；项目相关性、真实能力和匹配分仍需人工复核。
- 实际模型的输出质量及供应商兼容性未在线验证。严格校验可能过滤不规范结果，并提示用户重试。
- 系统状态页不再提供隐式在线模型探测或写入探测；未检查的能力明确显示未知，运行耗时/历史调用日志也未采集。
- API 保持同步调用。客户端超时不代表后台停止，第二批的任务核对提示继续保留。
- 历史数据没有回写；历史案例归属和缺失衍生数据属于第四批。
- 日常后端未重启，原 8000 端口进程仍需重启才能加载三批后端修改；所有本轮后端变更均已在隔离服务验证。

## 5. 收尾与 Git 状态

- 真实数据库、两份环境配置及 8 个上传文件共 11 个文件的 SHA-256 与本批开始时一致，上传文件清单一致。
- 已通过 dev.sh 恢复日常前端；3000/8000 端口服务均正常，后端仍为原 PID 174329，未重启。
- main 领先 origin/main 9 个既有提交；工作区共 22 个已跟踪修改、12 个未跟踪文件，包含三批累计内容。
- 未提交、未推送、未切换分支或创建 worktree。第四批尚未开始，等待用户确认。
- 最终定向页面复测、类型检查、差异检查均通过，无本批未解决测试失败。
