"""Render ignored local readiness report with final commit identity after archival."""
import hashlib,json,subprocess
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BASE='dda1af4914aec68f96cd0ae481caae732eea655d'
TAG='pilot-data-intake-ready-20260906-dda1af4'

def git(*args):return subprocess.check_output(['git','-C',str(ROOT),*args],text=True).strip()

def main():
    assert not git('status','--porcelain')
    assert git('branch','--show-current')=='feature/partner-enablement-v1.1'
    assert git('rev-parse',TAG)==BASE
    evidence=json.loads((ROOT/'artifacts/pilot-import/validation-results.json').read_text())
    for name,digest in evidence['source_sha256'].items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest
    header=f'''# Pilot Import Readiness 交付报告

- 生成时间：{datetime.now(timezone.utc).isoformat()}
- Intake accepted tag：`{TAG}` → `{BASE}`
- 分支：`{git('branch','--show-current')}`
- worktree：`{ROOT}`
- 最终 HEAD：`{git('rev-parse','HEAD')}`
- 归档后工作区：**clean**
- 本轮提交：

{git('log','--reverse','--format=- `%H` %s',BASE+'..HEAD')}

'''
    (ROOT/'PILOT_IMPORT_READINESS_REPORT.md').write_text(header+(ROOT/'docs/enablement/PILOT_IMPORT_READINESS.md').read_text())
    assert not git('status','--porcelain')
    print(json.dumps({'head':git('rev-parse','HEAD'),'clean':True,'readiness':'READY FOR REAL PILOT PACKAGE IMPORT','real_model_calls':0}))

if __name__=='__main__':main()
