# Coze UI 纯视觉精修验收（2026-09-28）

- 分支：`feature/coze-ui`；HEAD / 首批基线：`9296aecf105b81eb550c5cf6c52ae46c69fa849b`。
- 精修前基线是本轮开始时的**已有未提交 Coze UI 改版**，不是 main 原版。保留首批全部改动、首批截图与原报告；未切换分支、创建 worktree、commit、push、合并或部署。
- 范围：字体及视觉样式。后端、数据库、业务接口、模型流程、页面信息结构、内容、字段和展开方式未改。

## 字体取证与选择

用户亲自在本机 Edge 登录 `www.coze.cn` 工作界面后，检查 CSS、全部已注册 `@font-face`、清缓存后的字体网络请求和 CDP 实际渲染字体：中文为 Microsoft YaHei；英文/数字为 Segoe UI，500/600 选到 Segoe UI Semibold，700 选到 Bold。该页 CSS 的 `Inter` 名称并非实际使用字体，也无正文字体网络请求。WSL 结果单独记录，不冒充 Windows。

系统字体不直接打包。项目采用 Google Fonts 官方 **Noto Sans SC 可变字体**（SIL OFL 1.1），完整 WOFF2、许可证及固定来源提交均已保存到 `frontend/public/fonts/noto-sans-sc/`。实际中文、英文和数字均使用本地字体；字重轴 100–900，400/500/600/700 的字形轮廓已验证有区别，CSS 禁用字体合成。字体共 30,890 个字符编码，覆盖当前业务源码出现的全部 727 个中文字符。完整文件约 7.4 MiB，首次本地加载较原 Latin 文件大；无构建/运行时外部字体服务依赖。

详细取证、字体来源及样式规范：[设计记录](../design/COZE_VISUAL_REFINEMENT_20260928.md)。

## 实际修改

本轮相对开始时快照，仅四个产品代码文件改变：

- `frontend/app/globals.css`：本地字体、真实字重、文字/中性灰 token、圆角；保留原 Logo 字标字体和 700 字重。
- `frontend/app/ui-system.css`：共用阅读文字、内部说明块、风险提示、控件、标签、表格、弹窗及克制阴影。
- `frontend/app/coze-workspace.css`：沿用首批布局，调整正文 16/26、卡片标题 17/26/600、字号与间距；侧栏 #F7F7F5，内部块 #F4F4F3。
- `frontend/app/page.tsx`：将已有行内视觉属性改为共享样式类，去掉需求卡片红色外框，减轻风险底色和边框。移除 style/className 后，TypeScript JSX AST 与本轮前快照一致；节点、文字及事件处理未变。

测试补充：`coze-polish.spec.ts`、`playwright.polish.config.ts`；首批合成数据提取到 `coze-fixtures.ts` 复用，旧字体验证 helper 更新为本地中文可变字体。首批回归截图改存本轮独立目录，不覆盖原验收证据。旧设计文档仅追加指向当前规范的说明。

## 验证结果

| 验证 | 实际结果 |
|---|---|
| `npm run typecheck --prefix frontend` | 通过 |
| `npm run build --prefix frontend` | 通过，31 个静态页面生成成功 |
| 现有 PostgreSQL 隔离入口 + `--config=playwright.polish.config.ts` | **20 / 20 通过**，约 3.2 分钟 |
| 本轮前三尺寸基线采集 | **3 / 3 通过** |
| 窗口 / 缩放 | 1366×768、1920×1080、390×844；deviceScaleFactor=1，浏览器缩放=1 |
| 同内容对比 | 14 个状态 × 3 尺寸 = **42 个状态**，修改前后文字完全一致 |
| 截图 | 每状态都有单屏、完整页面、正文/卡片局部；前后各 **126 张** |
| 字体 | 等待 document.fonts.ready；真实中英数字字体 / 400、500、600、700 均核验为自托管字体；禁缓存、拦截外部来源，无外部字体请求 |
| 页面与操作 | 首页双 Tab 和伙伴选择、首页已有匹配结果、两类任务正文、底部追问、版本/运行记录、证据/风险/失败提示；课程/实验/案例筛选、详情与跳转；后台模型表格/表内编辑、用户表格/编辑弹窗 |
| 窄屏 / 滚动 | 42 个状态均无 document 横向溢出；宽后台表格在原局部容器滚动，底部输入区和操作仍可访问 |
| 范围 / Git | 本轮 JSX 去视觉属性后 AST 一致；`git diff --check` 通过；原未提交改动保留 |

测试使用现有 `banfei_agent_test` 专用 PostgreSQL 的临时 schema。浏览器业务数据全部为合成 fixture；无业务模型调用、无运行库测试写入。截图屏蔽密码/身份 Key 元素，不包含真实业务身份或材料。

开发服务先按项目脚本停下，浏览器测试完成退出后单独 build，然后按原配置恢复服务，未并行写同一 `.next`。前几次截图脚本暴露了拦截通配符过宽、异步内容未稳定、CDP 非直接文本节点等测试问题；均已修正，最终 20 项重新完整通过，不把早期失败算作通过。

WSL Chromium 验证了伴飞 UI；Windows Edge 验证了 Coze 实际字体及本地对比页。没有执行 ARM 或 Windows Edge 伴飞业务流程回归，不将限定 UI 回归称为全量业务验收。

## 预览恢复

原入口 `https://172.21.208.223` 已恢复。现有 Caddy 根证书校验通过；`/login`、`/api/health` 和本地 WOFF2 均返回 200。后端、前端与 Caddy 归属当前项目且均在运行。只做 HTTP / health 读取，没有在运行库创建测试身份或任务。

## 交付物

- [交互式前后对比页](../../artifacts/coze-polish/review.html)：已在本机 Edge 新标签打开。
- [本轮测试结果](../../artifacts/coze-polish/test-results-summary.json)
- [产品变更范围检查](../../artifacts/coze-polish/scope-verification.json)
- [字体文件与字重验证](../../artifacts/coze-polish/font-file-verification.json)
- [Windows Edge 的 Coze 字体证据](../../artifacts/coze-polish/reference/coze-edge-font-evidence.json)
- `artifacts/coze-polish/before/`、`after/`：同内容截图、布局与字体测量；`regression/` 为首批相关操作回归截图。

首批精修到此停止，等待用户视觉确认，不继续扩展页面信息结构或实施其他业务改动。


## 后续反馈：卡片边框不可辨识

补回场景/伙伴目录原本被 border:0 取消的边框，并将现有实体卡片统一为 1px #D4D4D0。共享目录卡片 min-width:0 修复了场景页既有的窄屏内容撑宽问题。仅修改三个共享 CSS 文件；不改正文、字段、信息结构或业务处理。三种尺寸共 15 个页面状态通过浏览器验证，typecheck / build / diff 检查通过。新证据独立保存，不覆盖此前对比截图：[卡片边框修正](../../artifacts/card-border-fix/README.md)。
