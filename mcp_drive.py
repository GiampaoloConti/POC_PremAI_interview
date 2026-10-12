"""Mock Google Drive MCP server: one folder per client.

It is a real MCP server with the tools the workflow needs. Only the storage is fake: files go
to data/files/ on this machine instead of Google Drive.    Run it alone:  python mcp_drive.py
"""
import base64
import re

from mcp.server.mcpserver import MCPServer

import db

server = MCPServer("google-drive", log_level="WARNING")
FILES = db.DATA / "files"


def stored_name(filename):
    """A file name without folders or odd characters."""
    return re.sub(r"[^\w.-]", "_", filename)


@server.tool()
def upload_file(client_id: int, filename: str, content_base64: str) -> str:
    """Save a file in the client's folder. Returns the name it was stored under."""
    folder = FILES / str(client_id)
    folder.mkdir(parents=True, exist_ok=True)
    name = stored_name(filename)
    while (folder / name).exists():         # never overwrite what the client sent before
        name = "new_" + name
    (folder / name).write_bytes(base64.b64decode(content_base64))
    return name


@server.tool()
def download_file(client_id: int, filename: str) -> str:
    """The content of a file in the client's folder, base64-encoded."""
    return base64.b64encode((FILES / str(client_id) / stored_name(filename)).read_bytes()).decode()


if __name__ == "__main__":
    server.run()
