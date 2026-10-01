"""Current PG lifecycle schema is initialized atomically, without old file snapshots."""
import pytest
from .test_enablement_migration import assert_initialization_rollback_and_retry

@pytest.mark.parametrize('fault_at', list(range(1, 15)) + [None])
def test_lifecycle_schema_atomic_initialization_and_retry(fault_at):
    assert_initialization_rollback_and_retry(fault_at)
