> **历史归档，不是当前开发规范。** 保留当时的需求、环境、测试和结论；旧品牌、分支、端口、数据库及授权状态均不代表当前 main。历史命令不可直接用于现有运行库。当前入口：[README](../../../README.md)。

# 行业与区域标准化记录

本轮仅更新功能分支 feature/partner-enablement-v1.1。未提交、未合并、未推送。

## 运行库与保护

- 当前运行库：`/home/yuan/project/lingjian-agent-enablement/.isolation/runtime/dev/app.db`。沿用原文件，未重建、替换、清空或初始化。
- 一致性备份：`/home/yuan/project/lingjian-agent-enablement/.isolation/runtime/dev/taxonomy-backups/before-20260908T032945278330Z.db`，使用 SQLite Connection.backup()。
- 私有逐记录审计：`/home/yuan/project/lingjian-agent-enablement/.isolation/runtime/dev/taxonomy-backups/updates-20260908T032945278330Z.json`，包含每个 id/字段的 before/after，不进入 Git。
- schema 仍为 12；sqlite_master hash 未变。全部表行数、非目标字段逐表 hash 未变。
- integrity_check = ok；foreign_key_check 仍为 cases rowid 3/4 → partners 的两条既有异常，新增 0。
- 旧版 3000/8000 不登录、不写库。验证仅用 /tmp，开发服务恢复显式跳过 lifespan 初始化。

## 标准与实现

- 唯一字典：`shared/business-taxonomy.json`，前端组件与后端校验共同读取；无第二套枚举。
- 行业：互联网、安平、部委与公共事业、教育医疗、零售、汽车、能源电力、交通物流、制造与工业、运营商、金融、中长尾。
- 国内为 34 个省级区域（含直辖市、自治区及港澳台省级表示）；海外为：亚太、中东中亚、拉美、欧洲、北部非洲、南部非洲。
- 支持跨国内/海外同时多选。API region_groups 为 [{region_type: domestic|overseas, regions: [...]}]；仍存入原 service_areas TEXT，兼容原逗号分隔接口。行业复用 industries TEXT；需求/机会复用各自原 TEXT 字段。
- 新写入只接受标准值；确定性别名在历史投影、模型结构化输出及本次数据修正时归一。未知旧值保留并由 classification_pending 单独提示，标准筛选、统计与模型结构化字段不使用它们。
- 伙伴新增/编辑/详情/摘要/筛选，任务内机会编辑，需求与机会统计筛选，匹配及画像模型上下文已统一；自然语言画像、项目需求、案例说明不做全文替换。
- 场景广场只有业务场景/能力分类，不存在独立行业/区域字典，本轮不新增。
- 筛选同一维度内按多选 OR，行业与区域之间按 AND。

## 本次原地 UPDATE

| 表 | 字段 | UPDATE 数 |
|---|---|---:|
| partners | industries | 30 |
| partners | service_areas | 32 |
| demand_profiles | industry_tags | 19 |
| demand_profiles | region_tags | 6 |
| project_opportunities | industry | 19 |
| project_opportunities | region | 7 |

共 113 条字段 UPDATE，涉及 78 条记录。在一次 BEGIN IMMEDIATE / COMMIT 内完成；有条件 UPDATE 校验旧值，任一步失败 ROLLBACK。没有修改 updated_at、用户、密码、任务、模型配置、Plan/Run/Version、案例关系等字段。

| 数据 | 前 | 后 |
|---|---:|---:|
| users | 2 | 2 |
| partners | 36 | 36 |
| cases | 6 | 6 |
| match_records | 48 | 48 |
| demand_profiles | 48 | 48 |
| project_opportunities | 48 | 48 |
| enablement_resources | 13 | 13 |
| development_plans | 12 | 12 |
| development_runs | 15 | 15 |
| development_versions | 14 | 14 |

## 待业务确认

原值保留在原记录，未擅自归到“中长尾”或扩展成所有省份。管理员后续确认归类后再针对这些值做原地修正。

- 行业：IT分销、企业培训、企业服务、传媒、供应链、信创、公共安全、农业、司法、国防、城管、大型企业、媒体、家电、工业互联网、应急、建筑、快消品、房地产、政企、政务、政务服务、政府、文旅、新能源制造、新能源电池、智慧园区、智慧城市、智慧矿井、机械、物联网、电信、电子、矿山、租赁、航空、财政、贸易、车联网、通信、钢铁、高科技。
- 区域：30+省市、上海和华东区域、俄罗斯、全国、华东、华中、华北、华北（北京）、华南、海外地区、港澳台地区、西北、西南。

## 验证

- 相关后端命令：`.venv/bin/python -m pytest backend/tests/test_business_taxonomy.py backend/tests/test_profile.py backend/tests/test_demand.py backend/tests/test_recommendations.py backend/tests/test_authorization.py backend/tests/test_v12_agent.py backend/tests/test_enablement_workspace.py backend/tests/test_historical_repair.py -q`：142 passed，0 failed。
- 最终保守别名调整后，标准化定向测试再次 21 passed。
- `npm run typecheck`、`npm run build`：通过。
- `npm run test:e2e -- business-taxonomy.spec.ts unified-entry.spec.ts development-assistant.spec.ts`：7 passed，0 failed；1366×768、1920×1080。
- 测试日志：`/tmp/taxonomy-pytest-final.log`、`/tmp/taxonomy-new-pytest-final.log`、`/tmp/taxonomy-{typecheck,build,e2e}.log`。
- 测试使用 /tmp 隔离库与 loopback mock，真实模型调用 0。第一次兼容回归发现两个旧测试将“未识别”作为正式行业提交；按新标准将清空操作改为空集合后通过，没有放宽标准校验。

## 回退方式

- 应用前备份与完整字段审计均已保留；不得以快照替换运行 app.db。
- 如需撤回数据修正，应在同一个 BEGIN IMMEDIATE 事务内，按私有审计逐条验证当前字段等于 after，再将该字段 UPDATE 为 before；如出现后续人工编辑冲突则停止并 ROLLBACK。其他列不动。
- `scripts/normalize_business_taxonomy.py` 不包含初始化/seed/DDL，仅允许本 worktree 的 runtime/dev/app.db 或 /tmp；默认 dry-run，显式 --apply 才写入。

## 字段值前后对照（按相同变更合并）

### partners

| 字段 | 修改前 | 修改后 | 记录数 |
|---|---|---|---:|
| industries | 政务,金融,电力,制造 | 政务,金融,能源电力,制造与工业 | 1 |
| industries | 高科技,通信,银行,企业金融,保险,能源,交通,公用事业 | 高科技,通信,金融,能源电力,交通物流,部委与公共事业 | 1 |
| industries | 政府,金融,能源电力,制造,电信,互联网,交通,水利,公共事业 | 政府,金融,能源电力,制造与工业,电信,互联网,交通物流,部委与公共事业 | 1 |
| industries | 金融,政府,电信,制造,能源 | 金融,政府,电信,制造与工业,能源电力 | 1 |
| industries | 医疗,政务,电信,教育,制造 | 教育医疗,政务,电信,制造与工业 | 1 |
| industries | 快消零售,汽车,金融,医疗,政企,教育,运营商 | 零售,汽车,金融,教育医疗,政企,运营商 | 1 |
| industries | 金融,物联网,通信,制造 | 金融,物联网,通信,制造与工业 | 1 |
| industries | 教育,政务,交通,制造 | 教育医疗,政务,交通物流,制造与工业 | 1 |
| industries | 政务,国防,公共安全,交通 | 政务,国防,公共安全,交通物流 | 1 |
| industries | 医疗,金融,政务,能源 | 教育医疗,金融,政务,能源电力 | 1 |
| industries | 制造,零售,金融,政务,建筑 | 制造与工业,零售,金融,政务,建筑 | 1 |
| industries | 制造,零售,金融,政务 | 制造与工业,零售,金融,政务 | 1 |
| industries | 政府,金融,电信,能源,制造 | 政府,金融,电信,能源电力,制造与工业 | 1 |
| industries | 金融,制造,零售,医疗,政府 | 金融,制造与工业,零售,教育医疗,政府 | 1 |
| industries | 金融,制造,能源,政府,医疗 | 金融,制造与工业,能源电力,政府,教育医疗 | 1 |
| industries | 金融,制造,能源,政府,医疗,零售 | 金融,制造与工业,能源电力,政府,教育医疗,零售 | 1 |
| industries | 金融,制造,零售,通信,能源 | 金融,制造与工业,零售,通信,能源电力 | 1 |
| industries | 金融,政府,电信,制造 | 金融,政府,电信,制造与工业 | 1 |
| industries | 保险,银行,证券,医疗,政务,教育,交通,农业,能源,电力,通信,航空,工业制造 | 金融,教育医疗,政务,交通物流,农业,能源电力,通信,航空,制造与工业 | 1 |
| industries | 文旅,医疗,通信,金融,能源,政务,互联网 | 文旅,教育医疗,通信,金融,能源电力,政务,互联网 | 1 |
| industries | 教育,政务,企业培训 | 教育医疗,政务,企业培训 | 1 |
| industries | 证券,基金,金融,期货 | 金融 | 1 |
| industries | 制造,金融,贸易,通信,电子商务,传媒,房地产 | 制造与工业,金融,贸易,通信,互联网,传媒,房地产 | 1 |
| industries | 金融,制造,政府,通信,医疗 | 金融,制造与工业,政府,通信,教育医疗 | 1 |
| industries | 政府,金融,制造,企业服务 | 政府,金融,制造与工业,企业服务 | 1 |
| industries | 证券,基金,银行,金融 | 金融 | 1 |
| industries | 银行,金融,农业,政务,信创 | 金融,农业,政务,信创 | 1 |
| industries | 银行,证券,保险,信托,基金,租赁,金融 | 金融,租赁 | 1 |
| industries | 制造 | 制造与工业 | 2 |
| service_areas | 30+省市,港澳台地区,亚太地区,海外地区 | 30+省市,港澳台地区,亚太,海外地区 | 1 |
| service_areas | 北京,上海,深圳,广州,南京,成都,西安,武汉 | 北京,上海,广东,江苏,四川,陕西,湖北 | 2 |
| service_areas | 北京,上海,深圳,广州,成都,杭州,南京,武汉 | 北京,上海,广东,四川,浙江,江苏,湖北 | 1 |
| service_areas | 沈阳,大连,北京,上海,南京,成都 | 辽宁,北京,上海,江苏,四川 | 1 |
| service_areas | 北京,上海,深圳,广州,成都 | 北京,上海,广东,四川 | 3 |
| service_areas | 南京,上海,北京,深圳,西安 | 江苏,上海,北京,广东,陕西 | 1 |
| service_areas | 长沙,北京,深圳,广州 | 湖南,北京,广东 | 1 |
| service_areas | 南京,北京,上海,深圳,武汉 | 江苏,北京,上海,广东,湖北 | 1 |
| service_areas | 北京,上海,成都 | 北京,上海,四川 | 1 |
| service_areas | 北京,上海,深圳,广州 | 北京,上海,广东 | 3 |
| service_areas | 深圳,北京,上海,广州 | 广东,北京,上海 | 1 |
| service_areas | 济南,北京,上海,深圳 | 山东,北京,上海,广东 | 1 |
| service_areas | 北京,上海,深圳,香港 | 北京,上海,广东,香港 | 2 |
| service_areas | 上海,北京,香港,深圳,广州,成都,重庆,大连,杭州,南京,武汉,厦门,西安 | 上海,北京,香港,广东,四川,重庆,辽宁,浙江,江苏,湖北,福建,陕西 | 1 |
| service_areas | 北京,上海,深圳,大连 | 北京,上海,广东,辽宁 | 1 |
| service_areas | 深圳,南京,武汉,北京,广州,东莞,福州,贵阳,香港 | 广东,江苏,湖北,北京,福建,贵州,香港 | 1 |
| service_areas | 北京,南京,广州,成都,武汉,西安 | 北京,江苏,广东,四川,湖北,陕西 | 1 |
| service_areas | 北京,广州,上海,深圳 | 北京,广东,上海 | 1 |
| service_areas | 重庆,北京,上海,深圳 | 重庆,北京,上海,广东 | 1 |
| service_areas | 福州,上海,深圳,北京 | 福建,上海,广东,北京 | 1 |
| service_areas | 广州,北京,上海,深圳,香港,佛山,武汉,成都,济南 | 广东,北京,上海,香港,湖北,四川,山东 | 1 |
| service_areas | 上海,北京,广州,成都,西安,青岛,武汉,深圳 | 上海,北京,广东,四川,陕西,山东,湖北 | 1 |
| service_areas | 上海,北京,深圳 | 上海,北京,广东 | 1 |
| service_areas | 深圳,北京,上海 | 广东,北京,上海 | 1 |
| service_areas | 北京,上海,深圳,广州,成都,西安,合肥,南京,威海 | 北京,上海,广东,四川,陕西,安徽,江苏,山东 | 1 |
| service_areas | 北京,上海,深圳,大连,南京,成都,西安,武汉 | 北京,上海,广东,辽宁,江苏,四川,陕西,湖北 | 1 |

### demand_profiles

| 字段 | 修改前 | 修改后 | 记录数 |
|---|---|---|---:|
| industry_tags | 煤矿,智慧矿井,能源 | 能源电力,智慧矿井 | 1 |
| industry_tags | 教育 | 教育医疗 | 1 |
| industry_tags | 汽车,智能网联汽车,车联网 | 汽车,车联网 | 1 |
| industry_tags | 公共事业,水务 | 部委与公共事业 | 1 |
| industry_tags | 银行金融 | 金融 | 1 |
| industry_tags | 能源 | 能源电力 | 2 |
| industry_tags | 航空交通 | 交通物流 | 1 |
| industry_tags | 银行 | 金融 | 1 |
| industry_tags | 金融证券 | 金融 | 1 |
| industry_tags | 保险,金融 | 金融 | 1 |
| industry_tags | 制造业,工业互联网 | 制造与工业,工业互联网 | 1 |
| industry_tags | 电子制造 | 制造与工业 | 1 |
| industry_tags | 煤炭,矿山,能源 | 能源电力,矿山 | 1 |
| industry_tags | 电力 | 能源电力 | 1 |
| industry_tags | 水务,智慧水务 | 部委与公共事业 | 1 |
| industry_tags | 燃气,能源,公共事业 | 能源电力,部委与公共事业 | 1 |
| industry_tags | 智慧城市,政务,交通,城管,应急 | 智慧城市,政务,交通物流,城管,应急 | 1 |
| industry_tags | 医疗 | 教育医疗 | 1 |
| region_tags | 深圳 | 广东 | 1 |
| region_tags | 广东广州 | 广东 | 1 |
| region_tags | 华南,深圳 | 华南,广东 | 1 |
| region_tags | 成都,西南 | 四川,西南 | 1 |
| region_tags | 德国 | 欧洲 | 1 |
| region_tags | 青岛 | 山东 | 1 |

### project_opportunities

| 字段 | 修改前 | 修改后 | 记录数 |
|---|---|---|---:|
| industry | 航空交通 | 交通物流 | 1 |
| industry | 银行 | 金融 | 1 |
| industry | 能源行业 | 能源电力 | 1 |
| industry | 金融证券 | 金融 | 1 |
| industry | 保险 | 金融 | 1 |
| industry | 制造业 | 制造与工业 | 1 |
| industry | 电子制造 | 制造与工业 | 1 |
| industry | 煤炭/矿山/能源 | 能源电力,矿山 | 1 |
| industry | 电力 | 能源电力 | 1 |
| industry | 水务 | 部委与公共事业 | 1 |
| industry | 燃气 | 能源电力 | 1 |
| industry | 医疗 | 教育医疗 | 1 |
| industry | 金融/银行 | 金融 | 1 |
| industry | 教育 | 教育医疗 | 1 |
| industry | 汽车/车联网 | 汽车,车联网 | 1 |
| industry | 公共事业/智慧水务 | 部委与公共事业 | 1 |
| industry | 银行金融 | 金融 | 1 |
| industry | 能源 | 能源电力 | 1 |
| industry | 汽车零部件制造 | 汽车 | 1 |
| region | 广东广州 | 广东 | 1 |
| region | 深圳 | 广东 | 2 |
| region | 山西、陕西 | 山西,陕西 | 1 |
| region | 北京、河北 | 北京,河北 | 1 |
| region | 江苏省 | 江苏 | 1 |
| region | 成都 | 四川 | 1 |


## 最终运行确认

- 新版 http://localhost:3100 与 8100 /health 返回 200，mock 18180 /health 返回 200，保持运行。
- 旧版 8000 /health 返回 200，3000/8000 原进程未变；旧版数据库及原始 runtime/app.db hash 未变。
- 已将新版本后端的实际 LINGJIAN_DATABASE_PATH 与上述 dev/app.db 再次对照。
- 数据修改完成后的前端复验：typecheck 通过，build 通过，相关 Playwright 7 passed；测试过程未改变开发运行库 hash。
- 最终保护证据：`/tmp/taxonomy-protection-final.json`。本轮未提交 Git，现有其他未提交改动保留。
