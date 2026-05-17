import sys
import types
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from mem0.utils import factory


class DummyConfig:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class DummyLlm:
    def __init__(self, config):
        self.config = config


class DummyEmbedder:
    def __init__(self, config):
        self.config = config


class DummyVectorStore:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self._search_calls = []

    def search(self, query, limit=10, filters=None):
        self._search_calls.append((query, limit, filters))
        return ["ok"]

    def reset(self):
        self.was_reset = True


class DummyTracer:
    class _Span:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            return False

        def set_attribute(self, *args, **kwargs):
            return None

        def record_exception(self, *args, **kwargs):
            return None

    def start_as_current_span(self, _name):
        return self._Span()


def _install_fake_otel(monkeypatch):
    fake_module = types.ModuleType("opentelemetry")
    # pyrefly: ignore [missing-attribute]
    fake_module.trace = SimpleNamespace(get_tracer=lambda _name: DummyTracer())
    monkeypatch.setitem(sys.modules, "opentelemetry", fake_module)


def test_load_class_imports_symbol():
    loaded = factory.load_class("json.decoder.JSONDecoder")
    from json.decoder import JSONDecoder

    assert loaded is JSONDecoder


def test_llm_factory_create_builds_llm(monkeypatch):
    monkeypatch.setitem(factory.LlmFactory.provider_to_class, "test_provider", "pkg.DummyLlm")
    monkeypatch.setattr(factory, "BaseLlmConfig", DummyConfig)
    monkeypatch.setattr(factory, "load_class", lambda _: DummyLlm)

    instance = factory.LlmFactory.create("test_provider", {"model": "x"})

    assert isinstance(instance, DummyLlm)
    assert isinstance(instance.config, DummyConfig)
    assert instance.config.kwargs == {"model": "x"}


def test_llm_factory_unsupported_provider_raises():
    with pytest.raises(ValueError, match="Unsupported Llm provider"):
        factory.LlmFactory.create("does_not_exist", {"model": "x"})


def test_embedder_factory_upstash_returns_mock_embeddings():
    vector_config = SimpleNamespace(enable_embeddings=True)

    # pyrefly: ignore [bad-argument-type]
    instance = factory.EmbedderFactory.create("upstash_vector", {}, vector_config)

    assert isinstance(instance, factory.MockEmbeddings)


def test_embedder_factory_create_builds_embedder(monkeypatch):
    monkeypatch.setitem(factory.EmbedderFactory.provider_to_class, "test_provider", "pkg.DummyEmbedder")
    monkeypatch.setattr(factory, "BaseEmbedderConfig", DummyConfig)
    monkeypatch.setattr(factory, "load_class", lambda _: DummyEmbedder)

    instance = factory.EmbedderFactory.create("test_provider", {"model": "abc"}, None)

    assert isinstance(instance, DummyEmbedder)
    assert isinstance(instance.config, DummyConfig)
    assert instance.config.kwargs == {"model": "abc"}


def test_vector_store_factory_uses_model_dump_for_config_object(monkeypatch):
    class ConfigObj:
        def model_dump(self):
            return {"collection_name": "demo"}

    monkeypatch.setitem(factory.VectorStoreFactory.provider_to_class, "test_vector", "pkg.DummyVectorStore")
    monkeypatch.setattr(factory, "load_class", lambda _: DummyVectorStore)
    _install_fake_otel(monkeypatch)

    instance = factory.VectorStoreFactory.create("test_vector", ConfigObj())

    assert isinstance(instance, DummyVectorStore)
    assert instance.kwargs == {"collection_name": "demo"}


def test_vector_store_factory_wraps_search_and_preserves_result(monkeypatch):
    monkeypatch.setitem(factory.VectorStoreFactory.provider_to_class, "test_vector", "pkg.DummyVectorStore")
    monkeypatch.setattr(factory, "load_class", lambda _: DummyVectorStore)
    _install_fake_otel(monkeypatch)

    instance = factory.VectorStoreFactory.create("test_vector", {"collection_name": "demo"})
    result = instance.search("hello", limit=3, filters={"user_id": "u1"})

    assert result == ["ok"]
    assert instance._search_calls == [("hello", 3, {"user_id": "u1"})]


def test_vector_store_factory_unsupported_provider_raises():
    with pytest.raises(ValueError, match="Unsupported VectorStore provider"):
        factory.VectorStoreFactory.create("unknown", {})


def test_vector_store_factory_reset_calls_reset_and_returns_instance():
    instance = Mock()

    returned = factory.VectorStoreFactory.reset(instance)

    instance.reset.assert_called_once_with()
    assert returned is instance
