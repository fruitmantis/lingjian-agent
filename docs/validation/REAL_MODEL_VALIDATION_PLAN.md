# 伴飞 Agent 真实模型验证

适用当前 main；此文档为验证方法，不是本轮执行报告。当前七个场景已绑定 `api.deepseek.com` / `deepseek-v4-flash` 且已获用户授权。历史累计调用数不在此维护；每次测试独立记录实际调用，不写“累计 0 CALLS”。

## 当前调用方式

- 复用 OpenAI-compatible `POST /chat/completions`、现有模型场景与权限。
- 能力发展按 `DirectionAnalysis` / `AdviceOutput` 等当前 [Pydantic 契约](../../backend/app/development_types.py) 处理；不使用旧培训长表单作为必填输入。
- DeepSeek 当前适配使用 `json_object` 并提供完整 schema 提示；其他供应商保持既有参数。`deepseek-v4-flash` 关闭思考输出，结果仍经严格程序校验。
- 项目机会抽取允许常见字段形态与包装差异，缺失记未知；这不允许能力发展编造资源 ID、URL、忽略权限或未经来源确认的强结论。
- explain/discuss 和 revise 使用当前任务上下文，前者不新建版本，后者成功产生新版本，失败保留旧结果。

## 有界 smoke

先完成 [执行前核对](REAL_MODEL_PRECHECK.md)。现有工具只发送写在代码中的合成方向、画像摘要、空标签/候选集合，不读取或发送真实伙伴/附件，不写业务对象：

```bash
.venv/bin/python scripts/verify_real_model.py   --environment <现有私有环境JSON>   --model-config-id <已批准启用配置ID>   --output <新的私有审计JSON>   --stage analyze --execute
```

`analyze` 为最多一次，默认 `both` 为最多两次真实 HTTP 请求。工具只临时限制 smoke token 预算，不修改保存的模型配置。此命令示例不是要求每次文档或 UI 改动都执行。

工具记录 provider、model、timestamp、scenario、HTTP/请求状态、接口返回的 usage、latency、程序校验结果与安全错误类型。只读配置不输出 Key；不保存完整 prompt/response。完整任务验收的模型调用数可能不同，不把两次 smoke 预算当所有 Run 的固定调用数。

## 业务与安全样例

以下是待执行时的验证清单，不代表已全部通过，也不新增产品输入步骤。使用合成或明确允许的数据；自动化写入仅限独立验证库，先明确每次调用预算。

| 场景 | 检查重点 |
|---|---|
| 项目找伙伴 | 伙伴画像、案例和交付物信息实际参与；推荐与证据归属正确，资料少自动降级 |
| 明确发展方向 | 目标理解、画像可复用基础、建议重点和候选资源相符 |
| 探索方向 / 局部实验 | 输出形态随意图变化；局部查询不强制完整长报告，不强制课程+实验+案例齐全 |
| 证据不足 / 非培训限制 | 不把资料缺失认作确认不足，不以培训解决地域/人力/商务问题 |
| 资源缺口 / unknown 条件 | 不虚构资源、不把 unknown 当符合；只说明当前目录缺口 |
| 解释 / 比较 | 回答与当前建议相关，不创建 Version、不要求先确认草稿 |
| 自然语言 revise | 新版本成功保存后更新 current，confirmed 保持原值直到明确采用 |
| 失败调整 / 撤权 | 旧版本保持可用；访问、后续模型输入和伙伴外发重新检查授权 |
| 项目机会提取 | 列表、分组区域、Markdown JSON 等常见形式可归一；缺失信息记未知；真正网络/保存失败不伪装成功 |

空响应、非法输出、HTTP 错误、限流、超时和数据库故障优先用隔离故障注入/replay，不故意向真实服务发坏凭据或制造付费超时。真实遇到的供应商行为单独记录，不用模拟结果冒充真实效果。

模型输出仍校验结构、enum、候选 ID/版本、URL、权限和强结论来源；金丝雀直接断言不在发送/外发/错误和日志中，发现泄漏立即停止相关验证。不得把金丝雀作为“请勿泄漏”的 prompt 文本发送出去。

分别记录：代码与环境、输入范围/摘要、真实请求次数及审计路径、自动化结果、真实资源核验、人工业务结论。后者使用 [业务验收模板](REAL_BUSINESS_ACCEPTANCE_TEMPLATE.md)，不由 smoke 自动判 PASS。
