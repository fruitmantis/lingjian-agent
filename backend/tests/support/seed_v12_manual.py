"""Explicit synthetic manual-review fixtures. Never imported at application startup."""
import os,json,sys,sqlite3
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[3]
DEV=ROOT/'.isolation/runtime/dev'


def main():
    db=DEV/'app.db'
    if ROOT.name!='lingjian-agent-enablement' or db.is_symlink() or db.stat().st_nlink!=1 or db.resolve()!=db:
        raise SystemExit('Only the isolated manual development database is allowed')
    env=json.loads((DEV/'environment.json').read_text())
    if Path(env['LINGJIAN_DATABASE_PATH'])!=db:raise SystemExit('Development DB mismatch')
    os.environ.update(env);sys.path.insert(0,str(ROOT))
    from backend.app.database import get_db
    from backend.app import enablement as service
    stamp=datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        admin=conn.execute("SELECT id FROM users WHERE username='dev_admin' AND role='admin' AND status='active'").fetchone()[0]
        tags={r['name']:r['id'] for r in conn.execute('SELECT id,name FROM capability_tags WHERE enabled=1')}
        assert '数据库' in tags and '盘古大模型' in tags
        for suffix,name,caps,industry,profile in [
            ('a','测试伙伴 A（合成：数据交付基础）','数据库,上云规划实施','制造','具备数据库交付、云基础和制造行业系统集成经验，可将数据工程经验迁移到新应用场景。'),
            ('b','测试伙伴 B（合成：Web 应用基础）','应用开发','零售','具备 Web 前端开发与零售应用实施经验。当前画像主要涉及业务应用开发，需要结合目标选择集成实践。')]:
            id='v12-partner-'+suffix
            conn.execute("INSERT OR IGNORE INTO partners(id,name,intro,capabilities,service_areas,industries,ai_profile,status,created_at,updated_at) VALUES (?,?,?,?,?,?,?,'active',?,?)",(id,name,'V1.2 合成开发数据，仅用于人工体验。',caps,'全国',industry,profile,stamp,stamp))
        for id,title in [('v12-case-db','数据库迁移项目实践'),('v12-case-agent','Agent 集成项目实践')]:
            conn.execute('INSERT OR IGNORE INTO cases(id,partner_id,title,description,created_at) VALUES (?,?,?,?,?)',(id,'v12-partner-a',title+'（合成内部案例）','合成内部记录，不直接作为共享学习正文。',stamp))
    entries=[('course','v12-course-db','数据库迁移进阶与风险校验','数据库','数据库迁移','advanced'),
             ('lab','v12-lab-db-check','数据库迁移校验进阶实验','数据库','数据库迁移验证','advanced'),
             ('lab','v12-lab-db-rollback','数据库回退与恢复进阶实验','数据库','数据库迁移回退','advanced'),
             ('course','v12-course-rag','RAG 知识库工程课程','盘古大模型','RAG 知识库 检索评估','advanced'),
             ('course','v12-course-integration','Agent 应用集成与 POC 课程','盘古大模型','Agent 系统集成 POC','advanced'),
             ('course','v12-course-foundation','应用集成与云服务基础','上云规划实施','API 云服务 集成','beginner'),
             ('lab','v12-lab-agent','Agent 工具调用与系统集成实验','盘古大模型','Agent 系统集成 POC','advanced'),
             ('lab','v12-lab-agent-eval','Agent 接口可靠性进阶实验','盘古大模型','Agent 系统集成 评估','advanced'),
             ('case','v12-case-db','数据库迁移共享实践','数据库','数据库迁移验证','advanced'),
             ('case','v12-case-agent','Agent 集成共享实践','盘古大模型','Agent 系统集成 POC','advanced')]
    created=0
    for kind,id,title,tag,focus,level in entries:
        domain='case' if kind=='case' else 'resource'
        with get_db() as conn:
            table='case_share_configs' if kind=='case' else 'enablement_resources';column='case_id' if kind=='case' else 'id'
            if conn.execute(f'SELECT 1 FROM {table} WHERE {column}=?',(id,)).fetchone():continue
        meta={'title':title+'（合成开发测试）','summary':focus+'；仅用于 V1.2 开发体验，不是真实业务资源。','source_platform':'本地开发示例目录','source_url':'https://example.com/','capability_tag_ids':[tags[tag]]}
        if kind=='case':meta.update(methods=focus+' 的模拟方法：准备、验证、复盘。',contributor_role='合成实施角色')
        else:meta.update(resource_type=kind,target_capability=focus,product_direction=focus,audience='交付工程师',difficulty=level,language='中文',site='开发示例',duration_minutes=90,prerequisites='了解对应技术基础',cost='unknown' if 'rag' in id else 'free',account_requirement='需要开发测试账号',environment_requirement='由使用者准备独立实验环境')
        save=service.ShareSave if kind=='case' else service.ResourceSave
        row=service.save(domain,id,save(base_revision=0,metadata=meta),admin)
        row=service.permissions(domain,id,service.Permissions(base_revision=row['revision'],system_visible=True,model_allowed=True,partner_allowed=True,reason='合成开发材料仅用于 local mock 和人工演示'),admin)
        row=service.review(domain,id,service.Review(base_revision=row['revision'],link_status='available',content_checked=True,authorization_checked=True,note='合成演示核验，不代表真实业务人工签审'),admin)
        service.publish(domain,id,service.Revision(base_revision=row['revision']),admin);created+=1
    with get_db() as conn:
        assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    print('Synthetic manual-review partners A/B ready; new resources:',created,'; intentional gap: no RAG-specific lab')

if __name__=='__main__':main()
