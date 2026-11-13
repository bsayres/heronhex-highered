"""The hosted server carries every tool unchanged, refuses to run unkeyed, checks the Host header, and serves MCP over HTTP."""
import json

import httpx
import pytest

from highered_hosted import prewarm
from highered_hosted import server as hosted

EXPECTED_TOOLS = sum(len(p.mcp._tool_manager.list_tools()) for p in hosted.PARTS)


def _payload(r: httpx.Response) -> dict:
    """The JSON-RPC body, whether the server answered as JSON or as one SSE event."""
    if r.headers.get("content-type", "").startswith("application/json"):
        return r.json()
    data = [line[5:].strip() for line in r.text.splitlines() if line.startswith("data:")]
    assert data, r.text
    return json.loads(data[-1])


async def test_every_tool_once_with_metadata():
    mcp = hosted.build()
    tools = await mcp.list_tools()
    assert len(tools) == EXPECTED_TOOLS >= 25
    names = [t.name for t in tools]
    assert len(set(names)) == len(names)
    for t in tools:
        assert t.title and t.description, t.name
        assert t.annotations is not None and t.annotations.read_only_hint is True, t.name


async def test_prompt_carried_over():
    prompts = await hosted.build().list_prompts()
    assert "institution_brief" in {p.name for p in prompts}


def test_prewarm_plan_names_real_tools_with_valid_arguments():
    for part, name, args in prewarm.PLAN:
        tool = part.mcp._tool_manager.get_tool(name)
        assert tool is not None, name
        assert set(args) <= set(tool.parameters["properties"]), name


def test_refuses_to_start_on_demo_keys(monkeypatch):
    for v in hosted.REQUIRED_ENV:
        monkeypatch.delenv(v, raising=False)
    monkeypatch.delenv(hosted.ALLOW_UNKEYED_VAR, raising=False)
    with pytest.raises(SystemExit) as e:
        hosted.check_env()
    assert all(v in str(e.value) for v in hosted.REQUIRED_ENV)
    monkeypatch.setenv(hosted.ALLOW_UNKEYED_VAR, "1")
    hosted.check_env()


def test_security_settings_follow_the_host_list(monkeypatch):
    monkeypatch.setenv(hosted.ALLOWED_HOSTS_VAR, "mcp.example.org, app.example.net")
    s = hosted.security()
    assert s.enable_dns_rebinding_protection
    assert s.allowed_hosts == ["mcp.example.org", "app.example.net"]
    assert s.allowed_origins == ["https://mcp.example.org", "https://app.example.net"]
    monkeypatch.delenv(hosted.ALLOWED_HOSTS_VAR)
    assert not hosted.security().enable_dns_rebinding_protection


async def test_http_endpoint(monkeypatch, tmp_path):
    monkeypatch.setenv("HIGHERED_MCPS_CACHE", str(tmp_path))
    monkeypatch.setenv(hosted.ALLOWED_HOSTS_VAR, "testserver")
    app = hosted.app()
    headers = {"content-type": "application/json", "accept": "application/json, text/event-stream"}
    async with app.router.lifespan_context(app), httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as c:
        r = await c.get("/healthz")
        assert r.status_code == 200 and r.json() == {"status": "ok", "name": hosted.NAME, "version": hosted.__version__}

        init = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "0"}}}
        r = await c.post(hosted.MCP_PATH, json=init, headers=headers)
        assert r.status_code == 200, r.text
        assert _payload(r)["result"]["serverInfo"]["name"] == hosted.NAME

        r = await c.post(hosted.MCP_PATH, json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, headers=headers)
        assert r.status_code == 200, r.text
        assert len(_payload(r)["result"]["tools"]) == EXPECTED_TOOLS

        r = await c.post(hosted.MCP_PATH, json={"jsonrpc": "2.0", "id": 3, "method": "tools/list"}, headers={**headers, "host": "evil.example"})
        assert r.status_code == 421

        r = await c.post(hosted.MCP_PATH, content=b"x" * 10, headers={**headers, "content-type": "text/plain"})
        assert r.status_code == 400
