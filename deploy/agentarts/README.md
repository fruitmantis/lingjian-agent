# AgentArts 双业务改造：本地阶段

> 当前部署与验证结论见 [脱敏归档](../../docs/validation/AGENTARTS_RELEASE_20261003.md)。下文的未构建/未推送等叙述属于注明日期的历史过程，不代表当前状态。

状态：独立 `agentarts` worktree，基线 `576926a`。用户本轮明确授权此工作树及 WSL 构建环境，覆盖根 AGENTS.md 的日常 main-only 限制。main 与 HTTP80 原服务不变。未提交、推送、上传镜像、创建云资源或正式切换。

## 边界与开关

- VM 保留 Caddy/Next、业务 API、登录权限、伙伴/资源查询、资料解析、PostgreSQL 与文件、任务/Run/Version、最终校验与事务保存。
- `backend/agent_runtime` 是两业务共用的正式托管代码，不复制 PoC 仓。提示词、严格契约、模型请求和阶段输出校验只有一份；原本地模式复用这些提示词。匹配为理解→初选→详评，发展为理解→按需生成/局部修改。VM 在阶段间按权限准备材料，托管端不连接 PG、不回连 VM。
- `BANFEI_MATCH_EXECUTOR=local|runtime`、`BANFEI_DEVELOPMENT_EXECUTOR=local|runtime` 独立控制，默认 `local`。失败不会暗中改走另一路重复调用。运行中的已发请求不因改开关自动迁移；回退应等待结束或标记中断后，显式重试新 Run。
- 匹配 local/Runtime 路径均让全部启用伙伴参与初选，不按字面关键词截断候选；超预算沿用完整语义压缩，仍不足则明确失败并保留任务，详评最多12家；发展沿用授权资源的关键词/标签候选。完整否定/限制段落一起选取，超过预算明确失败，不静默截断正文。托管包带来源 ID、版本/快照、有限资料提示；完整提示词、schema 与输出预留一起校验预算，使用保守 UTF-8 字节上界而非声称精确 token 计费。

## 协议与保护

- VM 先落业务任务/Run/用户原文；现有线程池仅负责发起和轮询。`app_metadata` 记录 `runtime_session:<run_id>` 与 `runtime_stage:<run_id>:<stage>`，无 schema 迁移。
- taskID、runID、随机平台 sessionID 分离；阶段 operationID 固定为 runID+阶段的 UUID5。所有结果校验协议、任务、Run、Session、操作、进程 incarnation、输入快照和模型指纹。
- Runtime 每次只调用一次供应商，超时后进入 `awaiting_retry`，不会自行重试。VM 重新核对账号、任务/current、来源权限及模型配置后，为指定前次尝试授权下一次；每份授权只发一次 POST，确认丢失仅 GET 对账。Runtime 按 incarnation、session 与尝试号拒绝乱序并去重授权。超时秒数和重试次数完整保留管理后台配置（含4001秒/5次），没有3600秒/3次隐式上限。非超时错误不重试。
- 首次提交只 POST 一次；确认丢失后 GET 查询同一操作，最多3次短暂传输重试。不存在/换实例/终态失败必须显式新 Run，不盲重发可能已计费的请求。Runtime 同操作不同包409，跨会话查询404，单进程绑定一个业务 Run。
- Runtime 短暂内存仅存本会话操作，VM 的 PG 是业务持久事实。Runtime 重启生成新 incarnation，拒绝旧操作重放；VM 启动回收将未结束 Run 与阶段记录标记中断，不自动续算。VM 每次轮询复核用户、Run/current、模型与资料权限；撤权/中断尝试取消 Runtime，30秒未收到 VM 轮询则取消孤立模型工作。VM 每次授权前的复核是撤权边界：尚未授权的重试停止；已授权且在传输中的执行与已发出的供应商请求不能保证追回/退费，但其晚到结果不能推进版本。
- 来源预选快照在发包前和返回时复核；事务保存继续沿用 existing CAS、引用权限与版本校验。解释型追问不增 Version，成功修改才推进 current；confirmed 只保留历史，不恢复确认/采纳入口。
- VM 用规范化端点（去末尾斜杠）+模型名生成非秘密路由摘要，与握手返回的实际部署摘要比较；Runtime 在每次供应商调用前再次从真实部署环境核对摘要。不同端点上的同名模型会拒绝，路由摘要不包含凭据；完整配置 fingerprint 仍用于 VM 重检固定配置，不能冒充 Runtime 的凭据验证。Runtime 只用部署环境提供的固定模型地址/名称/密钥，包中不含模型 Key、PG 连接或后台私密资料。运行进度写回 VM，浏览器仅轮询 VM。

## 本地复现

复用主项目 `.venv` 的已安装依赖，不向其安装包。测试先在进程中加载现有私有 `BANFEI_TEST_DATABASE_URL`（不要打印），仅接受专用本机 PG 和随机 `validation_*` schema。

```bash
cd /home/yuan/project/lingjian-agent-agentarts
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD" \
  /home/yuan/project/lingjian-agent-enablement/.venv/bin/python -B -m pytest \
  -q -p no:cacheprovider backend/tests/test_agentarts_runtime.py
```

浏览器：`scripts/validate_agentarts_browser.py` 要求 `BANFEI_EXISTING_NODE_MODULES` 和 `BANFEI_EXISTING_CADDY` 指向已有只读依赖。脚本在 `/tmp` 建源码副本，只在副本调整原测试固定端口，使用19080/19180/19280/19300/19800回环及独立 Caddy XDG。测试网关只是本地每会话实例模拟，不声称已验证平台路由。

有限真实模型：`scripts/validate_agentarts_real_model.py --execute --runtime-environment <现有私有环境文件>`；从现用配置只读取得已批准 DeepSeek 的模型设置，使用合成夹具，最多5次请求、零超时重试。真实 Key 仅注入本地临时 Runtime 子进程，不写入任务包/测试库/镜像/日志；不要无目的重复执行。

## 镜像与下一步

- `Dockerfile` 仅复制 Runtime 与两份纯 Python 公共模块、标准分类字典，不包含 VM、数据库驱动、Office、上传文件或环境配置。镜像非 root、8080、单 worker；`Dockerfile.dockerignore` 使用白名单。基础镜像按 digest 固定，16项依赖精确版本及官方 PyPI wheel 哈希锁定；ARM64 wheel 下载已核验。
- 用户批准官方 Docker apt 源、Engine/CLI/containerd/Buildx 安装与本地 Unix socket 服务。本轮已由用户在本机完成；`install-docker-wsl.sh` 保留为安装记录，不重跑。脚本不加入 docker 组、不设免密 sudo、不开放远程 TCP，不注册 binfmt。
- Docker Engine 29.8.2 / Buildx 0.37.1 已安装，服务active；当前用户无Docker socket权限且sudo仍需交互。镜像尚未构建、运行或扫描。ARM64 binfmt/模拟器的系统级变更仍需具体说明后批准，不能因基础镜像已有ARM清单就声称本机已能构建ARM镜像。
- 后续已具备构建能力时，从仓根用 `docker buildx build --platform linux/arm64 -f deploy/agentarts/Dockerfile -t banfei-runtime:local --load .`；本说明不自动执行 sudo、特权注册或上传。
- 云端拟用 HTTPS PREFIX_MATCH 的 `/runtimes/<name>/invocations` 根地址；实现了服务器端 Bearer 与 `X-Hw-Agentarts-Session-Id`，IAM签名尚未实现/测试。另有 `X-Banfei-Runtime-Key` 用于应用层校验，其平台转发需实测。正式凭据、SWR区域/仓库、运行时名称和镜像上传需先确定目的地并获授权。
- `BANFEI_RUNTIME_URL`、`BANFEI_AGENTARTS_BEARER`、`BANFEI_RUNTIME_SHARED_KEY` 只在 VM 服务端；Runtime 使用 `BANFEI_RUNTIME_MODEL_URL/NAME/KEY` 与同一共享校验密钥。HTTPS 外发默认关闭，另需显式 `BANFEI_RUNTIME_EXTERNAL_DATA_APPROVED=1`。这不是用户授权的替代：真实伙伴资料外发范围必须先确认。
- 尚待验证：真实 AgentArts 网关/会话路由、认证和header转发、15分钟空闲/24小时生命周期、云端网络与计费、ARM64容器、正式两业务平台端到端与用户确认后的切换/回退。

历史原始验收证据由操作者本地保留；脱敏最终结论见 `docs/validation/AGENTARTS_RELEASE_20261003.md`。

### 待批准的本机 ARM64 操作

`build-arm64-local.sh` 是供用户本机交互 sudo 的可审阅脚本，尚未执行。使用 Ubuntu noble 官方包（apt 索引 SHA256 `5bb397f66063efa349f6fd5cb3b68cd96f29edd0994e4ba5115cf0859a716bf0`）内已校验的 QEMU，只注册临时 ARM64 binfmt 项；特权操作前把精确注册名/路径同步到 `cleanup-state.txt` 并立即打印。正常清理先注销并核对条目确实消失，才删除本脚本 root 临时解释器；注销失败则保留解释器并报告残留，不假称成功。不安装其他架构注册、不改 docker 组/sudoers/TCP、不使用特权容器。SIGKILL/WSL 异常终止可能阻止 trap 清理，需读取持久记录按准确注册名及路径复核；不确定目录归属时保留，不清理其他条目。

批准后用户在 WSL 运行 `bash /home/yuan/project/lingjian-agent-agentarts/deploy/agentarts/build-arm64-local.sh`。脚本以 sudo 构建固定基础镜像/哈希依赖的 ARM64 本地镜像，再以非 root、无网络、只读根文件系统运行健康/认证/非法包冒烟；零模型调用，无 PG 或真实资料挂载。保留本地镜像和 `/tmp/banfei-arm64-image-*` 证据，不上传镜像。


### SWR 清单兼容修复（2026-10-02，待用户重构建）

用户推送 `swr.cn-southwest-2.myhuaweicloud.com/banfei/banfei-runtime:agentarts-local-20261002145622` 在层上传后收到 `Invalid image, fail to parse 'manifest.json'`。既有 `/tmp/banfei-arm64-image-HXSqlp/image-inspect.json` 明确记录顶层 `application/vnd.oci.image.index.v1+json`；`build.log` 同时记录 attestation manifest 与 manifest list 导出。这是已证实的镜像格式事实；未登录读取远端仓库或服务端日志，最终修复成功仍须新格式推送结果确认。

[华为云官方同报错 FAQ](https://support.huaweicloud.com/swr_faq/swr_faq_0006.html)说明基础版 SWR 不支持 OCI 镜像，并给出 `--provenance=false`。按 [Docker image exporter 文档](https://docs.docker.com/build/exporters/image-registry/)显式使用 `oci-mediatypes=false`、`push=false`、`store=true`；[默认 Docker driver](https://docs.docker.com/build/builders/drivers/docker/)会加载到本机 image store。

现有 `build-arm64-local.sh` 改为单 `linux/arm64`、`--provenance=false --sbom=false --output type=image,oci-mediatypes=false,push=false,store=true`，固定已有 default builder；不增加 builder、守护进程、端口、权限或云操作。构建后必须在 inspect 中观察到单 Docker V2 manifest（`application/vnd.docker.distribution.manifest.v2+json`）和 ARM64 才继续原无网络冒烟；不是期望格式则明确失败，不自动上传。日志新增 `format-check.log`，新 tag 前缀为 `banfei-runtime:agentarts-swr-`。未改 Dockerfile、业务代码、基础镜像或依赖。

用户仍只需本机运行原命令并自行确认 sudo：

```bash
bash /home/yuan/project/lingjian-agent-agentarts/deploy/agentarts/build-arm64-local.sh
```

这会按此前已授权范围临时注册 ARM64 binfmt、构建及冒烟并清理。助手未再次执行特权操作，未读取 Docker 认证文件或 `/tmp/banfei-swr-auth.*`，未代用登录凭据。重构建后先检查 format-check/smoke/cleanup，再由用户将新 tag 推送到原已指定仓库；旧 tag 不变，不把既有层 Pushed 视为整个镜像发布成功。

选用 `type=image` 而不是 `--load`：已核 [Buildx v0.37.1 源码](https://github.com/docker/buildx/blob/v0.37.1/build/opt.go#L450-L504)，无文件输出的 docker exporter 在 OCI importer 可用时可能改为 OCI；显式 image exporter 在已有 Docker driver 下进入 moby exporter，并保留 `oci-mediatypes=false` 属性。无需新建 builder 或改变 daemon 存储。参数路径有官方资料/源码依据；本轮仅离线验证，实际新镜像格式仍由构建后的严格检查判定。

离线验证证据：`/tmp/banfei-swr-format-4gxoohs4`。现存 OCI index 被拒绝，合成 Docker V2 ARM64 接受，amd64/manifest list/缺 Descriptor 均拒绝，共5项通过；bash语法检查通过。未执行新构建或上传。
