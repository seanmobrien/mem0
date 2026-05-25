import pytest

from app.routers import config as config_router


@pytest.mark.parametrize(
    "value, expected",
    [
        (None, False),
        ("", False),
        ("false", False),
        ("off", False),
        ("0", False),
        ("true", True),
        ("TRUE", True),
        ("yes", True),
        ("on", True),
        ("1", True),
    ],
)
def test_is_truthy(value, expected):
    assert config_router._is_truthy(value) is expected


def test_has_mcp_tool_write_access_from_scope():
    token_claims = {"scope": "openid profile mcp_tool:write"}
    assert config_router._has_mcp_tool_write_access(token_claims) is True


def test_has_mcp_tool_write_access_from_resource_access_roles():
    token_claims = {
        "resource_access": {
            "openmemory-api": {
                "roles": ["mcp_tool:write"]
            }
        }
    }
    assert config_router._has_mcp_tool_write_access(token_claims) is True


def test_has_mcp_tool_write_access_from_resource_access_permissions():
    token_claims = {
        "resource_access": {
            "openmemory-api": {
                "permissions": ["mcp_tool:write"]
            }
        }
    }
    assert config_router._has_mcp_tool_write_access(token_claims) is True


def test_has_mcp_tool_write_access_missing_claim():
    token_claims = {"scope": "openid mcp_tool:read"}
    assert config_router._has_mcp_tool_write_access(token_claims) is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "secrets,current_user,expected_expand",
    [
        (None, None, False),
        ("false", {"scope": "openid mcp_tool:write"}, False),
        ("true", None, False),
        ("true", {"scope": "openid mcp_tool:read"}, False),
        ("true", {"scope": "openid mcp_tool:write"}, True),
        (
            "1",
            {"resource_access": {"openmemory-api": {"roles": ["mcp_tool:write"]}}},
            True,
        ),
    ],
)
async def test_get_configuration_secrets_gate(monkeypatch, secrets, current_user, expected_expand):
    captured = {}

    def _fake_get_saved_memory_config(expand_secrets=False):
        captured["expand_secrets"] = expand_secrets
        return config_router.ConfigSchema.model_validate({"mem0": {"version": "v1.1"}})

    monkeypatch.setattr(config_router, "get_saved_memory_config", _fake_get_saved_memory_config)

    # Should not be called in this test path because get_saved_memory_config returns data.
    monkeypatch.setattr(config_router, "get_default_config", lambda: pytest.fail("unexpected default config call"))

    result = await config_router.get_configuration(
        secrets=secrets,
        db=None,
        current_user=current_user,
    )

    assert captured["expand_secrets"] is expected_expand
    assert result["mem0"]["version"] == "v1.1"


@pytest.mark.asyncio
async def test_get_configuration_denial_logs_and_traces(monkeypatch, caplog):
    class _SpanStub:
        def __init__(self):
            self.attributes = {}
            self.events = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def set_attribute(self, key, value):
            self.attributes[key] = value

        def add_event(self, name, attributes):
            self.events.append((name, attributes))

    class _TracerStub:
        def __init__(self, span):
            self._span = span

        def start_as_current_span(self, *args, **kwargs):
            return self._span

    span = _SpanStub()

    monkeypatch.setattr(config_router, "_TRACER", _TracerStub(span))
    monkeypatch.setattr(config_router.trace, "get_current_span", lambda *args, **kwargs: span)
    monkeypatch.setattr(
        config_router,
        "get_saved_memory_config",
        lambda expand_secrets=False: config_router.ConfigSchema.model_validate({"mem0": {"version": "v1.1"}}),
    )

    with caplog.at_level("WARNING"):
        result = await config_router.get_configuration(
            secrets="true",
            db=None,
            current_user={"scope": "openid mcp_tool:read"},
        )

    assert result["mem0"]["version"] == "v1.1"
    assert "Denied resolved config request without mcp_tool:write access" in caplog.text
    assert span.attributes["mem0.config.secrets_requested"] is True
    assert span.attributes["mem0.config.secrets_authorized"] is False
    assert span.attributes["mem0.config.auth_present"] is True
    assert span.events == [
        (
            "config.secrets_access_denied",
            {
                "mem0.required_access": "mcp_tool:write",
                "mem0.auth_present": True,
            },
        )
    ]
