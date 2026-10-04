# AgentArts 阶段三验收记录（2026-10-04）

## ARM v2 后续验收与提交收口

以下为同日后续授权窗口的最终状态；下文早期“未部署/未调用真实模型”仅描述相应阶段。

- 隔离 ARM 发布目录为 /opt/banfei-agentarts/releases/20261004-agentarts-stage3-v2，
  263 份部署源码哈希一致，Next.js production build 通过。复用独立 PG、账号与上传，
  未重新初始化或覆盖业务数据；原 main 应用服务保持停止。
- 用户自行通过隐藏输入录入两条 Runtime 各自的平台 Key 与 shared key，两次 v2 握手通过。
  管理员正常登录后保存无 Key 模型元数据连接及两个独立 Runtime 目标，刷新读取一致。
  模型为 deepseek-v4.1-flash，thinking 开启、单次超时 300 秒、额外超时重试上限 3 次。
- 获得本次限定真实资料及模型调用授权后，通过 Windows Edge 正常用户界面各创建一次业务任务：
  匹配 4f55dbbf-d620-4630-ad30-32b93e7c87b6，约 98 秒后 ready，返回 5 个候选；
  发展 90ab7377-8d60-4cea-a9a4-234552b3eeb4，约 90 秒后 ready，生成第 1 版。
  两条 Runtime 目标摘要均正确，匹配 3 个阶段、发展 2 个阶段各一次完成，无重试或错误记录。
  该次数来自应用 Runtime 阶段记录，不是云计费账单。
- 匹配结果明确缺少可核实案例/交付物，只能作为初步推荐。发展建议包含 4 阶段、
  17 项课程/实训；引用 ID、已发布版本、标题、类型与授权全部核对一致。
  正常页面展示原文、真实进度与结果，无页面脚本错误；本窗口未重跑全部动画与任务切换组合。
- 2026-10-04 14:57:37 UTC 确认零在途任务后恢复 systemd 外发禁止项，
  删除本次 /run 临时覆盖，隔离后端重启后 HTTP 80 健康检查 200。
  原环境文件不变；main 应用仍停止；验收浏览器和临时调试端口均已关闭。
- 后续新增离线检查：v2 握手 CLI 10 项、认证原因码 3 项、ARM 隐藏录入工具 6 项通过。
  本次提交收口仅做 git diff --check、57 份 Python AST 与两个 Shell 语法检查，
  不重复部署、Docker 构建或真实模型调用。
- 截图、业务响应、执行记录及关闭开关证据保留在用户电脑
  stage3-evidence/arm-v2/，不提交真实资料、截图输出、环境文件或认证数据。
  历史未跟踪归档保留原位，不纳入本次提交；POC 独立仓不在本次发布范围。

实施位于 /home/yuan/project/lingjian-agent-agentarts（HEAD 9adf33a；未提交）。
主干 /home/yuan/project/lingjian-agent-enablement 的 HEAD 0fda85c 未改，tracked diff 为空。
两边已有历史证据文件均保留，Git refs 未变化；未 push 或部署。

## 已完成

- 同步 main 阶段一、二固定智能体管理与 backend/business，共享业务提示词/契约/校验；
  Runtime 删除重复实现，保留适配、协议、授权与结果绑定。
- 两固定镜像 target matching/development；接收错误 workflow 时模型调用前拒绝。
- 新 Run 保存 executor/runtimeUrl/model/thinking/timeout 快照；基础处理固定本地，无静默回退。
- 云端只走已验证 AgentArts 模型代理；管理员选择的模型名、思考开关和超时传到模型调用。
  使用 MaaS chat_template_kwargs.thinking 及 max_completion_tokens，不与 max_tokens 并发。
- 云端连接只存元数据，拒绝在 VM 配置其 Key；HTTP API、任务包、镜像不携带模型凭据。
- 一键构建、检查、tag、push；默认固定 /home/yuan/.config/banfei/docker，显式 --docker-config 可覆盖，
  保留 --build-only。两个正式镜像均检查通过才开始推送；各自证据单独保留。
  未实际 Docker 构建、sudo/binfmt、认证、推送，未读取 Docker auth 文件。

## 实测

| 检查 | 结果 | 证据 |
|---|---|---|
| 配置/共享业务/Runtime/重启/预算 | 77 passed | banfei-stage3-directed.xml |
| 原有超时授权、幂等、失联对账、无非超时重试 | 21 passed | banfei-stage3-runtime-qa.xml |
| 最终云端连接边界、CRUD、共享 Prompt 与额度 | 52 passed；53 subtests passed | banfei-stage3-final.xml |
| 一键脚本 syntax + 离线 mock | 7 passed | scripts/test_image_publish.py |
| TypeScript --noEmit --incremental false | passed | 最终检查退出码 0 |
| WSL 隔离 Chromium 首轮 | 6 passed | /tmp/banfei-e2e-k171mkp9/browser.log |
| 最终界面与无伙伴发展复核 | 3 passed | /tmp/banfei-e2e-r5rudini/browser.log |
| Windows Edge 隔离管理界面 | passed（合成 API 路由，仅 UI） | windows-edge-ui.json / windows-edge-agent-settings.png |

测试批次有重叠，不相加为不同用例总数。PG 仅专用验证库随机临时 schema；退出时删除本轮 schema。
WSL 浏览器使用真实本机 HTTP + 合成模型 Runtime，云端认证、供应商与平台没有参与。
Windows 截图是新增配置控件、保存及刷新恢复的 UI 证据，使用合成身份与合成路由；
截图右上“系统异常”来自本次 UI fixture 未模拟 health，不能作为真实服务健康结论。
本轮未读取真实用户凭据、未改真实业务数据、未传真实伙伴资料、未调用付费模型。
首次 Windows Edge 受到 spawn EPERM 沙箱阻挡；允许的 require_escalated 重试后通过，没有绕过访问限制。
隔离临时服务已停止；主干后端 411867、前端 411868、Caddy 411932 始终未切换。

## 复现

- 在现有私有专用 PG 测试配置下，用主干 .venv 运行所列测试文件；
  scripts/validate_agentarts_browser.py 从 /tmp 副本启动隔离服务，默认跑 3 个选定测试文件。
- Windows UI 脚本 stage3_windows_ui.cjs 使用独立 Edge；需提供该隔离前端，
  不可以把它指向主干或真实服务，不可把合成路由通过作为真实业务通过。
- 正式镜像用户一条命令：
  bash /home/yuan/project/lingjian-agent-agentarts/deploy/agentarts/build-arm64-local.sh
  用户自行确认 sudo。登录由用户此前手动完成；脚本不重新 login/logout。
  未实际推送，因此本报告没有正式新镜像的 tag/digest。

## 未验证与待确认

- 标准 WSL 实际 IP HTTP 80 仍是主干，需要受控测试窗口；尚未把本轮 AgentArts 改动部署到它。
  需确认无在途任务、暂时切换专用测试配置与前后端、正常登录验收后恢复主干。
- ARM 及真实双 Runtime v2、实际 Docker ARM64 构建/推送、供应商真实响应均未验证。
- 不自动删除云资源。仅 banfei-model-probe-test 列为候选；其专属 workload identity/API Key
  的实际名称与共享引用仍待云控制台只读核实。本机环境未提供可直接枚举云资源的工具。
- 保留 banfei-model-proxy、huawei-maas-banfei、huawei-maas-key、defaultgw、
  AgentArtsGatewayAgency 的共享策略、banfei-runtime-test；保留长期 SWR 登录与本地/SWR 镜像。
- 未纳入后续七组件讨论；没有另做市场、观测或通用编排平台。


## 标准 HTTP 80 受控窗口补验（已完成）

用户明确批准后，停止前两次确认主干 matching/enriching 与 pending/running 计数均为 0，
并记录原进程身份、入口和配置 SHA256。由原受管脚本短停 main，
将 AgentArts 当前源码的独立副本运行在真实标准 80/3000/8000 端口，
实际入口为 http://172.21.208.223。数据库仅使用本轮专用 banfei_agent_test 随机 schema；
没有把 AgentArts 代码或迁移应用到主干数据库。

Windows Edge 无 API mock、无 Token 注入，使用合成管理员正常登录：
- 两个智能体分别选择模型连接 A/B、思考关闭/开启、超时 180/240 秒及各自 Runtime 目标；
  真实保存接口均 200，刷新后全部保留，修改匹配配置不改变发展配置，基础处理仍固定本地。
- /api/admin/agents、/api/admin/model-configs、两个 PUT 配置接口及健康接口均 200，没有 404。
- 8 份实际服务关键源码与 AgentArts 当前文件 SHA256 相同。
- 未运行真实或合成模型任务；本轮后端日志没有 Runtime 模型尝试或 chat/completions 记录。
- 临时服务结束，专用 schema 已核实不存在，没有遗留测试库修改。

电脑连接断开中断了首次恢复：前后端已启动而 Caddy 尚未恢复。
重连后重新核实零在途任务，使用原 main 受管脚本完成恢复：
backend 469594、frontend 469595、Caddy 469670 均 running。
实际 IP /api/health 为 200；原环境配置和 Caddy 配置 SHA256 均不变，
main tracked diff 仍为空，3000/8000 仅绑定 127.0.0.1。

恢复后 Windows Edge 再检查 /admin/models HTTP 200，并正常转到管理员登录页；
该独立浏览器没有主干管理员会话，因此没有查看主干受保护配置内容，也没有读取凭据或绕过认证。
本轮新增代码的受保护配置交互已在前述标准80合成管理员会话完整验证。

新增证据位于 Windows stage3-evidence/standard80/：
browser-done.json、windows-standard80-agent-settings.png、served-source-hashes.json、
recovery.json、main-restored-browser.json、windows-main-restored-login.png、
test-schema-cleanup.json、model-call-check.json。
标准窗口脚本 standard80_window.py、standard80_browser.cjs 与 standard80_restored.cjs
仅作本轮复现记录；不要盲目重跑旧控制文件或旧 schema。
ARM 仍未操作，云资源未变更，未 Docker 构建/push、未 commit/push。
