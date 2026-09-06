"""Render the local Phase C delivery report with exact final HEAD and commit list."""
from datetime import datetime,timezone
from pathlib import Path
import json,subprocess
ROOT=Path(__file__).resolve().parents[2]
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()
assert ROOT.name=='lingjian-agent-enablement'
branch=git('branch','--show-current');assert branch=='feature/partner-enablement-v1.1'
head=git('rev-parse','HEAD')
commits=git('log','--reverse','--format=- `%h` %s','4b0850d0cff3c277269868dcd8cef06f72de9dfc..HEAD')
results=json.loads((ROOT/'artifacts/enablement-phase-c/validation-results.json').read_text())
assert results['backend']['failures']==0 and results['browser']['failed']==0
body=(ROOT/'docs/enablement/PHASE_C_VALIDATION.md').read_text()
header=f'''# Phase C 交付报告

生成时间：{datetime.now(timezone.utc).isoformat()}

- 当前分支：`{branch}`
- 当前 HEAD：`{head}`
- worktree：`{ROOT}`
- Phase C 起点：`4b0850d0cff3c277269868dcd8cef06f72de9dfc`
- Phase B 验收标签：`phase-b-accepted-20260906-4b0850d`
- 初始工作区 clean，标签目标已核验；未覆盖标签。

## Phase C 全部提交

{commits}

'''
(ROOT/'PHASE_C_DELIVERY_REPORT.md').write_text(header+body)
print('Report HEAD:',head)
print(ROOT/'PHASE_C_DELIVERY_REPORT.md')
