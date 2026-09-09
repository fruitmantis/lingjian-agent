> **历史归档，不是当前开发规范。** 保留当时的需求、环境、测试和结论；旧品牌、分支、端口、数据库及授权状态均不代表当前 main。历史命令不可直接用于现有运行库。当前入口：[README](../../../../README.md)。

# Phase D 冻结与验证范围

Phase C accepted：`351489c3d3c89899837930bd7aab01fe61f4a52a`，开始前分支 `feature/partner-enablement-v1.1`、HEAD、clean 工作区均实测一致；本地标签 `phase-c-accepted-20260906-351489c`。

稳定版 main：`f79cbb29ec7b3ad70c88e618e3161211f211c06a`。稳定版代码、数据库、配置及上传目录只做文件读取/哈希；不打开稳定 SQLite，不登录、不写审计或会话。保留原进程 8000/3000，只有本次新建进程可停止。

唯一需求定义读取自 V1.1 §27，并读取 §27.1、§27.2、§28、§29。源文档 SHA-256：`4ab64c866d7d08893b6206ef14adc7a1a3ddcab5edac39b87dda9863ed8f857a`。矩阵包含 53 个 P0（含 2 个 P0-业务），排除 RES-06/10 P1 和 SEC-10 未来范围。旧报告仅用于定位测试，不继承 PASS。

## 隔离与执行

- worktree：`/home/yuan/project/lingjian-agent-enablement`；依赖 `.venv`、`frontend/node_modules`；构建 `frontend/.next`。
- 独立运行数据 `.isolation/runtime` 保留，创建官方 SQLite backup `.isolation/snapshots/phase-d-pre.db`，不进入 Git。
- pytest 数据 `/tmp/lingjian-pytest-*` / pytest tmp_path；进程故障库 pytest tmp_path；E2E `/tmp/lingjian-enablement-e2e`。均为独立合成数据。
- 新版浏览器 3100 / API 8100 / mock 18180；独立进程故障测试只 kill 自己 Popen 创建且核验 cwd/cmdline 的 8100 子进程。其他旧回归使用自动分配的 loopback 端口。
- typecheck/build 完成后才启动 Playwright，避免同一 `.next` 并发写入。
- 真实模型 **BLOCKED - USER AUTHORIZATION REQUIRED / NOT RUN / 0 CALLS**。不沿用历史 DeepSeek 批量任务授权；不修改稳定模型场景绑定。
- 真实业务数据 **DATA-01 / DATA-02 = BLOCKED - BUSINESS DATA REQUIRED**；合成 fixture 不进入正式 seed。

## 产品代码修正范围：NFR-04 时限边界

新增回归先复现：开始时间超过 601 秒的 running Run，无读取/重启时，保存未拒绝（1 failed，私有日志 `phase-d-deadline-before.log`）。

修正使用现有 SQLite 执行权与线程机制：默认模型 180 秒 / Run 600 秒，显式测试配置只允许缩短；Run 看门定时器主动标记 interrupted 并释放执行权；模型适配器设置请求超时，并使用 asyncio.timeout 对整次请求进行到期取消；进入后续模型阶段以及保存事务前后均检查 Run 执行权/时限。迟到结果不能创建版本；已有 current/confirmed 保留。未变更 schema、接口或外发字段。

后续分段慢回包也复现总耗时超过配置上限，已改为整次调用到期取消。测试默认值、非法/超大配置回落、短 slow mock、分段回包、无读取的 Run 超时、重试、旧确认版本、四处事务故障。180 秒和 10 分钟采用同一路径的短时限注入，不声称实际等待完整时长。

## 明确不做

不增加业务功能、不改变伙伴外发白名单、不接真实模型、不导入正式资源、不 merge/push/deploy。外发文案可读性仅评估与提出后续建议。最终结论必须分别说明工程/mock、真实模型、资源数据与业务试点。
