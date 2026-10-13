"""The workflow's only way to reach Google Drive, Gmail and Excel: MCP tool calls.

In this POC the three servers are mocks that run inside the app. To use real ones, replace
the server object given to Client() with the address of a real MCP server; nothing else changes.
"""
import asyncio

from mcp import Client

from onboarding import db, mcp_drive, mcp_excel, mcp_gmail

SERVERS = {"Google Drive": mcp_drive.server, "Gmail": mcp_gmail.server, "Excel": mcp_excel.server}


def call(server, tool, **arguments):
    """Call one tool of an MCP server, record the call in the audit log, and return its result."""
    async def run():
        async with Client(SERVERS[server]) as client:
            return await client.call_tool(tool, arguments)

    result = asyncio.run(run())
    if result.is_error:
        raise RuntimeError(f"{server} tool {tool} failed: {result.content[0].text}")
    # Short arguments only: file contents and email bodies stay out of the log.
    shown = ", ".join(f"{name}={value!r}" for name, value in arguments.items() if len(str(value)) < 60)
    db.log(arguments["client_id"], f"{server} (MCP)", f"{tool}({shown})")
    return result.structured_content["result"]
