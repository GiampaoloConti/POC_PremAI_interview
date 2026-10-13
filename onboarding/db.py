"""The small database behind the status board and the audit log (SQLite, a single file)."""
import logging
import shutil
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta

from onboarding import config

DATABASE = config.DATA / "onboarding.db"
audit = logging.getLogger("onboarding.audit")

SCHEMA = """
CREATE TABLE IF NOT EXISTS clients (
    id INTEGER PRIMARY KEY,
    token TEXT UNIQUE,                 -- the client's personal portal link
    name TEXT,
    email TEXT,
    status TEXT,
    busy INTEGER DEFAULT 0,            -- 1 while the agent is working on the file
    alert TEXT DEFAULT '',             -- something the employee must look at
    waiting_since TEXT,                -- day the file started waiting for documents
    reminders_sent INTEGER DEFAULT 0,
    form_approved INTEGER DEFAULT 0,
    bank_reply TEXT DEFAULT '',
    bank_requests TEXT DEFAULT '[]',   -- what the bank asks for, as a JSON list
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    client_id INTEGER,
    filename TEXT,
    type TEXT,                         -- empty until the document reader has read the file
    year INTEGER,
    problem TEXT,                      -- unreadable, outdated or not_needed
    text TEXT,
    uploaded_at TEXT
);
CREATE TABLE IF NOT EXISTS answers (
    client_id INTEGER,
    question_id TEXT,
    flag TEXT,                         -- ok, unverified, conflict or not_found
    value TEXT,                        -- the answer as it stands now
    agent_value TEXT,                  -- what the agent drafted, kept to measure corrections
    source TEXT,                       -- the document the answer comes from
    quote TEXT,                        -- the sentence it comes from
    note TEXT,
    options TEXT,                      -- when documents disagree: every value found, as JSON
    checked INTEGER DEFAULT 0,
    PRIMARY KEY (client_id, question_id)
);
CREATE TABLE IF NOT EXISTS emails (
    id INTEGER PRIMARY KEY,
    client_id INTEGER,
    recipient TEXT,
    label TEXT,                        -- welcome, reminder, questions or bank_request
    subject TEXT,
    body TEXT,
    created_at TEXT,
    sent_at TEXT                       -- empty while the email is a draft waiting for approval
);
CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY,
    client_id INTEGER,
    at TEXT,
    actor TEXT,
    action TEXT,
    status TEXT                        -- set when the entry is a status change
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value INTEGER);
"""


def connect():
    connection = sqlite3.connect(DATABASE, isolation_level=None)   # each statement is saved at once
    connection.row_factory = sqlite3.Row
    return connection


def init():
    config.DATA.mkdir(exist_ok=True)
    with closing(connect()) as connection:
        connection.executescript(SCHEMA)


def query(sql, *values):
    with closing(connect()) as connection:
        return connection.execute(sql, values).fetchall()


def one(sql, *values):
    rows = query(sql, *values)
    return rows[0] if rows else None


def run(sql, *values):
    with closing(connect()) as connection:
        return connection.execute(sql, values).lastrowid


def now():
    """The current time. The demo's "next day" button moves this clock forward."""
    skipped = one("SELECT value FROM settings WHERE key = 'days_skipped'")
    return datetime.now() + timedelta(days=skipped["value"] if skipped else 0)


def timestamp():
    return now().isoformat(timespec="seconds")


def skip_day():
    run("INSERT INTO settings VALUES ('days_skipped', 1) ON CONFLICT (key) DO UPDATE SET value = value + 1")


def log(client_id, actor, action, status=None):
    """Audit log: who did what, and when. Every entry also goes to the log file."""
    run("INSERT INTO audit (client_id, at, actor, action, status) VALUES (?, ?, ?, ?, ?)",
        client_id, timestamp(), actor, action, status)
    audit.info("%s: %s", actor, action, extra={"client": client_id})


def reset():
    """Empty the database and delete the uploaded files (demo only)."""
    for table in ("clients", "documents", "answers", "emails", "audit", "settings"):
        run(f"DELETE FROM {table}")
    shutil.rmtree(config.DATA / "files", ignore_errors=True)
    audit.warning("Demo reset: every client, document and email was deleted")
