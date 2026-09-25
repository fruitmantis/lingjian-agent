# 历史 Pilot 工具归档与正式后端验证

日期：2026-09-25。基线：main / a66c4b18679855858a00e523b6e933dad39f8c50。本次仅处理历史 Pilot 工具的支持范围、测试选择及文档，不修改现行业务功能或数据库。

## 调用核验

对 Git 跟踪的代码、脚本、包命令及运行/部署说明检查脚本名称、Python 导入与 Pilot 引用：

| 范围 | 当前调用情况 |
|---|---|
| `enablement-dev.sh` → `backend/scripts/enablement_environment.py` → `isolated_server.py` / Next.js | 不调用 Pilot；后端启动 `app.main:app` |
| `dev.sh`、`frontend/package.json`、仓库 ARM 运行说明 | 不调用 Pilot；仓库无另一个调用 Pilot 的部署或 CI 入口 |
| `backend/app/main.py`、业务路由及前端管理员页面 | 无 Pilot 导入或执行路径；课程/实验沿用当前资源 API |
| 当前华为云资源导入 | 使用 `import_huawei_resources.py`、`enrich_huawei_resources.py`，不依赖 Pilot |
| Pilot 导入、预检、证据契约和取证/报告脚本 | 仅历史工具互相引用；部分还硬编码旧分支、旧证据和历史工作区，未执行 |
| `test_pilot_import.py`、`test_pilot_intake.py` | 仅测试旧工具；原先由默认 pytest 收集，正是遗留失败进入正式测试的原因 |

结论：这套工具属于纯历史工具，明确标为 **archived**。归档工具不属于当前支持范围。没有访问旧工作区，也未运行历史导入、取证、报告或模型预检。

## 归档处理

- 七份 `scripts/*pilot*.py` 原位保留，只增加模块级归档说明；模板、签审资料和历史证据继续保留。
- 两份历史测试保留全部断言与夹具，只增加模块级 `archived` 标记。根目录 `pytest.ini` 注册标记，默认选择 `not archived`；普通 pytest 与正式 PostgreSQL 验证入口一致。
- 归档整个工具链的 **88 项**测试，而非仅跳过三个失败断言。默认选择仍包含现行资源、华为云导入、权限、事务、迁移及任务生命周期测试。
- README 和 [Pilot 目录说明](../../pilot-data/README.md) 写明支持边界与显式查看归档清单的方法。此前[三项失败记录](GIT_CLOSEOUT_20260925.md)保留，不改写为通过。
- 未适配旧资源字段，不恢复旧课程/实验人工核验或 V1.2 编辑流程。

## 验证

仅将私有验证配置加载到测试进程，不输出连接串。正式后端使用专用 PostgreSQL 测试库；原有 SQLite 兼容、迁移和进程故障测试仍只在 `/tmp` 执行，不将这些测试宣称为 PostgreSQL 路径。完整测试占用本地端口，先核验并停止本项目服务，结束后恢复。

| 检查 | 结果 |
|---|---|
| 默认 `pytest backend/tests --collect-only -q` | 876 项中选择 788 项，88 项归档排除；当前清单中没有 Pilot 测试 |
| 两份 Pilot 测试 `-m archived --collect-only -q` | 88 项可显式收集，包含此前三个失败用例；只检查清单，不执行旧夹具 |
| `.venv/bin/python scripts/run_postgres_validation.py backend -q` | **788 passed, 88 deselected**，0 失败、0 跳过；退出码 0，耗时约 12 分钟 |
| Python AST 对比 HEAD | 九份 Python 文件除模块说明和测试标记外完全一致，业务实现与历史断言均未改变 |
| `git diff --check` | 通过 |

JUnit 标记核对：595 项使用 PostgreSQL，193 项为原有 `/tmp` SQLite 兼容路径。另有 14 条非失败警告（11 条 `record_property` / JUnit xunit2 格式警告、3 条 HTTP 422 常量弃用警告），本次未扩展修改。

本地日志、JUnit XML、收集清单和只含数量/摘要的运行库核对文件保存在 `/tmp/banfei-pilot-archive-20260925/`，不进入 Git。

## 数据、服务与 Git

测试前后以只读事务核对 `banfei_agent` 的 38 张表，数量与内容摘要均一致。没有执行运行库迁移、导入、清理或重新 seed；测试数据仅位于专用验证库的临时 schema 和 `/tmp`。

测试结束后经 `enablement-dev.sh` 恢复本项目服务：3000 `/login` 与 8000 `/health` 均返回 HTTP 200。

以下为归档验证结束时的提交前快照，后续正式提交与推送以 Git 记录为准。

Git 保持 main，HEAD 与 origin/main 均为 `a66c4b18679855858a00e523b6e933dad39f8c50`；本次留下 13 个已跟踪文件修改和本验证说明 1 个新文件，均为归档标记、测试选择及文档。未 commit、未 push、未部署。
