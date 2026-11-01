import asyncio

from highered_accreditation import server


def test_every_tool_has_a_title_and_read_only_hint():
    tools = asyncio.run(server.mcp.list_tools())
    assert tools
    for t in tools:
        assert t.title and t.title.strip(), t.name
        assert t.annotations is not None and t.annotations.title == t.title, t.name
        assert t.annotations.read_only_hint is True, t.name
        assert len(t.name) <= 64, t.name
        assert t.description and t.description.strip(), t.name
