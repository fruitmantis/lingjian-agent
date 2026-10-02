# 2026-10-02：能力发展 P2 修复与长等待验收

当前修改在既有 main 工作区完成。此前任务切换、场景入口和可选伙伴改版保留；本次继续修复基础事实边界与派生提示一致性。AgentArts 保持暂停，未部署 ARM。

## 修复

- 仅将明确自述及获准资料作为能力事实；未说明的经验保持待核实。理解阶段不提前携带尚无候选依据的生成草稿。
- 修改上下文包含现有资源备注。基础纠正检查所有受影响正文、理由与备注，保留其他有效说明；patch 同步 analysis、overview、limitations、resource_gaps、next_steps 及受影响分组标题。
- 强结论保护逐个文本字段执行，避免 JSON 序列化后跨字段拼接误拒；原有拒绝模式不变。
- 将已有 patch 目标白名单与每个目标只允许一次操作的约束明确提供给模型，后端仍拒绝越界或重复操作。
- 不新增模型调用阶段、数据库表或队列，不改变正式模型参数及超时配置。原先落库再判断、Run 归属与旧版本保护保持。

## 验证结果

| 验证 | 结果 | 范围 |
|---|---|---|
| 聚焦离线回归 | 114 passed，84.39 秒 | P2、无伙伴、多轮纠正、超时重试、迟到旧 Run 不能写回 |
| 最终真实模型 | 两个 Run ready，4 次 HTTP 200，27,078 token | 当前 DeepSeek 配置；初始无伙伴需求＋一次 Python/RAG 追问；仅 2 课程＋2 实验合成目录 |
| 版本保护 | 通过 | 清理临时 schema 前对比 confirmed 指针及旧 Version 全部行字段；新 current 指向新版本 |
| 代理百秒 HTTP | 通过，120.003 秒 | 上游仅 1 次请求，正文及状态保留；此前结果未重跑 |
| 代理短边界 | 3 passed，1.035 秒 | 短延迟、客户端超时、不自动重试、停止断连 |
| 应用长等待＋浏览器 | 通过，241.336 秒 | 每次模型 HTTP 等待 120 秒，共 2 次；创建 202 仅 0.173 秒；模型返回前已保存任务与原文 |
| 等待期间交互 | 通过 | 重复点击仅 1 次 UI 提交；重复 API 请求返回相同 task/run；刷新、离开重进、侧栏选中与最终结果恢复 |
| 服务恢复 | 通过 | 原 backend/frontend/Caddy 均运行；localhost 与实际 IP 的 HTTP80 首页和 health 均 200；3000/8000 仅回环 |

真实模型原样使用单次 300 秒、额外重试 3 次的当前策略。应用合成测试将相同策略复制到专用验证 schema，未修改正式配置。所有测试写入仅在专用 PostgreSQL 随机 schema 或 /tmp，未创建真实业务测试记录。应用测试 schema 和临时模型服务已清理。

最终真实回包逐段检查：未将未提供的 API 集成／服务编排经验或“没有 AI 经验”写成事实；Python/RAG 补充与正文、使用提示、资源备注、相关分组一致。此结论仅覆盖本次受控样例，不保证所有模型输出。真实模型只有初始与一次追问；跨越三轮历史窗口的持久保留由离线测试覆盖，不冒充多轮真实验证。

## 失败记录与复测依据

本接续轮共 16 次真实模型 HTTP 调用、100,057 token，全部使用合成目录；没有账单数据，不估算费用。最终通过样例为最后 4 次，其余请求没有算作通过：第一次功能断言通过但人工发现正文／课程备注仍陈旧；第二次暴露跨字段强结论误拒；第三次暴露同一目标重复 patch 操作。每次均在对应修复和离线回归后才复测。两次失败调整均保存旧 current／confirmed 和旧版本。另有一次合成管理员随机密码格式导致准备失败，0 模型调用，验证器已修正。

## 本机证据与复现

原始响应、临时配置、合成会话、截图和录像仅留本机，不纳入 Git：

- `/tmp/banfei-final-acceptance-4_o3jz6s/focused-final.xml`
- `/tmp/banfei-final-acceptance-4_o3jz6s/live-final-contract/quality-review.json`
- `/tmp/banfei-final-acceptance-4_o3jz6s/live-final-contract/version-state-before-correction.json` 与 after，以及 versions-before/after-correction.json
- `/tmp/banfei-final-acceptance-4_o3jz6s/app-delay/browser-result.json`、`result.json`、四张 PNG 与 `video/`
- `/tmp/banfei-long-model-delay-798w2qf2/result.json`

仅代理的可选百秒复现：`python3 -B scripts/tests/check_long_model_delay.py --delay-seconds 120`。此命令仅合成回环 HTTP，不连接数据库或真实模型，不证明应用 UI。应用层执行器与浏览器脚本保留在本轮 /tmp 证据目录；须先核对服务归属、无运行任务及专用测试 PG，不能直接对正式库测试。

本轮浏览器为用户电脑 WSL Chromium；未验证 Windows 物理浏览器、真实移动键盘、ARM、AgentArts 或完整真实资源目录。未重复此前全部前端回归、build/typecheck；此前验收记录另见现有验证索引。
