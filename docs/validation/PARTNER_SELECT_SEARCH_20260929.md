# 伙伴选择搜索验证（2026-09-29）

## 改动范围

- 新任务「伙伴发展」的目标伙伴选择。
- 后台伙伴资料的所属伙伴筛选。
- 新增资料、编辑资料及旧资料归类共用的关联伙伴选择。

三个控件统一使用 `frontend/components/partner-select.tsx`。按伙伴名称片段搜索，英文忽略大小写；只筛选调用方已有权限的选项，不增加接口。支持整行点击、方向键、回车、Esc、Tab 和中文输入法；仅输入搜索词不会改变所选伙伴 ID。保留「全部伙伴」、必选限制、编辑回显、来源任务锁定及原有筛选参数。

下拉层使用普通 React 浮层，避开之前出现 Edge 鼠标崩溃的原生展开控件；挂载到 body，避免首页输入容器及后台弹窗裁切。表单提交、任务幂等、模型调用、权限和数据库均未修改。

## 本轮实际验证

| 检查 | 结果 |
|---|---|
| `npm run typecheck` | 通过 |
| `BANFEI_BUILD_CPUS=2 npm run build` | 通过，开发服务停止后单独构建 |
| `partner-select.spec.ts` | 15/15 通过：5 个场景 × 3 个视口 |
| `task-failure.spec.ts` 中新建发展任务超时与丢失创建响应回归 | 6/6 通过：2 个场景 × 3 个视口 |
| `git diff --check` | 通过 |

视口为 1366×768、1920×1080、390×844，使用 WSL Playwright Chromium。合成 500 家伙伴，验证中文片段、英文大小写、未找到、键盘/IME、取消搜索保留原选项、来源锁定、筛选清空、分页重置及新建/编辑提交真实 ID。截图与点击坐标检查确认浮层可见可点击、没有横向溢出。未将 WSL 结果等同于 Windows Edge 或 ARM 验证。

全部业务 API 在浏览器端拦截，测试写操作只更新内存夹具；无模型请求、无运行库写入。测试复用当前开发服务的静态页面，通过现有可信 CA 获取资源，不关闭 TLS 校验。证据保存在 `/tmp/banfei-partner-select-ui/`：`run.log`、`result.json`、`regression.log`、`regression-result.json` 及 `results/` 截图。

类型检查及构建日志分别为 `/tmp/banfei-partner-select-typecheck.log`、`/tmp/banfei-partner-select-build.log`。构建前只读核实运行中匹配任务和发展 Run 均为 0，再通过项目脚本停止已核验归属的服务；没有开发、测试、构建同时写 `.next`。

构建后已恢复原前后端及 Caddy；可信 HTTPS 的新任务页、伙伴资料页和 `/api/health` 均返回 200。

现有 8 份受影响 UI 测试已将原生 `selectOption` / ID 值断言调整为新控件的选择及 ID 断言，并将新测试加入默认 UI 子集；这不代表本轮运行过全部历史 UI 套件。当前 main 保留此前未提交改动，本轮不提交、不推送、不部署。
