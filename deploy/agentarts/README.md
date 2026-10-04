# AgentArts 阶段三：共享核心与两个固定 Runtime

本轮将 main 的阶段一、二（0fda85c）同步到既有 agentarts 工作区（HEAD 仍为 9adf33a）。
主干目录、Git refs、运行服务与真实数据库未改动；修改尚未提交或推送。
旧阶段结论见 ../../docs/validation/AGENTARTS_RELEASE_20261003.md，不能作为本轮云端部署证据。

## 执行边界

- backend/business 是本地与 Runtime 的提示词、严格类型及业务校验来源。
  agent_runtime 仅保留协议、传输、运行状态、部署入口与兼容导入，不复制业务提示词/类型。
- VM 保留身份、权限、材料预选、先落库、幂等、任务/Run/Version/current、PG 与最终事务保存。
  Runtime 不连接数据库，不获取真实资料目录或 VM 凭据。
- 管理后台两个固定智能体分别选择 local / runtime 与 runtimeUrl，受理时连同模型 ID、thinking、
  timeoutSeconds、timeoutRetries 存入已有执行快照。修改设置只影响新 Run；失败不自动改走本地。
  基础处理固定 local。旧 BANFEI_MATCH_EXECUTOR / BANFEI_DEVELOPMENT_EXECUTOR / BANFEI_RUNTIME_URL 不再决定新 Run。
- 部署两份镜像：Dockerfile target matching 只接受 match；target development 只接受 development。
  错工作流在调用模型前拒绝。协议升级为 banfei-runtime-v2，旧 v1 Runtime 不兼容，不能直接切换旧目标。
- 原有 lost-ACK GET 对账、单次 POST、VM 授权超时重试、30 秒 lease、来源/权限/CAS 检查与重启中断恢复保留。
  已受理运行保持目标地址；握手校验工作流和模型代理地址，每次调用复核所选模型路由。

## 云端模型连接

VM 模型配置新增一条不含 Key 的元数据连接，使用已验证代理 base URL：

    https://banfei-model-proxy-defaultgw-gzswgzdcgz.cn-southwest-2.huaweicloud-agentarts.com/inference/v1

模型名如 deepseek-v4.1-flash；实际使用管理员所选连接的名称、temperature、top_p。
Runtime 仅允许该代理地址（隔离测试显式允许 loopback），禁止改为 api.deepseek.com 直连。
Runtime HTTP JSON 显式发送 chat_template_kwargs.thinking=true/false。
输出额度使用 max_completion_tokens（包含推理与最终答复）；不同时发送 max_tokens。
沿用现有 Runtime 262144 输入/总上下文保守字节预算、131072 wire 输出上限及剩余预算检查，
后台不改写原额度，界面明确这些 Runtime 约束。供应商实际模型容量另需真实云端验证。
本地基础处理仍使用已有本地连接和已有供应商参数适配。

每份 Runtime 的云端私有环境：
- BANFEI_RUNTIME_SHARED_KEY：VM 与该 Runtime 的应用校验值，至少 32 字符。
- BANFEI_MODEL_PROXY_API_KEY：原始模型代理 Key，Runtime 自动构造 Authorization: Bearer；勿包含 Bearer 前缀。
- BANFEI_RUNTIME_MODEL_URL 可省略（默认上述代理），其他外部地址拒绝。
模型 Key 不进入 VM 的任务包、模型元数据、镜像、日志。VM 的云端连接不提供本地测试按钮。

VM 私有环境分别配置：
- BANFEI_MATCH_RUNTIME_SHARED_KEY / BANFEI_MATCH_AGENTARTS_BEARER
- BANFEI_DEVELOPMENT_RUNTIME_SHARED_KEY / BANFEI_DEVELOPMENT_AGENTARTS_BEARER
兼容旧单组 BANFEI_RUNTIME_SHARED_KEY / BANFEI_AGENTARTS_BEARER 作为部署值回退，不回退执行目标。
HTTPS 外发仍须 BANFEI_RUNTIME_EXTERNAL_DATA_APPROVED=1；设置此值不能代替用户对具体真实材料的批准。
本轮未设置真实凭据、未外发真实资料、未调用付费模型。

## 一条命令构建并推送

由用户在 WSL 普通用户终端启动：

    bash /home/yuan/project/lingjian-agent-agentarts/deploy/agentarts/build-arm64-local.sh

先构建两个固定 target，逐个检查 ARM64、单 Docker V2 manifest、非 root UID 10001、
各自固化入口及无网络容器冒烟；全部通过才对本次随机唯一标签逐个 tag 和 SWR push。
默认目的地 swr.cn-southwest-2.myhuaweicloud.com/banfei/banfei-runtime。
打印各自完整 tag、push 实际返回 digest 与不可变引用。任一构建/检查失败不推送；
推送失败停止，不重试或撤销已成功上传的其他镜像。

默认固定 sudo 前当前用户的 $HOME/.config/banfei/docker；当前为 /home/yuan/.config/banfei/docker。
所有 Docker 操作显式传同一 --config。旧 SWR_AUTH_DIR / DOCKER_CONFIG 不覆盖该默认；
换目录使用 --docker-config /absolute/directory。用户已手动确认长期登录成功；
脚本不读取认证文件内容，不自动 login/logout，不清理登录目录，也不保存密码。
--build-only 保留构建和检查，完全跳过 registry。
PoC 的 scripts/build_model_proxy_runtime.sh 复用本仓 image-publish.sh，共用发布保护，不复制框架。

正式构建保留原已审阅的临时 ARM64 QEMU/binfmt 注册与精确清理记录流程，sudo 由用户确认；
不安装 Docker、不加入 docker 组、不开放 TCP、不持久注册、不清理旧本地/SWR 镜像。
本轮助手仅修改源码与运行 shell/mock 检查，未实际构建、注册、推送或修改云资源。

## 正式 v2 无模型握手

用户在本机 WSL 交互终端运行一条命令（仅 Python 标准库，不需要 sudo）：

    python3 -B /home/yuan/project/lingjian-agent-agentarts/deploy/agentarts/verify_runtime_v2.py

按中文提示选择伙伴匹配/能力发展，粘贴控制台完整 Runtime 调用 URL，并隐藏输入
原始平台 Runtime API Key 和对应 BANFEI_RUNTIME_SHARED_KEY。平台 Key 不含 Bearer 前缀。
可加 --workflow match 或 --workflow development 跳过工作流选择；两个 Runtime 分别执行。
密钥不通过参数、环境或文件传递，不回显、不落盘；没有安全隐藏输入能力时直接停止。

脚本复用 VM URL 校验，仅接受官方 HTTPS AgentArts 调用根路径及可选 endpoint 参数；
自动生成 UUID Session，在查询参数之前追加 /runtime-info，一次 GET，20 秒超时，
不跟随任何重定向、不使用环境代理、不自动重试。校验 banfei-runtime-v2、所选工作流、
incarnation UUID 和既定模型代理 URL 摘要。失败保留 HTTP 状态、请求 ID 和脱敏返回片段。
退出码 0 表示握手通过，1 表示失败；不调用模型，不建立业务任务，不读写后端环境配置。
握手不能证明模型代理 Key 有效或模型调用成功。旧 arm/configure_runtime.py --verify
仍是 v1 检查，不用于本流程；此工具也不是后端密钥录入工具。

离线测试（模拟响应、禁止真实网络，不需要数据库）：

    python3 -B scripts/test_verify_runtime_v2.py

## 401 安全诊断镜像

服务端仍以原 X-Banfei-Runtime-Key 完整匹配鉴权，所有共享密钥失败均为 HTTP 401，
保留 detail=Unauthorized，仅追加固定 reason_code；不记录或返回密钥、摘要、具体长度或完整请求头：

- runtime_shared_key_unconfigured：服务端共享密钥未配置或为空。
- runtime_shared_key_too_short：服务端共享密钥未达到最小长度。
- runtime_key_header_missing：容器未收到 X-Banfei-Runtime-Key。
- runtime_key_mismatch：收到该头，但未通过完整匹配（空头也属于此类）。

既有握手 CLI 会显示这些原因码，不必更换输入方式。原镜像没有原因码；
只有构建新镜像、将 banfei-matching 更新为该新镜像并使相应版本生效后才会生效。
仅构建和推送 matching（用户执行，沿用已批准的临时 binfmt、检查与精确清理流程）：

    bash /home/yuan/project/lingjian-agent-agentarts/deploy/agentarts/build-arm64-local.sh --target matching

控制台选择本次输出 PUSHED_IMAGE，保留原鉴权/环境/前缀路由，保存新版本并确认 Latest 指向它，
然后才再次运行 verify_runtime_v2.py --workflow match。无需重建 development 或改协议。
不传 --target 仍构建两个 Runtime；--build-only 和 --docker-config 行为保持不变。
本轮只修改源码并执行离线验证，未构建、推送、调用 Runtime 或修改云端。

离线安全诊断测试（ASGI 内存请求、合成密钥、模拟 CLI 响应，禁止网络/模型）：

    /home/yuan/project/lingjian-agent-enablement/.venv/bin/python -B scripts/test_runtime_auth_diagnostics.py

## 验证与下一步

专用本机 PostgreSQL + 随机 validation_* schema；真实模型网络被阻断。
定向测试见 backend/tests/test_agentarts_stage3.py、test_agentarts_runtime.py、test_agentarts_qa_fixes.py。
scripts/validate_agentarts_browser.py 使用 /tmp 源码副本和原隔离高位回环端口；不会覆盖主干服务。
该脚本可传指定 e2e 文件，默认覆盖智能体配置、两模式入口和无关联伙伴的发展流程。
旧 scripts/validate_agentarts_real_model.py 已停用，不能从 VM 抄取模型 Key 做直连验收。

标准 WSL HTTP 80 已在用户批准的受控窗口完成补验：AgentArts 源码副本、独立 PG 测试 schema，
Windows Edge 正常合成管理员登录、真实配置 API 保存/刷新通过，随后恢复 main。主干配置摘要未变，
实际 IP 健康 200，测试 schema 已清理。断线恢复过程与证据见 docs/validation/AGENTARTS_STAGE3_20261004.md。
恢复后的受保护主干配置未登录查看；该独立浏览器只核对了正常登录入口。
ARM、SWR 与真实两个云端 Runtime 的部署/模型调用不在本轮执行范围。

## 云资源清理清单（未执行）

候选：banfei-model-probe-test。需先由云控制台核对它的专属 workload identity/API Key 与其他引用；
未查明实际关联名称，不能把建议名称当作已创建资源。提交确认后再删除具体对象。
保留：banfei-model-proxy、huawei-maas-banfei、huawei-maas-key、defaultgw、
AgentArtsGatewayAgency 的共享 Agency/CSMS 策略及 banfei-runtime-test（直到真实切换完成）。
本轮未访问/删除云资源，没有扩大到本地或 SWR 镜像清理。
