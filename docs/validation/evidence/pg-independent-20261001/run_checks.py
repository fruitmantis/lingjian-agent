"""Run only independent audit checks using the existing private PG test URL.

Usage: .venv/bin/python docs/validation/evidence/pg-independent-20261001/run_checks.py
Pass --supplier-only to run the eight added supplier-evidence checks alone.
Every invocation retains a fresh /tmp log and JUnit file; it never overwrites
the committed-review evidence or changes the running application configuration.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[4]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--supplier-only',action='store_true')
    args=parser.parse_args()
    settings=json.loads((ROOT/'.isolation/runtime/dev/validation-environment.json').read_text())
    env=dict(os.environ,BANFEI_TEST_DATABASE_URL=settings['BANFEI_TEST_DATABASE_URL'],PYTHONDONTWRITEBYTECODE='1')
    folder=Path(tempfile.mkdtemp(prefix='banfei-independent-review-'))
    targets=[Path(__file__).with_name('test_supplier_evidence.py')]
    if not args.supplier_only:targets.insert(0,Path(__file__).with_name('test_independent_pg.py'))
    command=[sys.executable,'-m','pytest','-p','backend.tests.conftest',*map(str,targets),
        '-q','--tb=short','-o','junit_family=xunit1','-o','cache_dir='+str(folder/'pytest-cache'),
        '--junitxml='+str(folder/'results.xml')]
    print('Audit output: '+str(folder),flush=True)
    with (folder/'results.txt').open('w') as stream:
        result=subprocess.run(command,cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT)
    print((folder/'results.txt').read_text())
    return result.returncode


if __name__=='__main__':raise SystemExit(main())
