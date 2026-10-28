"""Exercise the real stdio MCP connection and local file offload."""
import asyncio
from datetime import timedelta
import json
import os
from pathlib import Path
import sys
import tempfile
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    here = Path(__file__).resolve().parent
    state = tempfile.TemporaryDirectory(prefix="local-grunt-smoke-")
    env = dict(os.environ, LOCAL_GRUNT_STATE=state.name, LOCAL_GRUNT_ROOTS=str(here), LOCAL_GRUNT_FAST="granite4.2:3b", LOCAL_GRUNT_PANEL="0")
    params = StdioServerParameters(command=sys.executable, args=[str(here / "adapter.py")], env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=240)) as session:
            await session.initialize()
            catalog = await session.list_tools()
            assert {t.name for t in catalog.tools} == {"local_models", "local_run", "local_digest_log", "local_outcome", "local_stats", "local_cloud_usage"}
            models = await session.call_tool("local_models", {})
            assert not models.isError
            args = {"task": "extract", "instructions": "Extract customer and seats. Return keys customer and seats.",
                    "project_path": str(here), "files": ["example-source.txt"], "force_local": True,
                    "schema": {"type": "object", "properties": {"customer": {"type": "string"}, "seats": {"type": "integer"}},
                               "required": ["customer", "seats"], "additionalProperties": False}}
            first = await session.call_tool("local_run", args)
            assert not first.isError, first
            result = json.loads(first.content[0].text)
            assert result["result"] == {"customer": "River Labs", "seats": 12}
            second = await session.call_tool("local_run", args)
            assert not second.isError
            assert json.loads(second.content[0].text)["cached"] is True
            cached = json.loads(second.content[0].text)
            assert cached["local_input_tokens"] == cached["local_output_tokens"] == 0
            verdict = await session.call_tool("local_outcome", {"call_id": result["call_id"], "outcome": "accepted"})
            assert not verdict.isError
            stats = await session.call_tool("local_stats", {})
            assert not stats.isError and json.loads(stats.content[0].text)["reviewed"] >= 1
            artifact = await session.call_tool("local_run", dict(args, output_mode="artifact"))
            assert not artifact.isError
            saved = json.loads(artifact.content[0].text)
            assert "result" not in saved
            assert json.loads(Path(saved["artifact"]["path"]).read_text()) == result["result"]
            invalid = await session.call_tool("local_run", dict(args, files=["../outside.txt"]))
            assert invalid.isError
            print(json.dumps({"mcp_initialization": "passed", "tool_catalog": "passed", "file_offload": "passed", "cache": "passed", "outcome_and_stats": "passed", "artifact": "passed", "error_propagation": "passed", "local_result": result}, indent=2))


if __name__ == "__main__": asyncio.run(main())
