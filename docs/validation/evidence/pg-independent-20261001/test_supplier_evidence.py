"""Supplement the old eight supplier cases with per-mode transport evidence.

The original test and its assertions are invoked unchanged. A list observer
records which server mode actually received each HTTP request; final failure
codes are read through an independent psycopg connection.
"""
import json
import os

import pytest
from catalog_audit import direct
from backend.tests.test_development_lifecycle import prepared
from backend.tests.test_development_engine import scenario
from backend.tests.test_phase_d_model_and_samples import supplier
from backend.tests.test_phase_d_model_and_samples import (
    test_loopback_supplier_schema_error_timeout_and_retry as original_check,
)


@pytest.mark.parametrize('mode',['normal','markdown','empty','invalid','enum','http_error','slow','dribble'])
def test_fault_mode_reaches_supplier(scenario,supplier,monkeypatch,mode,caplog,record_property):
    observed=[]
    class Requests(list):
        def append(self,request):
            observed.append(supplier['mode'])
            super().append(request)
    supplier['requests']=Requests()
    original_check(scenario,supplier,monkeypatch,mode,caplog,record_property)
    assert mode in observed, 'Fault never reached supplier HTTP handler'
    with direct(os.environ['DATABASE_URL']) as conn:
        actual=conn.execute('SELECT current_database() AS db,current_schema() AS schema').fetchone()
        result=conn.execute('SELECT status,safe_error_message FROM development_runs WHERE submission_id=%s',
                            ('supplier-revise-'+mode,)).fetchone()
    assert result['status']==('ready' if mode=='normal' else 'failed')
    code=None
    if mode!='normal':
        code=json.loads(result['safe_error_message'])[0]['code']
        expected='timeout' if mode in ('slow','dribble') else 'provider' if mode=='http_error' else 'invalid_result'
        assert code==expected
    record_property('actual_supplier_injection',json.dumps({'requested_mode':mode,
        'http_handler_modes':observed,'actual_database':actual,'failed_run_code':code}))
