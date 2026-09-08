"""Render the local report after the reviewed intake commit, without self-hash loops."""
import json
import subprocess
import sys
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.validate_pilot_data import validate,real_model_precheck

def git(*args):return subprocess.check_output(['git','-C',str(ROOT),*args],text=True).strip()

def main():
    assert git('branch','--show-current')=='feature/partner-enablement-v1.1'
    assert not git('status','--porcelain'),'Commit reviewed intake files before rendering final report'
    tag='rc-preparation-accepted-20260906-1a0b4b4'
    assert git('rev-parse',tag)=='1a0b4b4f081de63c617b366788e19d0090d19093'
    db=ROOT/'.isolation/runtime/app.db'
    gate=real_model_precheck(validate(ROOT/'pilot-data/pilot-manifest.template.json',db,True),db)
    assert gate['checks']['worktree_clean'] and gate['status']=='BLOCKED'
    evidence={'head':git('rev-parse','HEAD'),'worktree_clean':True,'real_model_precheck':gate,'real_model_calls':0}
    private=ROOT/'.isolation/evidence/pilot-intake-final-precheck.json'
    private.write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
    header=f'''# Pilot Data Intake 交付报告

生成时间：{datetime.now(timezone.utc).isoformat()}

- 分支：`{git('branch','--show-current')}`
- worktree：`{ROOT}`
- 最终 HEAD：`{git('rev-parse','HEAD')}`
- 最终工作区：**clean**（提交后实测）
- RC Preparation accepted tag：`{tag}`
- 当前真实模型前检：**{gate['status']}**；worktree_clean=true，其他数据/授权门禁未满足；真实模型 **0 CALLS**。
- 本轮提交：

{git('log','--reverse','--format=- `%H` %s','066f78262a2df7abebcf1215073db41c3052a009..HEAD')}

'''
    (ROOT/'PILOT_DATA_INTAKE_REPORT.md').write_text(header+(ROOT/'docs/enablement/PILOT_DATA_INTAKE.md').read_text())
    assert not git('status','--porcelain')
    print(json.dumps(evidence,ensure_ascii=False))

if __name__=='__main__':main()
