from mcp.client.client import Client

from filament_agent.mcp_server import build_server


async def test_tools_and_annotations(service):
    async with Client(build_server(service)) as c:
        tools = {t.name: t for t in (await c.list_tools()).tools}
    assert set(tools) == {
        "list_spools",
        "get_spool",
        "list_prints",
        "usage_summary",
        "check_print_feasibility",
        "log_print",
        "correct_spool_weight",
    }
    writes = {n for n, t in tools.items() if not t.annotations.read_only_hint}
    assert writes == {"log_print", "correct_spool_weight"}


async def test_structured_output(service):
    async with Client(build_server(service)) as c:
        r = await c.call_tool("check_print_feasibility", {"grams": 180, "material": "PETG"})
    assert not r.is_error
    assert r.structured_content["verdict"] == "yes"
    assert r.structured_content["best_spool_id"] == 4


async def test_errors_are_readable(service):
    async with Client(build_server(service)) as c:
        r = await c.call_tool("get_spool", {"spool_id": 99})
    assert r.is_error
    assert "spool 99 not found" in r.content[0].text
