# Pilot 历史兼容模板

此目录保留的 JSON 是 **V1.1 SQLite Pilot 预检/导入工具的兼容输入**，不是当前伴飞能力发展页面或 PostgreSQL 导入规范。不要把其中培训长表单、人工差距确认、三类资源路径要求恢复到产品；当前普通输入只有伙伴 + 自然语言方向。

当前运行库为 PostgreSQL 16 / schema 12，使用 [正式 README](../README.md) 的配置。`scripts/validate_pilot_data.py`、`scripts/import_pilot_data.py` 只用于显式 SQLite 兼容验证，不能对 `banfei_agent` 使用。没有实现或宣称 PostgreSQL Pilot 批量导入能力。

- [历史接收说明](../docs/archive/v1.1/pilot-data/README.md)
- [历史签审模板](../docs/archive/v1.1/pilot-data/business-signoff.template.md)
- [当前业务验收模板](../docs/validation/REAL_BUSINESS_ACCEPTANCE_TEMPLATE.md)

模板不是正式数据；实际业务材料、签审原件和数据库不得提交 Git。旧报告生成器保留历史实现，不应在 main 上为复现历史结论而运行。
