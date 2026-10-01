"""Ten-chapter profile regression on disposable storage; no business data/model calls."""
import json
from pathlib import Path
import pytest
from backend.app import profile_report as report,material_files,doc_extractor
from backend.app.database import get_db
from backend.app.routers import profile
from .conftest import auth_headers,make_partner,make_user
from .support.profile_report_fixture import document,patch_all


@pytest.fixture
def setup(client,monkeypatch,tmp_path):
    from backend.app import partner_match_context
    admin=make_user('report-admin',role='admin');reader=make_user('report-reader');partner=make_partner()
    summaries=[]
    def summary(pid):
        with get_db() as conn:summaries.append(conn.execute('SELECT ai_profile FROM partners WHERE id=?',(pid,)).fetchone()[0])
        return True
    monkeypatch.setattr(partner_match_context,'generate_summary',summary)
    monkeypatch.setattr(profile,'chat_completion',lambda *a,**k:'{}')
    def preview(path):
        target=tmp_path/(path.stem+'.pdf');target.write_bytes(b'%PDF-synthetic');return str(target)
    monkeypatch.setattr(material_files,'office_preview',preview)
    def no_call(*a,**k):raise AssertionError('Unexpected model request')
    monkeypatch.setattr(profile.development_model,'completion',no_call)
    return client,auth_headers(admin),auth_headers(reader),partner['id'],summaries


def row(pid):
    with get_db() as conn:return dict(conn.execute('SELECT * FROM partners WHERE id=?',(pid,)).fetchone())


def upload(setup,data,initialize=True):
    client,admin,_,pid,_=setup
    response=client.post(f'/partners/{pid}/documents',headers=admin,files={'file':('report.docx',data)},data={'initialize_profile':str(initialize).lower()})
    assert response.status_code==201,response.text
    with get_db() as conn:return dict(conn.execute('SELECT * FROM partner_documents WHERE id=?',(response.json()['id'],)).fetchone())


@pytest.mark.parametrize('empty_cases',[False,True])
def test_import_all_chapters_tables_toc_and_admin_only(setup,empty_cases):
    data=document(toc=True,empty_cases=empty_cases);file=upload(setup,data);client,admin,user,pid,summaries=setup
    assert file['processing_status']=='ready',file['processing_error']
    saved=row(pid)['ai_profile'];parsed=report.parse(saved)
    assert len(parsed.chapters)==10 and saved.count('## 1. 公司概况')==1 and '目录' not in saved
    assert saved.count('| 字段 | 事实 |')==3 and '本公司 \\| 未核验<br>现有资料未提供' in saved
    assert '来源日期：2026-09-24；集团口径，企业自述，待核实' in saved
    assert Path(file['file_path']).read_bytes()==data
    assert file['extracted_text']==doc_extractor.extract_text(file['file_path'],'docx')
    assert summaries==[saved]
    assert client.get(f'/partners/{pid}',headers=user).json()['ai_profile'] is None
    assert client.get(f'/partners/{pid}/documents/{file["id"]}/file',headers=user).status_code==403
    assert client.get(f'/partners/{pid}/documents/{file["id"]}/file',headers=admin).content==data


def test_new_case_updates_only_case_chapter(setup,monkeypatch):
    upload(setup,document());client,admin,_,pid,summaries=setup;old=row(pid)['ai_profile'];old_parts=report.parse(old)
    response=client.post('/cases',headers=admin,json={'partner_id':pid,'title':'新制造案例','description':'本公司2026年9月实施，企业自述未外部核验','category_id':'technical-1'})
    assert response.status_code==201
    assert row(pid)['ai_profile']==old and row(pid)['materials_revision']!=row(pid)['profile_materials_revision']
    assert len(summaries)==1
    def complete(config,messages,schema):
        data=json.loads(messages[-1]['content']);assert data['current_report']==old and '新制造案例' in data['materials']
        return json.dumps({'sections':[{'chapter':6,'content':'| 时间 | 项目 | 口径 |\n| --- | --- | --- |\n| 2026年9月 | 新制造案例 | 本公司；企业自述，待核实 |'}]},ensure_ascii=False)
    monkeypatch.setattr(profile.development_model,'completion',complete)
    response=client.post(f'/partners/{pid}/profile',headers=admin);assert response.status_code==200,response.text
    after=report.parse(row(pid)['ai_profile'])
    assert all(after.chapters[i]==old_parts.chapters[i] for i in range(10) if i!=5)
    assert after.prefix==old_parts.prefix and '新制造案例' in after.chapters[5]
    assert row(pid)['materials_revision']==row(pid)['profile_materials_revision'] and len(summaries)==2


def test_no_profile_generates_all_ten_chapters(setup,monkeypatch):
    client,admin,_,pid,summaries=setup
    def complete(c,m,s):
        data=json.loads(m[-1]['content']);assert data['mode']=='create' and len(report.parse(data['current_report']).chapters)==10
        return patch_all()
    monkeypatch.setattr(profile.development_model,'completion',complete)
    response=client.post(f'/partners/{pid}/profile',headers=admin);assert response.status_code==200,response.text
    assert len(report.parse(row(pid)['ai_profile']).chapters)==10 and len(summaries)==1


def test_summary_is_restored_from_original_only_on_manual_update(setup,monkeypatch):
    upload(setup,document());client,admin,_,pid,_=setup;full=row(pid)['ai_profile']
    with get_db() as conn:conn.execute('UPDATE partners SET ai_profile=? WHERE id=?',('旧的能力摘要',pid))
    assert row(pid)['ai_profile']=='旧的能力摘要'
    def complete(c,m,s):assert json.loads(m[-1]['content'])['current_report']==full;return '{"sections":[]}'
    monkeypatch.setattr(profile.development_model,'completion',complete)
    assert client.post(f'/partners/{pid}/profile',headers=admin).status_code==200
    assert row(pid)['ai_profile']==full


@pytest.mark.parametrize('fault',['malformed','duplicate','missing_table','wrong_id','timeout','concurrent'])
def test_invalid_or_failed_update_preserves_complete_profile(setup,monkeypatch,fault):
    upload(setup,document());client,admin,_,pid,summaries=setup;before=row(pid)
    def complete(c,m,s):
        if fault=='timeout':raise TimeoutError('synthetic timeout')
        if fault=='concurrent':
            with get_db() as conn:conn.execute('UPDATE partners SET materials_revision=materials_revision+1 WHERE id=?',(pid,))
            return '{"sections":[]}'
        return {'malformed':'not json','duplicate':'{"sections":[{"chapter":8,"content":"a"},{"chapter":8,"content":"b"}]}','missing_table':'{"sections":[{"chapter":6,"content":"摘要替代了案例表"}]}','wrong_id':'{"sections":[{"chapter":11,"content":"bad"}]}'}[fault]
    monkeypatch.setattr(profile.development_model,'completion',complete)
    response=client.post(f'/partners/{pid}/profile',headers=admin)
    assert response.status_code==(409 if fault=='concurrent' else 502),response.text
    after=row(pid);assert after['ai_profile']==before['ai_profile'] and after['profile_updated_at']==before['profile_updated_at'] and len(summaries)==1


def test_unrecognized_word_and_unrecoverable_summary_preserve_old(setup):
    upload(setup,document());client,admin,_,pid,summaries=setup;old=row(pid)['ai_profile']
    failed=upload(setup,document(invalid=True))
    assert failed['processing_status']=='failed' and failed['extracted_text'] and Path(failed['file_path']).exists()
    assert row(pid)['ai_profile']==old and len(summaries)==1
    with pytest.raises(report.ReportError):report.baseline('旧纯文本摘要',[])


def test_budget_includes_current_report_and_all_materials(setup,monkeypatch):
    upload(setup,document(extra='完整底稿'*300));client,admin,_,pid,summaries=setup;before=row(pid)
    monkeypatch.setenv('BANFEI_PROFILE_INPUT_MAX_CHARS','1000')
    response=client.post(f'/partners/{pid}/profile',headers=admin)
    assert response.status_code==422 and '输入上限' in response.json()['detail']
    assert row(pid)==before and len(summaries)==1
