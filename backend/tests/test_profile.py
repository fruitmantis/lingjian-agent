"""Profile updates do not mutate administrator-maintained tags."""
import pytest
from backend.app.database import get_db
from .test_profile_report import setup,upload,profile

@pytest.mark.parametrize('empty_dictionary',[False,True])
def test_source_processing_preserves_formal_tags(setup,empty_dictionary):
    pid=setup[3]
    with get_db() as conn:
        if empty_dictionary:conn.execute('UPDATE capability_tags SET enabled=0')
        before=dict(conn.execute('SELECT capabilities,service_areas,industries FROM partners WHERE id=?',(pid,)).fetchone())
    upload(setup,'tag-source.txt','数据库相关能力，服务江苏制造客户。')
    with get_db() as conn:
        assert dict(conn.execute('SELECT capabilities,service_areas,industries FROM partners WHERE id=?',(pid,)).fetchone())==before
