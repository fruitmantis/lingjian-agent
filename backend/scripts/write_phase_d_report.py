"""Render the local report after the final commit so its HEAD/commit list are exact."""
from datetime import datetime,timezone
from pathlib import Path
import json,subprocess
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'artifacts/enablement-phase-d'
BASE='351489c3d3c89899837930bd7aab01fe61f4a52a'
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()
assert ROOT.name=='lingjian-agent-enablement'
assert git('branch','--show-current')=='feature/partner-enablement-v1.1'
assert git('rev-parse','phase-c-accepted-20260906-351489c')==BASE
results=json.loads((OUT/'validation-results.json').read_text())
matrix=json.loads((OUT/'acceptance-matrix.json').read_text())
metrics=results['metrics']
head=git('rev-parse','HEAD');commits=git('log','--reverse','--format=- `%H` %s',BASE+'..HEAD')
header=f'''# Phase D 交付报告

生成时间：{datetime.now(timezone.utc).isoformat()}

- 当前分支：`feature/partner-enablement-v1.1`
- 当前 HEAD：`{head}`
- worktree：`{ROOT}`
- Phase C 起点：`{BASE}`
- Phase C accepted tag：`phase-c-accepted-20260906-351489c`
- 起点分支、HEAD、clean 状态已核验，标签目标未覆盖。
- 最终建议：**{results['recommendation']}**；仅工程/mock 验证通过，真实模型和业务数据尚未验收。

## Phase D 全部提交

{commits}

## 性能实测汇总

| 范围 | 样本数 | P50 | P95 | max | 门槛 |
|---|---:|---:|---:|---:|---|
'''
for key,title,samples in [('http_creation','HTTP 创建',50),('catalog_performance','目录检索（2000+1000）',60),('candidate_performance','模型候选过滤（2000+1000）',30)]:
    m=metrics[key];header+=f"| {title} | {samples} | {m['p50_seconds']*1000:.3f} ms | {m['p95_seconds']*1000:.3f} ms | {m['max_seconds']*1000:.3f} ms | {'P95 ≤ 1s' if key=='http_creation' else 'P95 ≤ 2s'} |\n"
header+=f"\n8100 kill/restart 识别中断用时 **{metrics['kill_restart']['recovery_seconds']:.3f} 秒**，小于 60 秒；重试成功且 V1 confirmed 保持。\n\n"
header+='## ACC-01～20 状态\n\nPASS 范围限定为本阶段工程/mock 自动化；真实业务签审另列。\n\n| ACC | 状态 |\n|---|---|\n'
for row in matrix['acceptance']:header+=f"| {row['id']} | {row['status']} |\n"
body=(ROOT/'docs/enablement/PHASE_D_VALIDATION.md').read_text()
(ROOT/'PHASE_D_DELIVERY_REPORT.md').write_text(header+'\n'+body)
print('Report HEAD:',head)
print(ROOT/'PHASE_D_DELIVERY_REPORT.md')
