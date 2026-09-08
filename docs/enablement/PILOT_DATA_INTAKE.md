## 结论

**READY FOR PILOT DATA**：已具备接收真实 Pilot Package、进行本地预检并交给业务负责人签审的条件。尚不具备真实模型执行或业务上线条件。

| 维度 | 当前状态 |
|---|---|
| 工程基线 | RC Preparation 已接受；本轮没有修改产品代码 |
| 实际真实数据 | BUSINESS DATA BLOCKED，未收到业务批准包 |
| DATA-01-MACHINE-CHECK | BLOCKED - BUSINESS DATA REQUIRED（不是拿模板失败代替真实数据验收失败） |
| DATA-01 业务签审 | NOT RUN，仍需业务负责人签审 |
| DATA-02 | BLOCKED，工程结论与真实业务数据可用性仍分开 |
| REAL MODEL PRECHECK | BLOCKED |
| 真实模型 | NOT AUTHORIZED / NOT RUN / **0 CALLS** |
| 业务验收 | NOT RUN |

## RC 归档与冻结

最终 RC Preparation 归档提交：`1a0b4b4f081de63c617b366788e19d0090d19093`，本地标签：`rc-preparation-accepted-20260906-1a0b4b4`。标签只表示 Engineering Ready / RC Preparation Complete。RC 归档后已核验工作区 clean；本轮后续新增接收工具单独归档，不移动 RC 标签。

该归档包含检查过的 90 个文件；76 张截图 SHA、测试源证据 SHA 及原 131 个代码/测试文件均核验。`artifacts/enablement-rc/code-baseline.json` 保留实际测试代码 `066f78262a2df7abebcf1215073db41c3052a009` 与源文件 SHA；文档归档提交不能冒充重新执行产品测试。RC 阶段已有 399 后端 / 58 浏览器与 typecheck/build 通过，本轮按用户要求不重复运行。

## 接收目录及字段映射

`pilot-data/` 共六个文件：README、pilot-manifest.template.json、course.template.json、lab.template.json、shared-case.template.json、business-signoff.template.md。JSON 是唯一权威输入；共享案例也使用 JSON，避免 Markdown 正文与机器字段漂移。Markdown 只用于填写说明和业务签审。

完整逐字段映射见 `pilot-data/README.md`：直接复用 DevelopmentRequest、ResourceMetadata、ShareMetadata、Permissions、Review；source_id/source_version、contributor_id、reviewer_id/reviewed_at 对应既有表。业务称谓 model_send_allowed、partner_share_allowed 分别映射现有 model_allowed、partner_allowed，不引入第二套权限。

包内 manifest 文件引用、包来源标记、资料授权范围、资源缺口及签审是接收证据，不新增产品业务表。模板全部空白，不含正式资源、不包含用户凭据。业务方应在 `.isolation/pilot-intake/` 的私有副本填写，真实材料不提交 Git。

## 预检规则与模式

`scripts/validate_pilot_data.py` 是离线开发/验收工具，无业务路由、无写库、无网络请求。

- 必须提供独立数据库；URI mode=ro + query_only + 同一只读事务；拒绝稳定目录、v9、软链接/硬链接、包外路径及重复 JSON key。
- 严格复用现有 Pydantic schema；产品字段须显式填写；额外字段、未明确布尔权限、无效 URL/标签、缺核验/无效核验人时间、未发布目标状态均拒绝；错误只显示字段路径与受控代码。
- 核对伙伴 ID/名称/启用状态、正式标签、case_id/有效贡献伙伴。内部案例正文不得直接填入共享资源，即使 model_allowed=false 也检查已知内部文本片段。
- 检查已知 synthetic/fixture/example.com/验证伙伴/A-ready/金丝雀标记；机器无法识别所有被去标记的造假，真实性仍靠业务签审，绝不自动将“自称 real”视为业务通过。
- 系统、模型、伙伴三集合独立计算。模型拒绝未授权项/约束冲突项；unknown 保留并提示。按同一正式目标标签检查 course+lab+case 路径；缺口必须登记；缺实验仍没有完整路径，不补造实验。
- intake 模式：允许新资源 ID/共享版本尚未生成，核对拟接收数据，不能用于真实模型门禁。imported 模式：要求已有当前发布版本、相同快照、权限、授权 epoch 和实际核验审计。
- 真实模型前检额外检查 clean、已导入、最小投影、包外候选隔离、明确用户授权与业务数据批准、测试模型显式绑定、预算和调用审计证据、禁止附件。任何条件不满足 BLOCKED。机器校验签审记录及 hash 的一致性，不替代人工身份/批准真实性审核。

## 本轮实际测试

最终命令：

```bash
.venv/bin/python -m pytest backend/tests/test_pilot_intake.py -q --junitxml=/tmp/pilot-intake-tests.xml
.venv/bin/python -m py_compile scripts/validate_pilot_data.py scripts/collect_pilot_intake_evidence.py scripts/write_pilot_intake_report.py backend/tests/test_pilot_intake.py
.venv/bin/python scripts/collect_pilot_intake_evidence.py /tmp/pilot-intake-tests.xml
git diff --cached --check
```

最终定向测试 **37 passed / 0 failed / 0 errors / 0 skipped**，相关脚本语法检查通过。全部数据库写入仅在 pytest `/tmp` 临时 fixture 内；自测试将 socket.connect 和模型 completion 替换为立即失败，以保证不执行外部调用。格式正确路径的正向样例仍是临时合成测试，并未算作业务数据。

| 必测场景 | 结果与证据 |
|---|---|
| A 完整格式但 synthetic 标记 | 拒绝；其他 5 类测试标记也直接拒绝且错误不回显内容 |
| B 缺实验 | 真实路径不完整、缺口未登记分别报错；登记缺口仍不冒充完整路径 |
| C invalid case_id | 拒绝 |
| D orphan case | 拒绝共享；只在临时库注入孤儿关联 |
| E model_allowed=false | 系统可用，排除模型集合 |
| F partner_allowed=false | 排除伙伴外发集合，与模型权限独立 |
| 三维权限 8 种组合 | 全部验证 |
| 撤权/快照不匹配 | imported 模式拒绝 |
| 金丝雀/内部案例原文 | 内部临时资料可存在；模型投影与错误输出无泄漏 |
| 门禁收据 | 临时构造正向完整性分支、拒绝批准=false 和篡改；不代表实际有用户授权或已完成调用审计运行器 |
| 空白发布模板 | 明确拒绝当真实包 |
| 数据库保护 | hash 不变，写 SQL 被 query_only 拒绝；稳定路径/链接拒绝 |

开发过程中修正了两个测试构造问题（孤儿 case 的 NOT NULL、链接拒绝错误分类）及一次新增测试字符串语法错误；修正后完整定向组通过，没有遗留失败。产品 backend/app、frontend 未修改，产品 API、路由、schema、模型选择逻辑、权限与前端行为均未改变；未启动浏览器或新服务，没有新增截图。全量 pytest/Playwright/typecheck/build 本轮 NOT RUN（按本轮明确范围）。

## 当前实际数据与保护

本轮再次只读核验 `.isolation/runtime/app.db`：schema=12；33 家伙伴、3 条内部案例、0 条课程/实验资源、0 条共享配置、0 份 Development Plan。integrity_check=ok；foreign_key_check 2 项，与已有 2 条孤儿案例对应。本轮未导入、未迁移、未修复历史异常；独立数据库文件 hash 不变。已有伙伴/内部案例不等于获批准的试点包。

独立库 partner_development 仍无启用的显式绑定；不读取输出密钥、不修改正式配置、不擅自选用既有 DeepSeek/GLM 配置。

稳定 main 保持 `f79cbb29ec7b3ad70c88e618e3161211f211c06a`；稳定工作区 clean；167 个保护文件 SHA 未变（稳定数据库只读文件 hash，未连接 SQLite）；原 3000/8000 进程及 cwd 保持。旧版登录/session/audit/migration/写库次数为 0。新版 3100/8100/mock 均未启动，保持停止；未 push、merge、rebase、deploy，也未核验远端同步状态。

## 证据清单

- `artifacts/pilot-data-intake/validation-results.json`：最终测试计数、用例名称、工具/模板 SHA、原始 JUnit SHA（JUnit 仅在 /tmp）。
- `artifacts/pilot-data-intake/runtime-inventory.json`：脱敏统计、schema、既有 FK 异常、绑定状态。
- `artifacts/pilot-data-intake/template-rejection-and-gate.json`：提交前模板拒绝及门禁阻断；当时正在编写交付文件，因此 worktree_clean=false，不能误读为最后归档后状态。
- `artifacts/pilot-data-intake/protection-verification.json`：稳定保护及 RC 标签。
- `.isolation/evidence/pilot-intake-final-precheck.json`：交付提交后重新执行的 clean 与门禁检查，仅本地保留；当前报告头部包含最终结果。

## 待业务方补交与下一轮门禁

最低需要 1 个真实能力方向、1 家伙伴及允许诊断资料范围、明确诉求与目标/人员/时间/约束、至少 1 门课程+1 个实验+1 个现有案例的授权共享版本，完整元数据/核验/三维授权、已知缺口和业务签审。使用 `pilot-data/README.md` 与 `business-signoff.template.md`，详细缺口仍见 `FINAL_PILOT_DATA_GAP.md`。

后续真实包导入前要做 SQLite 一致性 backup、integrity/FK/原计数；导入需完整事务，失败 rollback。现有 API 逐操作提交，不能提供整包事务；**整包导入执行器尚未实现和验证**，收到数据后先准备独立库受控导入与恢复验证，本轮没有声称已经自动导入就绪。业务未提供数据不以合成资源补齐。

真实模型预算/审计测试运行器、明确用户授权、业务数据模型发送签审、approved test model configuration 均未具备；`REAL_MODEL_PRECHECK.md` 只准备门禁。当前 0 次真实模型调用。停止于本轮接收准备，等待真实 Pilot Package。
