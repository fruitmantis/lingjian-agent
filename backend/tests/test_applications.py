"""Removed registration/approval routes must not remain as alternate login paths."""
import pytest
from .conftest import auth_headers, make_user
from backend.app.database import get_db

@pytest.mark.parametrize('method,path',[
    ('post','/auth/login'),('post','/auth/user-applications'),('get','/admin/user-applications'),
    ('post','/admin/user-applications/example/approve'),('post','/admin/user-applications/example/reject'),
])
def test_registration_and_approval_retired(client,method,path):
    admin=make_user('retired_admin',role='admin')
    assert getattr(client,method)(path,headers=auth_headers(admin)).status_code==404
    with get_db() as conn:assert conn.execute('SELECT count(*) FROM user_applications').fetchone()[0]==0
