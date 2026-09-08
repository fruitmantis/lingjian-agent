"""Read-only stable-service checks. Never authenticate or open the stable SQLite database."""
import hashlib,json,subprocess,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
STABLE=Path('/home/yuan/project/lingjian-agent')

def git(where,*args):return subprocess.check_output(['git','-C',str(where),*args],text=True).strip()
manifest=json.loads((ROOT/'.isolation/evidence/phase-c-stable-start.json').read_text())
changed=[name for name,digest in manifest.items() if not (STABLE/name).is_file() or hashlib.sha256((STABLE/name).read_bytes()).hexdigest()!=digest]
assert not changed,f'Protected file hash changes: {len(changed)}; investigate privately'
assert git(STABLE,'branch','--show-current')=='main'
assert git(STABLE,'rev-parse','HEAD')=='f79cbb29ec7b3ad70c88e618e3161211f211c06a'
assert not git(STABLE,'status','--porcelain')
assert git(ROOT,'rev-parse','phase-b-accepted-20260906-4b0850d')=='4b0850d0cff3c277269868dcd8cef06f72de9dfc'
processes={}
for pid,cwd in [(227786,STABLE),(236033,STABLE/'frontend')]:
    actual=Path(f'/proc/{pid}/cwd').resolve();assert actual==cwd
    processes[str(pid)]=str(actual)
# The only stable HTTP request allowed by the Phase C instruction.
with urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=5) as response:health=json.load(response)
assert health['status']=='ok'
listeners=subprocess.check_output(['ss','-ltnp'],text=True)
for port in (3100,8100,18180):assert not any(f':{port} ' in line for line in listeners.splitlines()),'New validation listener remains'
for port in (3000,8000):assert any(f':{port} ' in line for line in listeners.splitlines())
private=ROOT/'.isolation/runtime';files=[p for p in private.rglob('*') if p.is_file()]
assert all(not p.is_symlink() and p.stat().st_nlink==1 and p.resolve().is_relative_to(private) for p in files)
assert not any(p.is_symlink() for p in private.rglob('*'))
result={'stable_branch':'main','stable_head':git(STABLE,'rev-parse','HEAD'),'stable_git_clean':True,'protected_file_count':len(manifest),'changed_protected_files':0,'stable_database_check':'file SHA-256 only; no SQLite connection or authentication','stable_health':'ok','stable_processes':processes,'new_ports_stopped':[3100,8100,18180],'runtime_regular_file_count':len(files),'runtime_links_to_old_data':0,'stable_logins':0,'real_model_calls':0,'remote_verified':False}
output=ROOT/'artifacts/enablement-phase-c/protection-verification.json';output.write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False))
