from backend.app.main import app


PUBLIC_OPERATIONS = {
    ("get", "/health"),
    ("post", "/auth/admin/login"),
    ("post", "/auth/identity/session"),
    ("post", "/auth/identity/key/login"),
    ("post", "/auth/identity/logout"),
}


def test_openapi_public_operations_are_only_identity_and_health():
    schema = app.openapi()
    operations = []
    public = set()
    for path, path_item in schema["paths"].items():
        for method, operation in path_item.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            operations.append((method, path))
            if not operation.get("security"):
                public.add((method, path))
    assert schema['paths']['/partners/{partner_id}']['delete']['security']
    assert public == PUBLIC_OPERATIONS


def test_openapi_admin_operations_all_declare_security():
    schema = app.openapi()
    admin_operations = [
        operation
        for path, path_item in schema["paths"].items() if path.startswith("/admin")
        for method, operation in path_item.items() if method in {"get", "post", "put", "patch", "delete"}
    ]
    assert len(admin_operations) >= 30
    assert all(operation.get("security") for operation in admin_operations)


def test_enablement_workspace_operations_remain_authenticated():
    schema = app.openapi()
    operations = [(method,path,operation) for path,item in schema['paths'].items()
                  if path.startswith('/enablement/') for method,operation in item.items()
                  if method in {'get','post','put','patch','delete'}]
    assert len(operations) == 5
    assert all(operation.get('security') for _,_,operation in operations)
    assert {method for method,_,_ in operations} == {'get','post'}


def test_development_conversation_requires_authentication():
    operation=app.openapi()['paths']['/development/plans/{plan_id}/conversation']['post']
    assert operation['security']
