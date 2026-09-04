from backend.app.main import app


PUBLIC_OPERATIONS = {
    ("get", "/health"),
    ("post", "/auth/login"),
    ("post", "/auth/user-applications"),
}


def test_openapi_contains_only_three_public_operations():
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
    assert len(schema["paths"]) == 60
    assert len(operations) == 71
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
