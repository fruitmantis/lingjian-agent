# 真实模型受控验证计划（未执行）

**REAL MODEL NOT AUTHORIZED；NOT RUN / 0 CALLS。** 本文件是后续授权范围建议，不是调用授权。当前不修改任何模型配置，不发送真实/合成输入给外部供应商。

## 实际代码与配置核验

- `backend/app/development_model.py`：HTTPX OpenAI-compatible `POST {base_url}/chat/completions`，Bearer 凭据由现有 resolver 在内存解析；`temperature=0.2`，max_tokens 使用配置且上限 16384，`response_format.type=json_schema`、`strict=true`，Pydantic schema。禁止跟随重定向、不继承代理环境。完整单调用墙钟超时默认 180 秒，Run 默认 600 秒。
- `partner_development` 场景先取显式 model_config_id，再取 `default` 场景显式绑定，再取唯一启用且 is_default 的配置；非法/停用配置拒绝，绝不取“第一个启用模型”。
- 本轮独立运行库核验：partner_development/default 均未绑定；标记默认的 GLM 配置已停用，启用的 DeepSeek 配置不是默认。因此**当前无法隐式解析到有效能力发展模型**；这是运行配置待授权门禁，不能把代码适配完成写成真实模型可用。
- 后续拟申请：仅在新建 `/tmp` 验证库将 `model_usage_configs.scene_key=partner_development` 显式绑定当前启用配置 `5f4ee5bf-733a-428f-ba81-a8afd0eeae92`（模型 `deepseek-v4-flash`、服务 `api.deepseek.com`、OpenAI Compatible）。执行前再次核验；如配置、供应商、模型或预算改变须重新确认。不得修改稳定库或独立日常运行库配置，不复制密钥到报告/代码。
- 真实网络开关 `LINGJIAN_ALLOW_REAL_DEVELOPMENT_MODEL` 默认不启用。仅未来获授权的专用测试进程可打开，退出后立即停止。现有全量工程测试均走 loopback mock。

## 预算与调用逐项安排

建议申请**最多 16 次外部 HTTP 模型调用**，不是 16 个 Run。当前引擎正常每个 Run 分别调用 diagnose 和 plan 两次。所有发出的请求（含 HTTP 错误/超时/失败/重试）都扣预算，不能以未获得 token usage 为理由不计数。不自动重试、没有“无限修复 JSON”循环，达到预算或安全违规立即停止相关步骤。

| 调用序号 | 场景 | 发送与验证 |
|---|---|---|
| 1–2 | A 正常生成 V1 | 诊断 + 候选受限方案；校验 schema/enum/目标 ID/候选 ID、版本、权限、无 URL/额外字段；保存完整 ready V1 |
| 3–4 | B 缺实验 | 相同目标但批准候选集中没有 lab；不得编造实验，ready 中明确当前资源库缺口 |
| 5–6 | C 证据不足 | 合成部分/缺失证据及人员基础待评估；不接受无确认来源的强结论 |
| 7–8 | D 非培训限制 | 明确地域/人力/商务/资质限制；分类 non_training_constraint，不安排课程来解决 |
| 9–10 | E unknown 条件 | 费用/账号条件未知；不能标为 meets，unknown 提示保留，conflicts 不入候选 |
| 11–12 | F 调整 | 先内部确认 A 的 V1，再基于 V1 缩短周期；成功 current=V2 draft、confirmed=V1，失败指针不变 |
| 13–16 | 有条件兼容预算 | 仅在前述 A–F 失败且属于供应商 strict 参数兼容、需要最小适配后的受控复测时使用；单个完整复测最多两次。预算不够则申请新授权，不换供应商 |

G 异常（空响应、非法 JSON、Markdown 包裹、schema 不兼容、HTTP 错误、timeout）**优先使用本地 OpenAI-compatible 测试服务/记录的脱敏响应回放，外部调用 0 次**。不为制造错误向真实服务发送无效凭据或等待真实超时。真实供应商遇到的参数行为按事实记录，不把 mock 注入写成真实供应商已验证。

## 每次允许发送的白名单

所有输入仅限合成或逐字段批准的测试包；目标附件/画像/内部案例材料默认禁止。后端先做 owner、有效性、发布版本及三维权限校验，再产生最小投影。

1. diagnose：target_partner_id、development_goal、trainee_role/count、known_baseline、duration_weeks、hours_per_week、constraints、accepted_assumptions；targets 仅 capability_tag_id/requirement；adjustment（明确授权的调整指令）。测试 ID 应为隔离环境 ID，不混用稳定对象。
2. plan：上述 request，已程序归一化的诊断（排除 confirmation 人工确认记录），以及最多 100 个已通过系统可见 + 当前发布 + 模型发送权限 + 约束过滤的候选。
3. 课程/实验候选：source_type/id/version、capability_tag_ids、title、summary、target_capability、audience、product_direction、difficulty、language、site、prerequisites、duration_minutes、cost、account_requirement、environment_requirement、source_platform 和受控 constraint 判定。
4. 共享案例候选：source_type=case、source_id=已有 case_id、当前共享版本、capability_tag_ids、已授权脱敏的 title/summary/methods/contributor_role/contributor_name/source_platform、constraint 判定。当前停止共享或旧授权 epoch 的内容不发送。

禁止发送：API Key/Token/密码、原始诉求 raw_demand、伙伴内部 ai_profile、原始附件、内部 case evidence、内部备注/核验 note、用户审计日志、来源任务/内部任务 URL、任何资源 URL、未经批准的个人资料、未获模型授权的资源、历史撤权正文、原始异常堆栈。自由输入即使在字段白名单中仍需人工批准及本地内容 guard，白名单不是敏感文本豁免。

## 程序校验与最小兼容方案

schema 生成于现有 Pydantic；模型返回依次过内容 guard、严格结构/enum/额外字段校验、ID/版本候选集合、强结论来源、当前权限/授权 epoch、事务保存。只有完整通过才有 Version。证据缺口等是合法业务结果，不算技术失败。

若供应商不支持 strict JSON schema：记录精简错误类型和参数支持情况，停止该请求；可在后续获授权的小范围适配中改为供应商支持的 JSON mode，或对**唯一完整 JSON 外的 Markdown 围栏**进行确定性解包。当前尚未实现该兼容，也未证明该供应商需要它。无论使用哪种参数，最终必须通过原有 Pydantic 与业务校验；不得宽松解析非法枚举/额外字段、补造 ID、接受自由文本或绕过强结论来源校验。

## 泄漏金丝雀与逐次审计

`INTERNAL_SECRET_PHASE_B_DO_NOT_SHARE` 仅保留于测试库授权内部资料。模型发送前直接断言最终 JSON payload 不含该字符串，模型响应后、伙伴可传递字段持久化前、preview/copy、错误响应、应用/审计日志分别断言不含。金丝雀不能作为 prompt 里的“请勿泄漏”内容发给真实模型。发现泄漏立即阻断并判该验证 FAIL，不继续外部调用。

每次调用记录：call_id、预算序号、provider、model、config_id（不含凭据）、UTC timestamp、scenario、Run/阶段的本地关联、success/failure、脱敏错误分类、token usage（prompt/completion/total，如未返回记 null）、latency_ms、schema/ID/URL/permission/strong-conclusion/canary 校验结果及响应哈希。不得记录 Authorization、完整 prompt/响应或内部材料。关联 ID 仅留内部验收证据，不进入伙伴外发。

**当前差距**：现有 adapter 返回 completion 文本，未持久化供应商 usage；不能声称当前已有完整真实调用账本。未来开闸前先在 mock 上验证测试专用拦截器/计数器：发请求前原子扣预算、接收后只提取上述白名单 usage/状态/时延、0 预算拒绝。该受控观测必须在首次真实请求前就绪，不能靠事后猜次数。本轮仅制定契约，不新增产品遥测范围。

最终分别签署：真实服务兼容、输出安全/业务约束、真实资源数据、业务负责人固定样例评审。本轮真实模型仍 **NOT AUTHORIZED / NOT RUN / 0 CALLS**。
