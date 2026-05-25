import pytest

from app.routers import well_known_auth


@pytest.mark.asyncio
async def test_oauth_protected_resource_metadata_includes_mcp_tool_write(monkeypatch):
    class _OpenIdStub:
        def well_known(self):
            return {}

    monkeypatch.setattr(well_known_auth, "get_keycloak_openid", lambda: _OpenIdStub())

    response = await well_known_auth.oauth_protected_resource_metadata()

    assert response.status_code == 200
    assert b'"mcp_tool:write"' in response.body