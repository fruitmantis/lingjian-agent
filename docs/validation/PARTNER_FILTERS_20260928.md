# 伙伴洞察三维筛选验证（2026-09-28）

## 实施范围

按用户追加要求，在搜索框下增加能力标签、行业、区域筛选。保留当前 `feature/coze-ui` 分支及所有既有未提交修改，未提交、推送或部署。

- `frontend/app/partners/page.tsx`：筛选状态、组合过滤、结果数、清除及无结果重置。
- `frontend/components/opportunity-ui.tsx`：从既有多选下拉抽出 `MultiSelectFilter`，行业/区域原包装与后台调用方式保留；能力标签使用可搜索选项。
- `frontend/components/opportunity-ui.module.css`、`frontend/app/ui-system.css`：复用既有控件表面样式，补齐选项搜索框、长标签及伙伴页面响应式筛选布局。
- `frontend/components/partner-tag-list.tsx`：导出同一标签分项函数，确保筛选选项与卡片显示一致，不改变标签原文、顺序或数据。
- `frontend/e2e/partner-filters.spec.ts`：新增隔离浏览器行为验证；`business-taxonomy.spec.ts` 更新旧“没有筛选器”断言，本轮未执行该含数据库写入的集成用例。

能力选项来自现有 `/partners/profiles` 响应的伙伴能力，去重后按名称排序；完整标签精确匹配，不把相同前缀误当同一能力。行业/区域沿用 `shared/business-taxonomy.json` 和现有标准化函数，不使用未确认分类，不自行猜测。单维度多项为 OR，跨维度及关键词为 AND。清除筛选保留关键词；无结果时的重置同时清空关键词。

无接口、后端、权限、数据结构或模型调用改动，无新增数据请求或运行数据库写入。

## 实际检查

- `npm run typecheck`：通过。
- `BANFEI_BUILD_CPUS=2 npm run build`：通过，31 个静态页面生成完成。已核对本项目服务归属，先停止开发服务、构建完成后恢复，未并行写 `.next`。
- `git diff --check`：通过。
- Playwright 实际通过 10 个不同用例：伙伴筛选 4 项、既有伙伴标签 3 项、后台项目机会筛选 3 项。
- 首轮 9 通过 / 1 失败：390px 用例尝试直接点击被已展开菜单覆盖的下一个筛选器。测试调整为点击搜索框收起菜单后再切换，新增筛选 4 项复测全部通过（11.2 秒），无需为该操作顺序修改产品代码。两次原始报告及最终按用例汇总见 `artifacts/partner-filters/`。
- WSL Chromium，100% 缩放，1366×768、1920×1080、390×844：筛选位于搜索框下，无页面水平溢出；窄屏纵向排列，弹出选项内部限高滚动。
- 覆盖能力精确匹配/去重/搜索、单维度多选、三维度与关键词交集、国内与海外同时选择、结果数、清除/重置、无结果、加载失败、Escape 恢复焦点及焦点移出关闭。原卡片标签汇总和详情导航回归通过。
- 浏览器所有业务 API 由合成数据拦截，无真实模型请求、API 写请求或页面脚本错误。截图等待字体加载完成，不包含真实身份 Key。
- 本轮未实测 Windows Edge 或 ARM，不将 WSL 检查视作这些平台验证。

## 截图

- [1366 桌面](../../artifacts/partner-filters/partners-1366.png)
- [1920 桌面](../../artifacts/partner-filters/partners-1920.png)
- [390 窄屏](../../artifacts/partner-filters/partners-390.png)
- [组合筛选](../../artifacts/partner-filters/filtered-1366.png)
- [国内与海外区域多选](../../artifacts/partner-filters/region-open-1366.png)
- [汇总结果](../../artifacts/partner-filters/verification.json)
