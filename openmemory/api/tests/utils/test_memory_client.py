from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.utils import memory_client


class _DummySpan:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def set_attribute(self, *args, **kwargs):
        return None

    def record_exception(self, *args, **kwargs):
        return None

    def set_status(self, *args, **kwargs):
        return None


class _DummyTracer:
    def start_as_current_span(self, *args, **kwargs):
        return _DummySpan()


class _QueryStub:
    def __init__(self, result_rows):
        self._result_rows = result_rows

    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return self._result_rows


class _DbStub:
    def __init__(self, rows):
        self._rows = rows

    def query(self, *args, **kwargs):
        return _QueryStub(self._rows)

    def close(self):
        return None


@pytest.fixture(autouse=True)
def _stub_tracer(monkeypatch):
    monkeypatch.setattr(memory_client, "_TRACER", _DummyTracer())


@pytest.mark.asyncio
async def test_search_memories_passes_app_uuid_to_acl(monkeypatch):
    user = SimpleNamespace(id=uuid4())
    app = SimpleNamespace(id=uuid4(), is_active=True)
    memory_rows = [SimpleNamespace(id=uuid4())]

    db = _DbStub(memory_rows)
    monkeypatch.setattr(memory_client, "SessionLocal", lambda: db)
    monkeypatch.setattr(memory_client, "get_user_and_app", lambda *_args, **_kwargs: (user, app))

    class _VectorStore:
        def search(self, query, embeddings, limit, final_filters, page_number):
            return []

    class _EmbeddingModel:
        def embed(self, query, mode):
            return [0.42]

    client = SimpleNamespace(vector_store=_VectorStore(), embedding_model=_EmbeddingModel())
    monkeypatch.setattr(memory_client, "get_memory_client_safe", lambda: client)

    import app.utils.permissions as permissions

    captured = {}

    def _fake_acl(db_arg, app_id_arg, user_arg):
        captured["db"] = db_arg
        captured["app_id"] = app_id_arg
        captured["user"] = user_arg
        assert isinstance(app_id_arg, UUID)
        assert user_arg is user
        return {memory_rows[0].id}

    monkeypatch.setattr(permissions, "get_accessible_memory_ids", _fake_acl)

    result = await memory_client.search_memories(
        query="case 98",
        user_id=str(user.id),
        app_id=str(app.id),
        numberOfHits=5,
        page=1,
    )

    assert result == []
    assert captured["db"] is db
    assert captured["app_id"] == app.id
    assert captured["user"] is user


@pytest.mark.asyncio
async def test_search_memories_none_acl_means_all_accessible(monkeypatch):
    user = SimpleNamespace(id=uuid4())
    app = SimpleNamespace(id=uuid4(), is_active=True)
    memory_rows = [SimpleNamespace(id=uuid4()), SimpleNamespace(id=uuid4())]

    db = _DbStub(memory_rows)
    monkeypatch.setattr(memory_client, "SessionLocal", lambda: db)
    monkeypatch.setattr(memory_client, "get_user_and_app", lambda *_args, **_kwargs: (user, app))

    class _VectorStore:
        def __init__(self):
            self.final_filters = None

        def search(self, query, embeddings, limit, final_filters, page_number):
            self.final_filters = final_filters
            return []

    class _EmbeddingModel:
        def embed(self, query, mode):
            return [0.42]

    vector_store = _VectorStore()
    client = SimpleNamespace(vector_store=vector_store, embedding_model=_EmbeddingModel())
    monkeypatch.setattr(memory_client, "get_memory_client_safe", lambda: client)

    import app.utils.permissions as permissions

    monkeypatch.setattr(permissions, "get_accessible_memory_ids", lambda *_args, **_kwargs: None)

    result = await memory_client.search_memories(
        query="case 98",
        user_id=str(user.id),
        app_id=str(app.id),
        numberOfHits=5,
        page=1,
    )

    assert result == []
    assert vector_store.final_filters is not None
    has_id_conditions = [
        cond for cond in (vector_store.final_filters.must or [])
        if hasattr(cond, "has_id") and cond.has_id is not None
    ]
    assert len(has_id_conditions) == 1
    assert set(has_id_conditions[0].has_id) == {str(memory_rows[0].id), str(memory_rows[1].id)}
