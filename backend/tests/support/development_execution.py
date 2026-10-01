"""Run accepted conversations to completion before asserting their business outcome."""
import time
from backend.app import development_engine as engine, development_views as views


def finish(result, user, *, execute=True):
    if execute:
        engine.execute(result['run_id'])
    deadline=time.monotonic()+5
    while time.monotonic()<deadline:
        detail=views.detail(result['plan_id'],user)
        run=next(r for r in detail['runs'] if r['id']==result['run_id'])
        if run['status'] not in ('pending','running'):
            return detail,run
        time.sleep(.01)
    raise AssertionError('Accepted conversation did not finish')


def answer(result,user):
    detail,run=finish(result,user)
    assert run['status']=='ready',run
    assert detail['conversation']
    return detail['conversation'][-1]['answer']
