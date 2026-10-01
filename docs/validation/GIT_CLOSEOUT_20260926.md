> 2026-10-01 数据库清理说明：本文中的混合数据库数字仅为历史实测记录，不代表当前 PG-only 验证。当前规则见 [PG-only 验证](POSTGRES_ONLY_20261001.md)，不再执行文中的旧文件数据库路径。

# 2026-09-26 文档刷新与 Git 收口

用户明确要求先刷新项目 Markdown，再提交、推送，最后总结。本次整理已确认实现与文档；验证中只修复旧 Playwright 定位/夹具并补齐课程卡片漏接的既有共享悬停选择器，不新增业务功能，不部署、不重跑迁移或名单整理。收口前基线：`c7454be16b37b94cde49a92d90e3ba326ebc0974`；fetch 后 main 与 origin/main 无分歧。

## 提交范围

1. 六类资料原生文字处理、完整原件/文本、缓存预览、手动画像、单一案例展示，以及 schema 17 显式迁移代码与兼容测试。
2. 后台伙伴资料统一管理：全局和伙伴详情两个入口、三列分类卡片、原文件归类/替换、画像区域及普通可见内容。
3. 伙伴卡片和后台悬停统一、运营报表筛选排列/焦点/过时响应保护。
4. README、AGENTS、现行模型验证方法、历史验证边界、验证索引与项目交接。

私有环境、数据库、名单原件、真实上传材料、一次性名单脚本、快照、日志及测试产物均不提交；保留在原有私有位置。归档文档原文不重写为现行规则。

## 本次验证

以下为本轮重跑结果，不将此前阶段数字合并到通过数。

- 后端：`run_postgres_validation.py backend -q --junitxml=/tmp/banfei-closeout-backend.xml`，**810 passed / 0 failed / 0 skipped**，754.12 秒。JUnit 标记为 635 项 PostgreSQL、175 项既有 `/tmp` SQLite 兼容/迁移/进程用例；不是 810 项全为 PostgreSQL 原生测试。88 项 archived Pilot 在默认收集阶段排除，不计为通过或跳过。
- 非失败警告 15 条，涉及 PyPDF2 弃用、HTTP 422 常量弃用和既有 `record_property` / xunit2 格式提示；本轮不扩展依赖或功能调整。
- 前端：`npm --prefix frontend run typecheck` 与 `npm --prefix frontend run build` 均通过；悬停选择器及测试修正后又按顺序执行最终 typecheck/build，均退出 0。
- Playwright：修正后整组复验 **25 passed / 0 failed / 0 skipped**，3.3 分钟。使用专用 PostgreSQL 临时 schema 与显式本地 replay；覆盖 `partner-materials`、`enablement-admin`、`enablement-workspace`、`partner-delete`、`ui-system`、`business-taxonomy` 六个测试文件。
- 浏览器首轮：15 passed / 3 failed / 7 未运行。分类测试误命中新建输入框，已限定到保存后的分类行并等待保存结束；旧视觉测试仍查找已替换的课程卡片和旧案例响应，已适配现用结构。同时补齐 `.learning-card` 的共享悬停选择器。断言继续核验阴影、位移、焦点、减少动画、链接和窄屏布局，不恢复旧业务界面。
- 静态：git diff --check、更新文档的本地链接、候选文件中的私有配置值和产物检查。
- 正式数据：停服后和服务恢复后只读比对，**35 张表行数与内容摘要完全一致，6 个原件/预览 SHA-256 完全一致**；伙伴仍为 178 家。没有执行正式库迁移、seed、回填、导入或清理。
- 不调用真实模型；replay 仅供隔离工程验证，不代表供应商效果或人工业务验收。

本地临时日志与结果位于 `/tmp/banfei-closeout-*`，不进入 Git。

## 已完成的数据操作边界

以下操作属于本次 Git 收口之前的用户授权工作，本轮没有重复执行：

- schema 16 → 17 已完成，现库为 schema 17，旧案例共享/核验表已移除。
- 伙伴名单已精确整理为 178 家：保留 9 家、新增 169 家；清单外 26 家清理；佳杰云星合并到重庆伟仕宏翔科技发展有限公司，删除独立别名行。
- 名单整理的专属业务清理及混合匹配历史处理、完整备份、事务对账记录保存在 `.isolation/partner-roster/20260926/`。原件和预览保留，课程/实验、账号和模型配置未改变。
- 不把一次性名单操作变成日常强删接口；后台伙伴删除保护继续生效。名单脚本依赖操作前基线，不能重跑。

## Git 与运行状态

验证完成后通过 `enablement-dev.sh start` 恢复当前项目服务：8000 `/health`、3000 `/admin/partner-materials` 与 `/admin/reports` HTTP 200；测试回放的 18180 已退出。

代码分组 commit 如下；本文件随最后的 `docs: refresh project guidance and handoff` 文档提交保存。仅执行普通 `git push origin main`，不 force push、不部署。最终文档 commit 的 SHA 和推送后 `main == origin/main` / clean 状态由本轮最终回复及实时 Git 提供，文档不引用自身 commit。


| Commit | 功能 |
|---|---|
| `157c8d5` | 六类资料原生提取、预览、手动画像、案例展示及 schema 17 后端和回归 |
| `dbbdad2` | 统一伙伴资料管理界面、伙伴入口、附件/画像交互与相关浏览器回归 |
| `43555ad` | 目录卡片、后台交互、报表筛选及现行视觉回归 |

文档提交同步刷新 23 份 Markdown：当前指引、验证索引和交接说明采用现行口径；旧阶段结果保留并注明适用基线。
