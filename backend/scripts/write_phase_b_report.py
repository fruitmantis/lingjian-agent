"""Render the local delivery report after commits so its HEAD/list are exact."""
from datetime import datetime, timezone
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]

def git(*args):
    return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()

branch=git('branch','--show-current')
if branch != 'feature/partner-enablement-v1.1':
    raise SystemExit('Report must be generated from the accepted isolated feature branch')
head=git('rev-parse','HEAD')
commits=git('log','--reverse','--format=- `%h` %s','5408e2d6caaabc69d965226a1060d85f1f222019..HEAD')
body=(ROOT/'docs/enablement/PHASE_B_VALIDATION.md').read_text()
header=f'''# Phase B 交付报告

生成时间：{datetime.now(timezone.utc).isoformat()}

- 当前分支：`{branch}`
- 当前 HEAD：`{head}`
- 工作目录：`{ROOT}`
- Phase B 起点：`5408e2d6caaabc69d965226a1060d85f1f222019`（Phase A 已验收提交）
- 以下提交仅在此功能分支，未 merge、未 push、未进入 Phase C。

## Phase B 全部提交

{commits}

'''
output=ROOT/'PHASE_B_DELIVERY_REPORT.md'
output.write_text(header+body)
print(output)
print('Report HEAD:',head)
