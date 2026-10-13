"""Approved review changes: offline model mocks and isolated PostgreSQL only."""
import copy,json
import pytest
from backend.app import partner_match_context as ctx,profile_sources as sources
from backend.app import development_context,development_engine as engine,development_lifecycle as life,development_views as views,development_model as model,enablement
from backend.app.database import get_db
from backend.app.development_types import Submit,Conversation,DevelopmentRequest
from backend.tests.test_development_lifecycle import prepared
from backend.tests.test_enablement import grant,published
from backend.tests.test_profile_report import setup,upload
from backend.tests.test_matching_v3 import raw_row,assemble
from backend.tests.conftest import auth_headers


def test_number_space_native_sections_keep_business_qualifiers_without_archive_review():
    text=('资料存档\n原始URL：https://example.invalid/article\n证据边界：采集者未核实交付，不作为证明。\n导航\n'
          '项目标题\n2026 / 01 / 01\n集团自述，项目仍在规划；2026年提供内部演示。\n'
          '01 AI互动问答\n平台提供问答服务。\n02 会员与系统\n会员功能尚未对外交付。\n')
    ranges=ctx._intro_ranges(text);intro=''.join(text[a:b] for a,b in ranges)
    assert '项目标题' in intro and '2026 / 01 / 01' in intro and '集团自述' in intro and '规划' in intro
    assert '01 AI互动' not in intro and '证据边界' not in intro and '采集者' not in intro
    start=text.index('会员功能');native=ctx._group_ranges(text,start,start+4)
    assert any('会员功能尚未对外交付。' in text[a:b] for a,b in native)
    assert any(a==text.index('02 会员与系统') for a,b in ctx._native_blocks(text))


def test_ancillary_material_cannot_take_budget_before_business_body():
    row=raw_row({'id':'mixed','name':'合成主体'},['目录导航\n'+'x'*18000,'会员和系统实践。'+'正文事实。'*700])
    row[1]['_groups'][0]['ancillary']=True
    _,chars,_=assemble([row]);assert chars<=25000
    assert any('会员和系统实践' in p['text'] for p in row[1]['profilePassages'])
    assert any(entry['reason']=='selection_budget' and entry['hitIndexes']==[0] for entry in row[1]['inputCoverage']['omissions'])


def test_existing_candidate_rotation_gives_another_source_body_its_first_turn():
    texts=['长文事实'+str(i)+'。'+'甲'*4500 for i in range(4)]+['会员与系统项目事实。'+'乙'*1200]
    row=raw_row({'id':'mixed-sources','name':'多来源主体'},texts)
    offset=0
    for passage in row[1]['profilePassages'][:4]:
        entry=row[1]['_sourceMap'][passage['source']]
        entry.update(sourceRef='document:one-long-document',start=offset,end=offset+len(entry['text']))
        offset=entry['end']
    peer=raw_row({'id':'peer','name':'另一主体'},['另一个伙伴的完整主要事实。'+'丙'*6000])
    _,characters,_=assemble([row,peer]);assert characters<=25000
    assert any('会员与系统项目事实' in p['text'] for p in row[1]['profilePassages'])
    assert peer[1]['profilePassages'] and any('长文事实0' in p['text'] for p in row[1]['profilePassages'])


@pytest.mark.parametrize('date',['2026 / 06 / 04','2026-06-04','2026年06⽉04⽇ 18:03'])
def test_archive_native_date_forms_keep_article_subject_and_exclude_collection(date):
    text='存档原文\n原始URL：https://example.invalid/article\n证据边界：采集操作。\n导航\n实际项目标题\n'+date+'\n集团自述，未来计划开展内部实践。'
    a,b,extra=ctx._source_layout(text)
    assert text[a:b]=='实际项目标题\n'+date+'\n集团自述，未来计划开展内部实践。' and extra==[]


@pytest.mark.parametrize('bad,reason',[
    ({'chapter':5,'title':'标题不能补摘要','block_ids':['B1']},'缺少summary'),
    ({'chapter':5,'summary':'事实','block_ids':[]},'block_ids无效'),
    ({'chapter':5,'summary':'事实','block_ids':['unseen']},'block_ids未知'),
])
def test_source_diagnostic_reports_actual_failed_field_without_filling(bad,reason):
    source={'kind':'document','id':'synthetic','text':'原始业务事实。'};_,mapping=sources.source_blocks(source)
    with pytest.raises(ValueError,match=reason):sources.numbered_sections(source,json.dumps({'sections':[bad]}),mapping)


def test_source_partial_failure_persists_summary_diagnostic_and_exact_quotes(setup,monkeypatch):
    calls=[]
    def complete(config,messages,schema):
        blocks=json.loads(messages[-1]['content'])['blocks'];calls.append(blocks)
        return json.dumps({'sections':[{'chapter':5,'summary':'实际产品事实','block_ids':[blocks[0]['id']]},
                                       {'chapter':6,'title':'不可补成功','block_ids':[blocks[0]['id']]}]})
    monkeypatch.setattr(model,'completion',complete)
    original='企业自述提供产品；目前仍为内部演示。'
    fid=upload(setup,'partial-summary.txt',original)
    with get_db() as conn:row=dict(conn.execute('SELECT state,error,sections_json FROM partner_profile_sources WHERE source_id=?',(fid,)).fetchone())
    assert row['state']=='ready' and '来源章节缺少summary' in row['error'] and len(calls)==1
    accepted=json.loads(row['sections_json']);assert [s['chapter'] for s in accepted]==[5]
    assert accepted[0]['quotes']==[original]


@pytest.fixture
def twelve_mixed(prepared,monkeypatch):
    user,_,admin,_=prepared
    kinds=['course','lab','course','lab','lab','course','lab']+['course']*5
    for i,kind in enumerate(kinds+['lab'],1):
        row=enablement.save('resource','mixed-'+str(i),enablement.ResourceSave(base_revision=0,metadata=enablement.ResourceMetadata(
            resource_type=kind,title='Agent实践'+str(i),summary='数据库与AI Agent开发实践',level='advanced',
            source_url='https://example.com/resource/'+str(i),**({'duration_minutes':90} if kind=='lab' else {}))),admin['id'])
        published(grant(row,admin),admin)
    captures=[]
    def complete(config,messages,schema):
        data=json.loads(messages[-1]['content']);captures.append((schema['title'],copy.deepcopy(data)))
        from backend.tests.support.development_mock import response
        if schema['title']=='Understanding':
            result=response(messages)
            if data.get('current'):
                target=next(item for item in data['current']['resources'] if item['source_type']=='lab' and item['type_position']==2)
                result.update(used_refs=[],used_profile_chapters=[])
                if '解释' in data['message']:result.update(action='answer',answer='第二个实验是Agent实践4。',edit_item_ids=[],edit_answer_spans=[])
                else:result.update(action='patch',answer='',edit_item_ids=[target['item_id']],edit_answer_spans=['使用第二个实验验证Agent部署。'])
            return json.dumps(result)
        if schema['title']=='AdvicePatch':
            return json.dumps({'target_partner_id':'partner-1','changes':[{'action':'replace','item_id':data['understanding']['edit_item_ids'][0],
                'items':[{'source_type':'lab','source_id':'mixed-13','source_version':1,'reason':'更进阶的部署实践'}]}],
                'answer_changes':[{'before':'使用第二个实验验证Agent部署。','after':'使用进阶实验验证Agent部署。'}],
                'answer':'已更新第二个实验。','used_refs':[],'used_profile_chapters':[]})
        return json.dumps({'target_partner_id':'partner-1','answer':'第一段保持。\n使用第二个实验验证Agent部署。\n末段保持。',
            'used_refs':[],'used_profile_chapters':[],'stages':[{'title':'混排实践','items':[
                {'source_type':kind,'source_id':'mixed-'+str(i),'source_version':1,'reason':'当前方向实践'} for i,kind in enumerate(kinds,1)]}]})
    monkeypatch.setattr(model,'completion',complete)
    return prepared,captures


def test_twelve_mixed_type_order_and_one_to_one_patch_keep_item_ids_and_dependencies(twelve_mixed):
    prepared,captures=twelve_mixed;user=prepared[0]
    req=DevelopmentRequest(target_partner_id='partner-1',development_direction='数据库与AI Agent开发实践',model_input_allowed=True,partner_goal_allowed=True)
    accepted=life.create(Submit(submission_id='mixed-twelve-create',request=req),user);engine.execute(accepted['run_id'])
    before=views.detail(accepted['plan_id'],user);base=before['plan']['current_version_id'];old=before['payload']
    assert len(old['stages'][0]['items'])==12
    run=views.converse(accepted['plan_id'],Conversation(submission_id='mixed-twelve-explain',based_on_version_id=base,message='解释第二个实验'),user);engine.execute(run['run_id'])
    explained=views.detail(accepted['plan_id'],user);assert explained['plan']['current_version_id']==base and len(explained['versions'])==1
    frame=captures[-1][1]['current']['resources']
    assert [r['position'] for r in frame]==list(range(1,13))
    assert [r['type_position'] for r in frame]==[1,1,2,2,3,3,4,4,5,6,7,8]
    assert frame[3]['source_id']=='mixed-4' and frame[3]['item_id']==old['stages'][0]['items'][3]['item_id']
    run=views.converse(accepted['plan_id'],Conversation(submission_id='mixed-twelve-patch',based_on_version_id=base,message='第二个实验换一个更进阶的'),user);engine.execute(run['run_id'])
    after=views.detail(accepted['plan_id'],user);new=after['payload']['stages'][0]['items']
    assert len(new)==12 and len(after['versions'])==2
    for i,item in enumerate(old['stages'][0]['items']):
        assert new[i]['item_id']==item['item_id']
        if i!=3:assert new[i]==item
    assert new[3]['source_id']=='mixed-13'
    assert after['payload']['answer']=='第一段保持。\n使用进阶实验验证Agent部署。\n末段保持。'
    with get_db() as conn:
        old_deps=json.loads(conn.execute('SELECT dependency_json FROM development_versions WHERE id=?',(base,)).fetchone()[0])
        new_deps=json.loads(conn.execute('SELECT dependency_json FROM development_versions WHERE id=?',(after['plan']['current_version_id'],)).fetchone()[0])
    for ref in old_deps:
        if ref['source_id']!='mixed-4':assert ref in new_deps
    assert any(ref['source_id']=='mixed-13' for ref in new_deps)


@pytest.mark.parametrize('hours',[None,1.0])
def test_original_transfer_preview_copy_uses_item_hours_without_catalog_inference(twelve_mixed,client,monkeypatch,hours):
    prepared,_=twelve_mixed;user=prepared[0]
    original=model.completion
    def complete(config,messages,schema):
        result=json.loads(original(config,messages,schema))
        if schema['title']=='AdviceOutput':result['stages'][0]['items'][0]['estimated_hours']=hours
        return json.dumps(result)
    monkeypatch.setattr(model,'completion',complete)
    req=DevelopmentRequest(target_partner_id='partner-1',development_direction='数据库与AI Agent开发实践',model_input_allowed=True,partner_goal_allowed=True)
    accepted=life.create(Submit(submission_id='hours-original-exit',request=req),user);engine.execute(accepted['run_id'])
    pid=accepted['plan_id'];detail=views.detail(pid,user);version=detail['plan']['current_version_id']
    assert detail['payload']['stages'][0]['items'][0]['estimated_hours']==hours
    headers=auth_headers(user)
    preview=client.get(f'/development/plans/{pid}/transferable',headers=headers)
    copied=client.post(f'/development/plans/{pid}/copy',headers=headers,json={'version_id':version})
    assert preview.status_code==copied.status_code==200 and preview.json()==copied.json()
    text=preview.json()['text']
    assert ('预计投入（小时）：1.0' in text)==(hours is not None)
    assert text.count('预计投入（小时）')==(0 if hours is None else 1)
