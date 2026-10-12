"""Mock Excel MCP server: writes a real .xlsx workbook into the client's folder.

Run it alone:  python mcp_excel.py
"""
from mcp.server.mcpserver import MCPServer
from openpyxl import Workbook
from openpyxl.styles import Font

from mcp_drive import FILES, stored_name

server = MCPServer("excel", log_level="WARNING")


@server.tool()
def create_workbook(client_id: int, filename: str, rows: list[list[str]]) -> str:
    """Write rows to a workbook in the client's folder; the first row is the header. Returns its name."""
    workbook = Workbook()
    sheet = workbook.active
    for row in rows:
        # A cell that starts with "=" would run as a formula when the bank opens the file.
        sheet.append(["'" + cell if cell.startswith("=") else cell for cell in row])
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for column, width in zip("ABCD", (6, 22, 58, 48)):
        sheet.column_dimensions[column].width = width
    folder = FILES / str(client_id)
    folder.mkdir(parents=True, exist_ok=True)
    workbook.save(folder / stored_name(filename))
    return stored_name(filename)


if __name__ == "__main__":
    server.run()
