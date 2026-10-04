# AgentArts ARM 隔离部署

## 阶段三 v2 更新（2026-10-04，替代下方旧 v1 操作指引）

两个正式 Runtime 已由用户各自执行握手通过，protocol=banfei-runtime-v2，workflow
分别为 match/development，provider_endpoint 均为
7800aeda488c5317424e42954f4ba0912e28983bb79a320f0692f802ceb8060c。
matching 原先 401 的根因未得到证实；新增原因码是诊断能力，不等于修复根因。
matching 新镜像 tag 尚未提供，不能依据握手回推镜像 digest。

本次复用已有 banfei-agentarts 账号、PG 55432、前端 3001、后端 8001 和独立 Caddy HTTP 80。
主干服务保持停止，不迁移或覆盖 main。旧版已部署，阶段三需要更新源码及前端构建；
使用新 release 目录保留旧 current 目标作为代码回退点，不重新复制伙伴、用户、上传或初始化数据库。
后台元数据的阶段三迁移会归档旧场景绑定；保留历史任务，失败不覆盖已有结果。

新版本部署后，用户在 ARM 自己的 SSH 交互终端运行：

    sudo python3 -B /opt/banfei-agentarts/current/deploy/agentarts/arm/configure_runtime_v2.py

按顺序隐藏输入匹配平台 Key、匹配应用 shared key、发展平台 Key、发展应用 shared key，
平台 Key 均为原始值，不含 Bearer。工具只更新既有 /etc/banfei-agentarts/backend.env 的四个
分智能体凭据和 BANFEI_RUNTIME_EXTERNAL_DATA_APPROVED=0，保留其他配置；不自动备份密钥、
不重启服务、不写数据库，默认不联网。可显式加 --verify，在保存后各发一次 v2 握手 GET；
握手失败会明确说明配置已保存，不能误认为事务未发生。
默认权限检查及四次隐藏输入均成功后才原子替换；无法隐藏输入时拒绝，不作明文降级。

部署窗口同时通过后端 systemd 的 UnsetEnvironment=BANFEI_RUNTIME_EXTERNAL_DATA_APPROVED
阻止旧环境中的授权值被继承；需获后续具体资料范围批准后再移除此部署闸门并设置环境授权。
用户录入密钥后仅在无在途任务时重启隔离后端，以加载新值。不能运行下方旧 v1
configure_runtime.py、configure_private.py 或旧 preflight.py --phase configured；
旧流程会检查 v1/直连地址或要求外发开关=1。

后台通过正常管理员登录设置（凭据不进入网页）：

- 新建不含 Key 的模型元数据连接：
  https://banfei-model-proxy-defaultgw-gzswgzdcgz.cn-southwest-2.huaweicloud-agentarts.com/inference/v1
  模型名称 deepseek-v4.1-flash；保留确认过的模型参数，不调用连接测试。
- 伙伴匹配选择 Runtime，URL：
  https://defaultgw-gzswgzdcgz.cn-southwest-2.huaweicloud-agentarts.com/runtimes/banfei-matching/invocations?endpoint=Latest
- 能力发展选择 Runtime，URL：
  https://defaultgw-gzswgzdcgz.cn-southwest-2.huaweicloud-agentarts.com/runtimes/banfei-development/invocations?endpoint=Latest
- 两者选择上述元数据连接；thinking、超时、重试在对应智能体表单保存，基础处理保持 local。
  未取得具体业务资料外发批准前，不创建业务测试任务、不更新画像或触发模型处理。

最小先决条件：独立服务/目录/PG 已存在、原 main 应用停机、无在途任务、现有管理员可正常登录；
四个云 Key 由用户持有。若这些条件不满足，先处理具体阻塞，不重置账号或数据库。
仅回退 current 不能自动撤销已提交的数据库元数据变更；回退前须核对迁移与旧版兼容性，
不得为回退覆盖真实业务数据。


2026-10-02 UTC 已部署基础入口、独立前端、独立 PostgreSQL 和目录副本。当时业务 API 因私有配置缺失明确关闭。该段为历史准备记录；当前部署及验证结论见 [脱敏归档](../../../docs/validation/AGENTARTS_RELEASE_20261003.md)，原始现场证据本地保留。

## 实际部署

- 原版 `576926a`、5432、3000/8000 和 IP 入口保留。原版前后端与共享 Caddy 未重启，PID 为18259/18260/18261。
- 新代码 `/opt/banfei-agentarts/releases/20261002-agentarts-arm-prep`，独立venv `/opt/banfei-agentarts/venv`；`current` 指向新发布。两个专用系统账号使用独立组、锁定密码、nologin，无SSH目录或sudo授权。
- `banfei-agentarts-postgres.service`：PG16独立postmaster，127.0.0.1:55432，数据 `/var/lib/banfei-agentarts-pg/data`，私有socket `/run/banfei-agentarts-pg`。peer管理员 `banfei_agentarts_admin`，业务角色 `banfei_agentarts_app` 无superuser/createdb/createrole/replication权限。本轮不生成密码，业务角色TCP认证不可用。
- `banfei-agentarts-frontend.service`：127.0.0.1:3001，完整ARM生产构建通过。`banfei-agentarts-backend.service`：预留127.0.0.1:8001，因 `private-config-ready` 不存在而保持停止；两条服务都要求 `data-copy-ready`。前端不依赖后端启动成功。
- 新上传 `/var/lib/banfei-agentarts/uploads`，临时目录 `/var/lib/banfei-agentarts/tmp`，日志 `/var/log/banfei-agentarts`，Next缓存 `/var/cache/banfei-agentarts/next`。代码root只读，应用与PG数据互不可读，原版代码/资料/PG/家目录不可读。服务开启NoNewPrivileges/PrivateTmp/ProtectSystem/ProtectHome；不添加资源限额。
- 新站点 `http://banfei-agentarts.test` 使用共享Caddy80。已合并 `Caddyfile.maintenance.fragment`，精确核对Caddy进程后SIGUSR1平滑加载；原IP站点块及全局设置保留。新站点页面200、所有 `/api` 返回明确待配置503，不发Cookie、不创建身份/任务。`Caddyfile.fragment`是后续业务就绪后的正常代理模板，当前未启用。
- 用户已完成Windows hosts；助手只读解析确认为当时指定服务器地址。但Windows访问原IP和新域名HTTP均10秒超时；ARM主机内Host路由通过不代表公网或Windows浏览器通过。不修改TUN、网络、防火墙、SSH、TLS或新公网端口。

## 目录副本

基线 `arm-catalog-576926a-s19-92c35b4e64df`，9表逐行一致（仅152个上传路径换为新根目录），152文件逐一SHA256一致，schema19，全部外键有效。179伙伴、76文档、1案例、173资源、301版本；3个画像冲突已按源DOCX与版本证据解决。

用户明确不迁移任何个人历史，新匹配/发展历史为空。两条资源来源作者保留引用ID，名称统一“来源作者（不可登录）”、role=user、status=disabled、密码NULL，未导入原用户资料/Key/会话。所有认证和历史表计数为0。实际执行脚本有目标库必须为空及目标上传目录必须为空的保护，禁止对已复制实例重跑。

## 运行时与未完成私有配置

运行时根URL固定为 `https://defaultgw-gzswgzdcgz.cn-southwest-2.huaweicloud-agentarts.com/runtimes/banfei-runtime-test/invocations?endpoint=Latest`；子路径插在query前。新模型记录为 `https://api.deepseek.com` + `deepseek-flash`，VM没有模型APIKey；两执行器为runtime，缺认证不回退本地模型。原版模型未改。

平台已创建运行时不等于认证通过。当前缺少平台APIKey、已轮换SHARED_KEY，以及新VM数据库密码/DSN、JWT签名键、身份Fernet键和首次管理员。本轮没有生成、读取或传输这些秘密。

后续用户在自己的已授权root交互终端输入两项运行时凭据：

```text
/opt/banfei-agentarts/venv/bin/python /opt/banfei-agentarts/current/deploy/agentarts/arm/configure_runtime.py --verify
```

该命令只更新root:root0600的新环境文件，并发起一次runtime-info认证GET，保留endpoint=Latest，校验协议/incarnation/deepseek-flash路由；不创建任务、不调用模型、不重启服务。无TTY或getpass隐藏输入不可用时立即拒绝；第二次提示失败也不部分写入。不得把密钥贴入聊天、命令行或管道。

这条命令**不配置本地数据库/应用密钥、不创建管理员、不解除维护闸门**。其他独立秘密必须由用户在私有配置流程提供；首次管理员需单独初始化：现有main.py仅当users总数为0时自动bootstrap，而目录副本已有2条禁用作者记录。不能通过清空/替换作者记录规避。后续仅在独立配置、管理员、真实认证及新后端验证通过后，才创建 `private-config-ready`、启动新后端并切换新主机名的维护路由。原版服务不参与此流程。

## 可复查证据

远端 `/root/banfei-agentarts-deploy-20261002/`：`catalog_copy.py`实际复制脚本、`schema.sql`、`catalog-copy-verification.json`、`entry-verification.json`、`isolation-verification.json`、`p2-handoff-verification.json`、构建和安装日志。本地副本 `/tmp/banfei-agentarts-arm-deploy-oz5s4xwu/`。

最终离线测试19项、34子场景通过；ARM无TTY拒绝及两次提示降级测试通过，配置不变。P2修复只更新交接脚本及测试，未重启前端或原版。无commit、push或付费模型调用。
