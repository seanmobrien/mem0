import pytest
from unittest.mock import patch
from app.utils import permissions
try:
    from app.models import MemoryState
    ACTIVE_STATE = MemoryState.active
except ImportError:
    pytest.skip("app.models.MemoryState is unavailable; skipping permission tests", allow_module_level=True)

class DummyMemory:
    def __init__(self, state, id, user_id):
        self.state = state
        self.id = id
        self.user_id = user_id

class DummyApp:
    def __init__(self, id, is_active=True):
        self.id = id
        self.is_active = is_active

class DummyUser:
    def __init__(self, id):
        self.id = id

class DummyDB:
    def __init__(self, app=None):
        self._app = app
    def query(self, model):
        class Q:
            def filter(self, *args, **kwargs):
                return self
            def first(inner_self):
                return self._app
        return Q()

def test_memory_inactive():
    db = DummyDB()
    memory = DummyMemory(state='archived', id=1, user_id=1)
    user = DummyUser(id=1)
    assert not permissions.check_memory_access_permissions(db, memory, user)

def test_memory_active_no_app():
    db = DummyDB()
    memory = DummyMemory(state=ACTIVE_STATE, id=1, user_id=1)
    user = DummyUser(id=1)
    assert permissions.check_memory_access_permissions(db, memory, user)

def test_app_not_found():
    db = DummyDB(app=None)
    memory = DummyMemory(state=ACTIVE_STATE, id=1, user_id=1)
    user = DummyUser(id=1)
    assert not permissions.check_memory_access_permissions(db, memory, user, app_id=123)

def test_app_inactive():
    db = DummyDB(app=DummyApp(id=123, is_active=False))
    memory = DummyMemory(state=ACTIVE_STATE, id=1, user_id=1)
    user = DummyUser(id=1)
    assert not permissions.check_memory_access_permissions(db, memory, user, app_id=123)

def test_app_accessible_memory_ids_all():
    db = DummyDB(app=DummyApp(id=123, is_active=True))
    memory = DummyMemory(state=ACTIVE_STATE, id=1, user_id=1)
    user = DummyUser(id=1)
    with patch('app.utils.permissions.get_accessible_memory_ids', return_value=None):
        assert permissions.check_memory_access_permissions(db, memory, user, app_id=123)

def test_app_accessible_memory_ids_subset():
    db = DummyDB(app=DummyApp(id=123, is_active=True))
    memory = DummyMemory(state=ACTIVE_STATE, id=1, user_id=1)
    user = DummyUser(id=1)
    with patch('app.utils.permissions.get_accessible_memory_ids', return_value={1, 2, 3}):
        assert permissions.check_memory_access_permissions(db, memory, user, app_id=123)
    with patch('app.utils.permissions.get_accessible_memory_ids', return_value={2, 3}):
        assert not permissions.check_memory_access_permissions(db, memory, user, app_id=123)
