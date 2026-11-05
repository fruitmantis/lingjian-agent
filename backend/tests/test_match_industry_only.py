"""Industry-only recall, original evidence and unchanged mixed work; isolated PG."""
import json
from datetime import datetime, timezone
from uuid import uuid4
import pytest
from backend.app import partner_match_context as context, profile_sources
from backend.app.business_taxonomy import INDUSTRIES
from backend.app.database import get_db
from backend.business import matching
from .test_match_certification_priority import partner, condition


def entry(pid, industry='', body=None, tags='', identities=(), status='active'):
    partner(pid, tags, identities)
    with get_db() as conn:
        conn.execute('UPDATE partners SET industries=?,status=? WHERE id=?', (industry, status, pid))
        if body is not None:
            cid='case-'+uuid4().hex;stamp=datetime.now(timezone.utc).isoformat()
            conn.execute('INSERT INTO cases(id,partner_id,title,description,visible,created_at,updated_at) VALUES (?,?,?,?,1,?,?)',
                         (cid,pid,'合成案例资料',body,stamp,stamp))
            source=next(s for s in profile_sources.sources(conn,pid) if s['kind']=='case' and s['id']==cid)
            conn.execute("INSERT INTO partner_profile_sources(partner_id,source_kind,source_id,source_fingerprint,state,sections_json,updated_at) VALUES (?,'case',?,?,'ready',?,?)",
                         (pid,cid,profile_sources.stamp(source),json.dumps([{'chapter':6,'summary':body,'quotes':[body]}],ensure_ascii=False),stamp))


def facts(requirement, industry, work=(), conditions=(), tags=()):
    body={'industry':industry,'workEvidence':list(work),'partnerRequirements':list(conditions),
          'capabilityTags':list(tags),'capabilityEvidence':{tag:'数据库迁移' for tag in tags}}
    return matching.parse_understanding(json.dumps({'in_scope':True,'facts':body},ensure_ascii=False),requirement,['数据库','容器'])[0]['facts']


@pytest.mark.parametrize('industry', INDUSTRIES)
def test_all_standard_industries_union_standard_field_and_current_source_once(industry):
    entry('field-only',industry)
    entry('text-only','',f'【合成资料】已为{industry}客户完成信息系统上线。')
    entry('both',industry,f'【合成资料】{industry}项目已经完成上线。')
    entry('disabled',industry,status='disabled')
    entry('unrelated')
    requirement=f'帮我找在{industry}行业有相关经验的伙伴'
    understood=facts(requirement,industry);info={}
    assert matching.recall_query(requirement,understood)[0]==[]
    with get_db() as conn:
        selected=context.recall_candidates(conn,requirement,understood,diagnostics=info)
        field=next(item for item in selected if item['partnerId']=='field-only')
        row=context.detailed_candidate(conn,'field-only','行业适配',requirement,facts=understood,hits=field['hits'])
    assert {item['partnerId'] for item in selected}=={'field-only','text-only','both'}
    assert len(selected)==3 and info['keyword_count']==1
    assert row[1]['industries']==industry and row[1]['profilePassages']==[]
    assert all(item['certification']['relatedCapabilityTags']==[] for item in selected)


@pytest.mark.parametrize('requirement',['帮我找在汽车行业有相关经验的伙伴','汽车'])
def test_automotive_field_with_only_vehicle_text_is_not_lost_and_not_semantically_expanded(requirement):
    entry('field-vehicle','汽车','【合成资料】从事车载设备软件适配，未提供已交付项目记录。')
    entry('field-only','汽车')
    entry('both','汽车','【合成资料】已完成汽车制造企业数据平台上线。')
    entry('source-only','','【合成资料】已为汽车零部件厂完成应用上线。')
    entry('negative-source','','【合成资料】未开展汽车业务，当前仅维护银行办公系统。')
    entry('implicit-only','','【合成资料】提供车载设备软件适配。')
    understood=facts(requirement,'汽车')
    with get_db() as conn:
        selected=context.recall_candidates(conn,requirement,understood)
        negative=next(p for p in selected if p['partnerId']=='negative-source')
        row=context.detailed_candidate(conn,'negative-source','核对实际事实',requirement,facts=understood,hits=negative['hits'])
    assert {p['partnerId'] for p in selected}=={'field-vehicle','field-only','both','source-only','negative-source'}
    assert any('未开展汽车业务' in p['text'] for p in row[1]['profilePassages'])
    # This is a coarse candidate hit, not a claim of project experience. Vehicle-only text without a field is not an automotive synonym.


def test_standard_aliases_are_field_matches_but_pending_values_and_regions_are_not():
    entry('alias','银行')
    entry('pending','金融行业')
    entry('region-only')
    with get_db() as conn:
        conn.execute("UPDATE partners SET service_areas='金融' WHERE id='region-only'")
        selected=context.recall_candidates(conn,'找金融行业伙伴',facts('找金融行业伙伴','金融'))
    assert [p['partnerId'] for p in selected]==['alias']


@pytest.mark.parametrize('work,expected',[
    ('数据库迁移',{'cert-db','work-source'}),
    ('汽车行业数据库迁移',{'cert-db','work-source','car-text-only'}),
])
def test_mixed_work_does_not_get_industry_field_candidates(work,expected):
    entry('field-only','汽车',identities=['服务合作伙伴'])
    entry('cert-db','金融',tags='数据库')
    entry('work-source','','【合成资料】提供数据库迁移服务。')
    entry('car-text-only','','【合成资料】从事汽车行业营销服务。')
    requirement='需要汽车行业数据库迁移服务伙伴'
    understood=facts(requirement,'汽车',[work],tags=['数据库'])
    with get_db() as conn:selected=context.recall_candidates(conn,requirement,understood)
    assert {p['partnerId'] for p in selected}==expected
    assert selected[0]['partnerId']=='cert-db'


@pytest.mark.parametrize('industry',['未知','待确认行业',''])
def test_no_standard_industry_does_not_fill_the_pool(industry):
    entry('active','汽车',tags='数据库')
    requirement='帮我找相关伙伴'
    with get_db() as conn:selected=context.recall_candidates(conn,requirement,facts(requirement,industry))
    assert selected==[]


def test_required_certificate_filters_industry_hits_and_priority_still_limits_to_twelve():
    requirement='找金融行业伙伴，必须具备数据库认证'
    understood=facts(requirement,'金融',conditions=[condition(tags=['数据库'],quote='必须具备数据库认证')])
    entry('field-only','金融')
    for i in range(15):entry(f'cert-{i:02}','金融',tags='数据库')
    with get_db() as conn:selected=context.recall_candidates(conn,requirement,understood,limit=100)
    assert [p['partnerId'] for p in selected]==[f'cert-{i:02}' for i in range(12)]
    assert all(p['certification']['relatedCapabilityTags']==['数据库'] for p in selected)
