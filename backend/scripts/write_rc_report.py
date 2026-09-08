"""Render the ignored local RC report with exact final HEAD after reviewed commits."""
from pathlib import Path
from datetime import datetime,timezone
import subprocess,json
ROOT=Path(__file__).resolve().parents[2]
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()
BASE='78e70ac0f3e258d3f4ce51a8ca60455a8887028d';TAG='phase-d-engineering-accepted-20260906-78e70ac'
assert git('branch','--show-current')=='feature/partner-enablement-v1.1'
assert git('rev-parse',TAG)==BASE
r=json.loads((ROOT/'artifacts/enablement-rc/validation-results.json').read_text())
header=f'''# RC Preparation 交付报告

生成时间：{datetime.now(timezone.utc).isoformat()}

- Phase D engineering accepted tag：`{TAG}` → `{BASE}`
- 当前分支：`{git('branch','--show-current')}`
- 当前 HEAD：`{git('rev-parse','HEAD')}`
- 工作区：{'clean' if not git('status','--porcelain') else '有未提交变更'}
- worktree：`{ROOT}`
- 本轮提交：

{git('log','--reverse','--format=- `%H` %s',BASE+'..HEAD')}

## 最终状态

| 验收维度 | 结论 |
|---|---|
| ENGINEERING | {r['engineering']} |
| REAL MODEL | NOT AUTHORIZED / NOT RUN / **0 CALLS** |
| BUSINESS DATA | BLOCKED |
| BUSINESS ACCEPTANCE | NOT RUN |
| 整体 | CONDITIONAL GO；不代表真实业务上线 GO |

全量后端：{r['backend']}；全量浏览器：{r['browser']}。typecheck / production build：PASS。新截图 {r['screenshots']} 张；清单见 `artifacts/enablement-rc/screenshot-manifest.json`。

'''
(ROOT/'RC_PREPARATION_REPORT.md').write_text(header+(ROOT/'docs/enablement/RC_VALIDATION.md').read_text())
print('RC report HEAD: '+git('rev-parse','HEAD'))
