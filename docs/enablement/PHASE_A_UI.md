# Phase A 管理后台交付批次

新增 `/admin/resources`，复用 App Shell / apiFetch / require_admin；提供课程和实验元数据、正式标签、多用途授权、核验记录、发布/下架/敏感撤权和发布版本概览。未知时长留空，费用/难度未知显式显示。草稿未保存时禁用发布与授权操作，避免丢失编辑；服务端重复校验revision，拒绝旧页面覆盖。

原 `/admin/partners/{id}` 的每个案例增加“共享设置”，进入 `/admin/partners/{id}/cases/{caseId}/sharing`；手动维护脱敏摘要、可学习方法、实际角色和来源入口，不预填/复制内部案例正文。共享配置继续使用原case_id。没有新增普通用户中心、外部伙伴账号、课程播放器、实验执行、模型管理系统或方案执行链。

验证（2026-09-06，新worktree，合成数据）：

- `npm run build`：通过。
- `npm run typecheck`：通过（最终重检通过）。
- `npm run test:e2e -- enablement-admin.spec.ts`：6 passed，0 failed/skipped。
- `npm run test:e2e`：43 passed，0 failed/skipped，包含原37项回归及新增6项。
- 所有6张新后台截图均使用合成资源/账号，1366×768、1920×1080无页面横向溢出；编辑页允许正常纵向滚动。
- 最终链接校验复核补齐浏览器数字地址127.1/十六进制变体拦截；专项后端52 passed，0 failed/skipped。不请求来源URL，不自动探测外链。

截图见 `artifacts/enablement/`：resource-list、resource-editor、case-sharing，各有1366/1920版本。基线/完整原功能截图以及Playwright trace仅保存在忽略目录；没有用含真实需求的截图替换旧基线。

业务验收未执行：截图中的资源、管理员核验及授权全部是自动化合成数据，不能当作真实资源可用/已获授权的业务证明。
