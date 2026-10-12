"""Mock Gmail MCP server for the onboarding mailbox.

Every tool takes a client id and the server looks up the registered address itself. No tool
accepts a free recipient, so the agent cannot write to a bank or to a stranger.
Only the delivery is fake: emails are kept in the database instead of being sent.
Run it alone:  python mcp_gmail.py
"""
from mcp.server.mcpserver import MCPServer

import db

server = MCPServer("gmail", log_level="WARNING")


def store(client_id, subject, body, label, sent):
    recipient = db.one("SELECT email FROM clients WHERE id = ?", client_id)["email"]
    return db.run("INSERT INTO emails (client_id, recipient, label, subject, body, created_at, sent_at)"
                  " VALUES (?, ?, ?, ?, ?, ?, ?)",
                  client_id, recipient, label, subject, body, db.timestamp(), db.timestamp() if sent else None)


@server.tool()
def send_email(client_id: int, subject: str, body: str, label: str) -> int:
    """Send an email to the client's registered address. Returns the email's id."""
    return store(client_id, subject, body, label, sent=True)


@server.tool()
def create_draft(client_id: int, subject: str, body: str, label: str) -> int:
    """Prepare an email to the client without sending it. Returns the draft's id."""
    return store(client_id, subject, body, label, sent=False)


@server.tool()
def send_draft(client_id: int, draft_id: int, body: str) -> int:
    """Send one of the client's drafts with its final text."""
    db.run("UPDATE emails SET body = ?, sent_at = ? WHERE id = ? AND client_id = ? AND sent_at IS NULL",
           body, db.timestamp(), draft_id, client_id)
    return draft_id


@server.tool()
def delete_drafts(client_id: int, label: str) -> str:
    """Throw away the client's unsent drafts that carry this label."""
    db.run("DELETE FROM emails WHERE client_id = ? AND label = ? AND sent_at IS NULL", client_id, label)
    return label


if __name__ == "__main__":
    server.run()
