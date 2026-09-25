# Pilot 历史工具（archived）

**归档工具不属于当前支持范围。** 此目录保留 V1.1/V1.2 时期 SQLite schema 12 的 Pilot 预检、导入模板及签审资料，不是当前伴飞页面或 PostgreSQL 导入规范。当前 main 的服务启动、管理员流程及部署说明均未调用这套工具；当前课程/实验导入使用华为云资源导入工具，见[当前导入记录](../docs/validation/HUAWEI_RESOURCE_IMPORT.md)。

归档范围：

- `scripts/validate_pilot_data.py`、`scripts/import_pilot_data.py`、`scripts/pilot_import_contract.py`。
- `scripts/collect_pilot_intake_evidence.py`、`scripts/collect_pilot_import_evidence.py`、`scripts/write_pilot_intake_report.py`、`scripts/write_pilot_import_report.py`。
- `backend/tests/test_pilot_intake.py`、`backend/tests/test_pilot_import.py`，以及本目录模板和原有历史证据。

这些脚本和断言原位保留，不保证与当前资源契约兼容，不用于当前运行库。不得为恢复历史测试而恢复培训长表单、人工差距确认、旧资源字段或人工核验流程，也不要运行引用旧工作区的历史取证/报告脚本。当前 PostgreSQL 配置与数据保护规则以[正式 README](../README.md)为准。

## 测试边界

两份历史测试统一标记 `archived`，由根目录 `pytest.ini` 默认排除；普通 pytest 和正式 PostgreSQL 验证入口采用相同口径。不是仅跳过三个失败断言，也不将排除的历史测试计为通过。当前功能的资源、导入、权限、事务、迁移与生命周期测试继续保留。

如需检查历史测试清单，可显式选择归档标记（只收集，不执行夹具或导入）：

```bash
.venv/bin/python -m pytest backend/tests/test_pilot_import.py backend/tests/test_pilot_intake.py -m archived --collect-only -q
```

移除 `--collect-only` 会显式执行历史测试，仅用于独立的 `/tmp` SQLite 兼容调查；可能失败，不属于当前支持或发布验证。本次只核对清单，没有执行历史导入、取证、报告或真实模型预检。

- [本次归档核验](../docs/validation/PILOT_ARCHIVE_20260925.md)
- [历史接收说明](../docs/archive/v1.1/pilot-data/README.md)
- [历史签审模板](../docs/archive/v1.1/pilot-data/business-signoff.template.md)
- [当前业务验收模板](../docs/validation/REAL_BUSINESS_ACCEPTANCE_TEMPLATE.md)

模板不是正式数据；实际业务材料、签审原件、数据库和私有配置不得提交 Git。历史脚本、文档和证据保留，不重新生成历史结论。
