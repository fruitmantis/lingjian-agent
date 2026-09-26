# Pilot 历史工具（archived）

**归档工具不属于当前支持范围。** 此目录保留 V1.1/V1.2 时期 SQLite schema 12 的 Pilot 预检、导入模板及签审资料，不是当前伴飞页面或 PostgreSQL 导入规范。当前 main 的服务启动、管理员流程及部署说明均未调用这套工具；当前课程/实验导入使用华为云资源导入工具，见[当前导入记录](../docs/validation/HUAWEI_RESOURCE_IMPORT.md)。

归档范围：

- `scripts/validate_pilot_data.py`、`scripts/import_pilot_data.py`、`scripts/pilot_import_contract.py`。
- `scripts/collect_pilot_intake_evidence.py`、`scripts/collect_pilot_import_evidence.py`、`scripts/write_pilot_intake_report.py`、`scripts/write_pilot_import_report.py`。
- `backend/tests/test_pilot_intake.py`、`backend/tests/test_pilot_import.py`，以及本目录模板和原有历史证据。

这些脚本和断言原位保留，不保证与当前资源契约兼容，不用于当前运行库。不得为恢复历史测试而恢复培训长表单、人工差距确认、旧资源字段或人工核验流程，也不要运行引用旧工作区的历史取证/报告脚本。当前 PostgreSQL 配置与数据保护规则以[正式 README](../README.md)为准。

## 测试边界

两份历史测试统一标记 `archived`，根目录 `pytest.ini` 默认排除。schema 17 移除旧案例 API 后，`backend/tests/conftest.py` 还在默认收集阶段排除这两个模块，避免导入已经退出当前架构的契约。普通 pytest 和正式 PostgreSQL 验证入口口径一致；88 项归档数量来自归档当时的收集记录，不计为当前通过数。

查阅历史清单请打开两份测试源码及 [2026-09-25 归档记录](../docs/validation/PILOT_ARCHIVE_20260925.md)。当时的 `-m archived --collect-only` 结果仅证明当时基线可收集；pytest 收集本身会导入 Python 模块，当前 schema 17 不保证该命令还能运行。因此不再将它作为当前核验指令，不执行历史夹具，也不恢复旧 API 来满足它。需要调查历史行为时先明确旧提交与隔离环境，不能对现有工作区/运行库回退、seed 或导入。

- [本次归档核验](../docs/validation/PILOT_ARCHIVE_20260925.md)
- [历史接收说明](../docs/archive/v1.1/pilot-data/README.md)
- [历史签审模板](../docs/archive/v1.1/pilot-data/business-signoff.template.md)
- [当前业务验收模板](../docs/validation/REAL_BUSINESS_ACCEPTANCE_TEMPLATE.md)

模板不是正式数据；实际业务材料、签审原件、数据库和私有配置不得提交 Git。历史脚本、文档和证据保留，不重新生成历史结论。
