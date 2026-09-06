# 真实模型前置门禁

当前：**BLOCKED；NOT AUTHORIZED / NOT RUN / 0 CALLS**。本轮不绑定任何模型、不读取/输出 API key、不发送请求。此文档以及校验通过都不是调用授权。

可执行入口：`scripts/validate_pilot_data.py <manifest> --database <independent-db> --imported --real-model-precheck`。任何未满足条件输出 BLOCKED 并退出 2。该命令只有本地 JSON、Git 与 SQLite 只读操作。

| 检查 | 执行口径 |
|---|---|
| worktree_clean | 当前功能 worktree `git status --porcelain` 必须为空 |
| imported_machine_pass | 真实包 schema 严格通过，库中已有当前发布 ID/版本、payload、人工核验审计和三维权限与包相符 |
| model_path_complete | 至少一个目标能力有可发模型的课程+实验+共享案例路径；无授权资源不能凑路径 |
| safe_projection | 复用请求白名单与 resolve_reference(model)，剔除 URL/核验 note/附件；guard 检查内部片段及金丝雀，无正文输出 |
| model_pool_within_approved_package | 复用实际候选检索，目标能力命中的可发送候选不能混入包外未批准数据 |
| request_model_permission | DevelopmentRequest.model_input_allowed 显式允许 |
| explicit_user_authorization | 私有审批证据明确 real_model_test、包哈希、供应商、模型和最大调用数，且仍在有效期内 |
| business_data_authorization | 业务方 data_for_model_test 签审，包哈希与实际模型字段投影哈希一致 |
| explicit_approved_test_model | 仅独立库 partner_development 显式绑定批准配置 ID，启用且 provider/model 与授权完全对应；此门禁不接受 default 回退 |
| budget_and_audit_ready | 最大调用数 1–16、测试运行器哈希与 mock 证据一致、预算用尽阻断/失败也计数/金丝雀阻断/审计字段完整均通过 |
| independent_database | 明确路径仅独立 worktree 或 /tmp、非软/硬链接、只读 URI、query_only、schema=12；禁止稳定目录 |
| unapproved_attachments_excluded | 授权收据显式 attachments_allowed=false；一期工具无附件输入字段，拒绝额外字段 |

## 未来私有授权收据

只有收到用户明确授权及真实业务签审后才创建，放 `.isolation`。本轮不创建看似已批准的收据。加 `--authorization-receipt .isolation/<receipt>.json` 进行核验。

收据必需字段：package_sha256、expires_at（ISO 带时区）、approved_test_config_id、model、provider_base_url、max_calls、attachments_allowed=false，以及 user_authorization、business_signoff、budget_audit_mock_test、audit_runner 四个证据引用。每个引用是 `{path, sha256}`，path 相对 `.isolation`，必须私有单链接文件，禁止目录逃逸。

- user_authorization 文件是审计用 JSON 摘要，字段 approved=true、signed_by、signed_at、scope=real_model_test、package_sha256、model、provider_base_url、max_calls。摘要必须可追溯到用户原始授权，不能由工具自行生成批准。
- business_signoff JSON 摘要包含 approved=true、signed_by、signed_at、scope=data_for_model_test、package_sha256、model_projection_sha256，来源为业务签审原件；机器只验证记录一致性，负责人身份及批准真实性仍由人工核实。
- budget_audit_mock_test JSON 必须包含 status=PASS、real_model_calls=0、runner_sha256，以及四个 true：budget_exhaustion_blocks、failed_calls_counted、canary_blocked、audit_fields_complete。当前**尚未实现并验收真实调用预算/审计运行器**，所以该门禁目前不可能完成；本轮不伪造此证据。
- audit_runner 引用未来批准的本地测试运行器源码；其哈希必须与 mock 验证记录一致。一次 HTTP 请求记一次调用，失败/超时也扣预算，达到上限阻断；不自动无限重试。

收据完整性检查不是电子签章或身份认证。本脚本不会开启 `LINGJIAN_ALLOW_REAL_DEVELOPMENT_MODEL`，不会调用适配层，不会自动创建配置，PASS 也不执行模型。实际执行前须再次核验 Git、包、权限、授权有效期及运行器；任何数据/模型/预算变化使旧批准失效。

## 当前配置与后续计划

产品调用方式是现有 OpenAI-compatible `/chat/completions` 严格 JSON schema；产品允许 partner_development → default 显式绑定 → 唯一启用默认配置，但本次门禁要求第一层明确绑定。当前独立运行库没有有效 partner_development 显式绑定，**不将现有正式配置自动设为测试模型**。仅未来得到授权后，在独立试点数据库创建/绑定 approved test model configuration。

测试场景、每次字段白名单、最多 16 次 HTTP 调用建议、JSON/ID/URL/enum/权限/强结论不可放宽等沿用 `REAL_MODEL_VALIDATION_PLAN.md`。其中旧 RC 文档提到的候选配置 ID 仅是当时建议，不构成执行选择；本轮以新批准测试配置机制为准。

金丝雀只放隔离自动化库的内部资料，不作为 prompt 中的提示发送。每次调用前验证最终 payload，返回、持久化外发字段、copy、错误和日志边界继续检查；发现泄漏必须阻断。调用审计白名单：provider、model、timestamp、scenario、success/failure、usage（缺失为 null）、latency、各程序校验结果、请求序号和摘要 hash，不保留完整 payload/响应/凭据。

## 原子导入后的不可变输入绑定

Pilot Import Executor 现在通过事务内账本生成实际 ID/版本与系统审核身份；原始签审包不回写。对已导入包运行上述命令时增加 `--import-ledger .isolation/pilot/<pilot>/imports/<package-id>/import-ledger.json`。validator 先核对文件中的事务账本与当前 DB app_metadata 中的权威记录，再校验完整原包 hash 与当前发布内容。完整 package hash 包含包内 signoff 等来源证据；新一轮模型授权收据应存放包外，避免改变原始签审包。

导入器自动化通过不改变本文件的当前 BLOCKED 状态；本轮仍无真实业务包、调用授权、批准测试模型配置或已验收的真实调用预算/审计运行器，真实调用仍为 0。
