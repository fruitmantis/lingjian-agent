"""Disposable format fixtures only. Never seed or import these as pilot business data."""
import copy
import hashlib
import json
import sqlite3
import socket
from pathlib import Path

import pytest
from backend.app.database import DATABASE_PATH, get_db
from backend.app import enablement as service
from backend.tests.conftest import make_partner, make_user
from scripts import validate_pilot_data as v


@pytest.fixture(autouse=True)
def forbid_network_and_model(monkeypatch):
    def forbidden(*args, **kwargs): raise AssertionError('Network/model forbidden in intake tests')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr('backend.app.development_model.completion', forbidden)


@pytest.fixture
def package(client, tmp_path):
    admin = make_user('intake-reviewer', role='admin')
    make_partner()
    with get_db() as conn:
        conn.execute("UPDATE partners SET name='格式校验对象' WHERE id='partner-1'")
        conn.execute("INSERT INTO cases VALUES ('intake-case','partner-1','仅临时库内部标题',?,'2026-09-06')",(v.CANARY,))
        tag = conn.execute('SELECT id FROM capability_tags WHERE enabled=1 LIMIT 1').fetchone()[0]
    paths=[]
    for kind in ['course','lab','case']:
        meta = {'title':'离线格式校验资源','summary':'公开课程简介','source_platform':'资源提供方',
            'source_url':'https://learning.vendor.edu/path','capability_tag_ids':[tag]}
        if kind=='case': meta.update(methods='分阶段实践方法',contributor_role='实施职责')
        else: meta.update(resource_type=kind,target_capability='迁移交付',audience='工程师',product_direction='数据库',
            difficulty='beginner',language='中文',site='全球',prerequisites='基础操作',duration_minutes=60,
            cost='unknown',account_requirement='未知',environment_requirement='浏览器')
        domain = 'case' if kind=='case' else 'resource'
        source_id = 'intake-case' if kind=='case' else 'intake-'+kind
        save = service.ShareSave if kind=='case' else service.ResourceSave
        row=service.save(domain,source_id,save(base_revision=0,metadata=meta),admin['id'])
        row=service.permissions(domain,source_id,service.Permissions(base_revision=row['revision'],system_visible=True,
            model_allowed=True,partner_allowed=True,reason='本地格式验证授权'),admin['id'])
        rev=row['revision']
        row=service.review(domain,source_id,service.Review(base_revision=rev,link_status='available',content_checked=True,authorization_checked=True),admin['id'])
        row=service.publish(domain,source_id,service.Revision(base_revision=rev),admin['id'])
        review=row['reviews'][0]
        entry={'source_type':kind,'source_id':source_id,'source_version':row['published_version'],
            'contributor_id':'partner-1' if kind=='case' else None,'status':'published','metadata':meta,
            'permissions':{'base_revision':rev,'system_visible':True,'model_allowed':True,'partner_allowed':True,'reason':'本地格式验证授权'},
            'review':{'base_revision':rev,'link_status':'available','content_checked':True,'authorization_checked':True,'note':''},
            'reviewer_id':admin['id'],'reviewed_at':review['reviewed_at']}
        file=tmp_path/(kind+'.json');file.write_text(json.dumps(entry,ensure_ascii=False));paths.append(file.name)
    request=v.DevelopmentRequest(target_partner_id='partner-1',raw_demand='希望完成迁移交付',development_goal='完成迁移交付',
        trainee_role='工程师',trainee_count=2,known_baseline='已掌握基础操作',duration_weeks=4,hours_per_week=2,
        constraints={k:'无要求' for k in ('language','site','account','network','environment','cost','budget')},
        targets=[{'capability_tag_id':tag,'requirement':'完成迁移交付','confirmed_gap':True,'confirmation_note':'负责人确认'}],
        model_input_allowed=True).model_dump()
    manifest={'package_kind':'real','target_partner_name':'格式校验对象','allowed_diagnostic_scope':['仅批准的结构化目标与共享学习内容'],
        'request':request,'resources':paths[:2],'shared_cases':paths[2:],
        'resource_gaps':{'reviewed':True,'items':[],'no_known_gaps_reason':'本条格式路径资源类型齐全'}}
    file=tmp_path/'manifest.json';file.write_text(json.dumps(manifest,ensure_ascii=False))
    return file


def change(package, name, fn):
    file=package if name is None else package.parent/name
    data=json.loads(file.read_text());fn(data);file.write_text(json.dumps(data,ensure_ascii=False))


def codes(result):return {e['code'] for e in result['errors']}


def test_complete_format_checks_do_not_accept_business(package):
    before=hashlib.sha256(DATABASE_PATH.read_bytes()).hexdigest()
    for imported in (False,True):
        result=v.validate(package,DATABASE_PATH,imported)
        assert result['machine_status']=='PASS',result
        assert result['complete_path_counts']=={'system':1,'model':1,'partner':1}
        assert result['DATA_01_business_signoff']=='NOT RUN' and result['DATA_02']=='BLOCKED'
        assert result['real_model_calls']==0
        assert 'UNKNOWN_PRESERVED' in {w['code'] for w in result['warnings']}
    assert hashlib.sha256(DATABASE_PATH.read_bytes()).hexdigest()==before


@pytest.mark.parametrize('marker',['synthetic','fixture','example.com','验证伙伴','A-ready',v.CANARY])
def test_reject_test_markers_without_echoing(package,marker):
    change(package,None,lambda p:p.update(package_kind='synthetic') if marker=='synthetic' else p.update(allowed_diagnostic_scope=[marker]))
    result=v.validate(package,DATABASE_PATH)
    assert result['machine_status']=='FAIL' and 'TEST_DATA_FORBIDDEN' in codes(result)
    assert marker not in json.dumps(result,ensure_ascii=False)


def test_missing_lab_is_not_fabricated(package):
    change(package,None,lambda p:p.update(resources=['course.json']))
    result=v.validate(package,DATABASE_PATH)
    assert {'REAL_RESOURCE_PATH_INCOMPLETE','UNREGISTERED_RESOURCE_GAP'} <= codes(result)
    with get_db() as conn:assert conn.execute('SELECT COUNT(*) FROM enablement_resources').fetchone()[0]==2
    change(package,None,lambda p:p['resource_gaps']['items'].append({'capability_tag_id':p['request']['targets'][0]['capability_tag_id'],'source_type':'lab','detail':'当前资源库缺实验'}))
    result=v.validate(package,DATABASE_PATH)
    assert 'UNREGISTERED_RESOURCE_GAP' not in codes(result) and 'REAL_RESOURCE_PATH_INCOMPLETE' in codes(result)


@pytest.mark.parametrize('orphan',[False,True])
def test_invalid_or_orphan_case(package,orphan):
    if orphan:
        # Fault injection only in the disposable pytest database, reproducing legacy orphan rows.
        with sqlite3.connect(DATABASE_PATH) as conn:conn.execute("UPDATE cases SET partner_id='missing-parent' WHERE id='intake-case'")
    else:change(package,'case.json',lambda p:p.update(source_id='does-not-exist'))
    assert 'INVALID_OR_ORPHAN_CASE' in codes(v.validate(package,DATABASE_PATH))


@pytest.mark.parametrize('flag,purpose',[('model_allowed','model'),('partner_allowed','partner')])
def test_permissions_independent(package,flag,purpose):
    change(package,'course.json',lambda p:p['permissions'].update({flag:False}))
    result=v.validate(package,DATABASE_PATH)
    assert result['machine_status']=='PASS',result
    assert 0 in result['eligible_record_indexes']['system']
    assert 0 not in result['eligible_record_indexes'][purpose]
    assert 0 in result['eligible_record_indexes']['partner' if purpose=='model' else 'model']


@pytest.mark.parametrize('field',['system_visible','model_allowed','partner_allowed'])
def test_permissions_must_be_explicit_booleans(package,field):
    change(package,'course.json',lambda p:p['permissions'].pop(field))
    assert 'EXPLICIT_PRODUCT_FIELDS_REQUIRED' in codes(v.validate(package,DATABASE_PATH))


@pytest.mark.parametrize('mutation', ['invalid_tag','empty_url','no_review','bad_status','unknown_omitted','internal_model_text'])
def test_bad_metadata_and_reviews(package,mutation):
    def edit(p):
        if mutation=='invalid_tag':p['metadata']['capability_tag_ids']=['missing-tag']
        if mutation=='empty_url':p['metadata']['source_url']=''
        if mutation=='no_review':p['review']['content_checked']=False
        if mutation=='bad_status':p['status']='draft'
        if mutation=='unknown_omitted':p['metadata'].pop('cost')
        if mutation=='internal_model_text':p['metadata']['summary']='仅临时库内部标题'
    if mutation=='internal_model_text':
        with get_db() as conn:conn.execute("UPDATE cases SET description='仅临时库内部标题超过十二个汉字禁止发送' WHERE id='intake-case'")
        change(package,'course.json',lambda p:p['metadata'].update(summary='仅临时库内部标题超过十二个汉字禁止发送'))
    else:change(package,'course.json',edit)
    assert v.validate(package,DATABASE_PATH)['machine_status']=='FAIL'


def test_imported_snapshot_mismatch_and_revocation(package):
    change(package,'course.json',lambda p:p['metadata'].update(title='更改后的标题'))
    assert 'IMPORTED_SNAPSHOT_MISMATCH' in codes(v.validate(package,DATABASE_PATH,True))
    with get_db() as conn:conn.execute("UPDATE case_share_configs SET status='revoked',authorization_epoch=authorization_epoch+1 WHERE case_id='intake-case'")
    assert 'IMPORTED_REFERENCE_UNAVAILABLE' in codes(v.validate(package,DATABASE_PATH,True))


def test_canary_stays_internal_and_precheck_blocks(package):
    with get_db() as conn:assert conn.execute("SELECT description FROM cases WHERE id='intake-case'").fetchone()[0]==v.CANARY
    result=v.validate(package,DATABASE_PATH,True)
    assert result['machine_status']=='PASS' and result['model_projection_safe']
    gate=v.real_model_precheck(result,DATABASE_PATH)
    assert gate['status']=='BLOCKED' and not gate['checks']['explicit_user_authorization']
    assert not gate['checks']['explicit_approved_test_model'] and gate['real_model_calls']==0
    assert v.CANARY not in json.dumps([result,gate])


def test_readonly_connection_and_stable_path_rejected(package,tmp_path):
    with v.readonly_database(DATABASE_PATH) as conn:
        with pytest.raises(sqlite3.OperationalError):conn.execute('DELETE FROM partners')
    result=v.validate(package,v.STABLE/'data/app.db')
    assert 'STABLE_DATABASE_FORBIDDEN' in codes(result)
    link=tmp_path/'linked.db';link.symlink_to(DATABASE_PATH)
    assert 'SYMLINK_REJECTED' in codes(v.validate(package,link))


def test_path_escape_and_unknown_constraint(package):
    change(package,None,lambda p:p['request']['constraints'].update(account='企业账号'))
    result=v.validate(package,DATABASE_PATH)
    assert 'MODEL_CONSTRAINT_UNKNOWN' in {w['code'] for w in result['warnings']}
    change(package,None,lambda p:p.update(resources=['../escape.json']))
    assert 'PATH_OUTSIDE_PACKAGE' in codes(v.validate(package,DATABASE_PATH))


def test_distributed_templates_rejected():
    result=v.validate(v.ROOT/'pilot-data/pilot-manifest.template.json',DATABASE_PATH)
    assert result['machine_status']=='FAIL' and result['real_model_calls']==0


@pytest.mark.parametrize('flags',[(a,b,c) for a in (False,True) for b in (False,True) for c in (False,True)])
def test_all_permission_combinations(package,flags):
    change(package,'course.json',lambda p:p['permissions'].update(dict(zip(v.FLAGS,flags))))
    result=v.validate(package,DATABASE_PATH)
    for purpose,allowed in [('system',flags[0]),('model',flags[0] and flags[1]),('partner',flags[0] and flags[2])]:
        assert (0 in result['eligible_record_indexes'][purpose]) == allowed


def test_duplicate_keys_and_hardlinks_fail_closed(package,tmp_path):
    import os
    link=tmp_path/'hardlink.db';os.link(DATABASE_PATH,link)
    try:assert 'REGULAR_PRIVATE_FILE_REQUIRED' in codes(v.validate(package,link))
    finally:link.unlink()
    package.write_text('{"package_kind":"real","package_kind":"synthetic"}')
    assert 'DUPLICATE_JSON_KEY' in codes(v.validate(package,DATABASE_PATH))


def test_precheck_receipts_are_verified_without_model_call(package,tmp_path,monkeypatch):
    from datetime import datetime,timezone,timedelta
    result=v.validate(package,DATABASE_PATH,True)
    assert result['machine_status']=='PASS',result
    monkeypatch.setattr(v,'ROOT',tmp_path)
    monkeypatch.setattr(v.subprocess,'check_output',lambda *a,**k:'')
    private=tmp_path/'.isolation';private.mkdir()
    now=datetime.now(timezone.utc)
    with get_db() as conn:
        config=dict(conn.execute('SELECT id,model_name,base_url FROM model_configs LIMIT 1').fetchone())
        conn.execute('UPDATE model_configs SET enabled=1 WHERE id=?',(config['id'],))
        conn.execute("UPDATE model_usage_configs SET model_config_id=? WHERE scene_key='partner_development'",(config['id'],))
    signed={'approved':True,'signed_by':'仅用于临时测试的签审人','signed_at':now.isoformat(),'package_sha256':result['package_sha256']}
    user={**signed,'scope':'real_model_test','model':config['model_name'],'provider_base_url':config['base_url'],'max_calls':4}
    business={**signed,'scope':'data_for_model_test','model_projection_sha256':result['model_projection_sha256']}
    runner=b'# inert unit-test evidence, never used to execute a model'
    # Receipt tests check integrity logic only, not an implemented real-call audit runner.
    audit={'status':'PASS','real_model_calls':0,'runner_sha256':v.digest(runner),'budget_exhaustion_blocks':True,
        'failed_calls_counted':True,'canary_blocked':True,'audit_fields_complete':True}
    receipt={'package_sha256':result['package_sha256'],'expires_at':(now+timedelta(hours=1)).isoformat(),
        'approved_test_config_id':config['id'],'model':config['model_name'],'provider_base_url':config['base_url'],
        'max_calls':4,'attachments_allowed':False}
    for key,data in [('user_authorization',user),('business_signoff',business),('budget_audit_mock_test',audit),('audit_runner',runner)]:
        body=data if isinstance(data,bytes) else json.dumps(data).encode()
        file=private/key;file.write_bytes(body);receipt[key]={'path':file.name,'sha256':v.digest(body)}
    file=private/'receipt.json';file.write_text(json.dumps(receipt))
    assert v.real_model_precheck(result,DATABASE_PATH,file)['status']=='PASS'
    user['approved']=False
    body=json.dumps(user).encode();(private/'user_authorization').write_bytes(body)
    receipt['user_authorization']['sha256']=v.digest(body);file.write_text(json.dumps(receipt))
    gate=v.real_model_precheck(result,DATABASE_PATH,file)
    assert gate['status']=='BLOCKED' and not gate['checks']['explicit_user_authorization']
    assert gate['real_model_calls']==0
    (private/'business_signoff').write_text('{}')
    assert v.real_model_precheck(result,DATABASE_PATH,file)['status']=='BLOCKED'


def test_internal_case_text_rejected_even_when_model_permission_denied(package):
    with get_db() as conn:conn.execute("UPDATE cases SET description='这是一段仅限内部查看的案例原始材料' WHERE id='intake-case'")
    change(package,'case.json',lambda p:(p['metadata'].update(summary='这是一段仅限内部查看的案例原始材料'),p['permissions'].update(model_allowed=False)))
    assert 'INTERNAL_CONTENT_IN_RESOURCE_METADATA' in codes(v.validate(package,DATABASE_PATH))
