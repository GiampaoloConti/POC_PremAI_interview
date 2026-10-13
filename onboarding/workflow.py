"""The onboarding workflow: fixed steps and one status per client.

The agent's steps (steps.py) run inside the workflow and never choose what happens next.
Files, emails and spreadsheets are reached only through MCP tools (tools.py).
Nothing in this file sends anything to a bank: that is always the employee, outside the system.

The file is in three parts: what the client does, what the agent does, what the employee does.
"""
import base64
import json
import logging
import secrets
from datetime import date

from onboarding import db, emails, steps, tools

log = logging.getLogger(__name__)

# The stage is the simple view of a status, shown as four steps on the screens.
STATUSES = {
    "started":                {"label": "Started",                "waiting_on": "Agent",    "stage": "Documents"},
    "awaiting_documents":     {"label": "Awaiting documents",     "waiting_on": "Client",   "stage": "Documents"},
    "documents_complete":     {"label": "Documents complete",     "waiting_on": "Agent",    "stage": "Review"},
    "form_drafted":           {"label": "Form drafted",           "waiting_on": "Agent",    "stage": "Review"},
    "in_review":              {"label": "In review",              "waiting_on": "Employee", "stage": "Review"},
    "sent_to_bank":           {"label": "Sent to bank",           "waiting_on": "Bank",     "stage": "Bank"},
    "bank_needs_information": {"label": "Bank needs information", "waiting_on": "Employee", "stage": "Bank"},
    "bank_accepted":          {"label": "Bank accepted",          "waiting_on": "Employee", "stage": "Bank"},
    "onboarded":              {"label": "Onboarded",              "waiting_on": "",         "stage": "Onboarded"},
}
STAGES = ["Documents", "Review", "Bank", "Onboarded"]

REMINDER_DAYS = [1, 3]      # days of waiting before the first and the second reminder
CALL_CLIENT_DAY = 5         # still nothing after the last reminder: the employee is asked to call

QUESTION_TEXT = {question["id"]: question["text"] for question in steps.QUESTIONS}
DETAILS_MISSING = "To complete your onboarding form we still need a few details that are not in your documents."
BANK_ASKS = "The bank reviewing your file has asked for some additional information."


def get(client_id):
    return db.one("SELECT * FROM clients WHERE id = ?", client_id)


def find_by_email(email):
    """The file of the client with this email address, or None. One file per address."""
    return db.one("SELECT * FROM clients WHERE lower(email) = ?", email.strip().lower())


def set_status(client_id, status, actor="Workflow"):
    db.run("UPDATE clients SET status = ? WHERE id = ?", status, client_id)
    db.log(client_id, actor, f"Status: {STATUSES[status]['label']}", status)
    return status


def oldest_year_accepted():
    """Documents must be from this year or the previous one."""
    return db.now().year - 1


def read_documents(client_id):
    """The client's documents that the document reader has already read."""
    return db.query("SELECT * FROM documents WHERE client_id = ? AND type IS NOT NULL", client_id)


# ---------------------------------------------------------------- the client

def start_onboarding(name, email):
    """A new client registers. They can send their documents now or later, in any order."""
    client_id = db.run("INSERT INTO clients (token, name, email, status, created_at) VALUES (?, ?, ?, 'started', ?)",
                       secrets.token_urlsafe(16), name, email, db.timestamp())
    db.log(client_id, "Client", "Registered on the portal", "started")
    return get(client_id)


def add_documents(client_id, files):
    """Save uploaded files in the client's Google Drive folder. files = [(name, content), ...]"""
    for name, content in files:
        stored = tools.call("Google Drive", "upload_file", client_id=client_id, filename=name,
                            content_base64=base64.b64encode(content).decode())
        db.run("INSERT INTO documents (client_id, filename, uploaded_at) VALUES (?, ?, ?)",
               client_id, stored, db.timestamp())
        db.log(client_id, "Client", f"Uploaded {stored}")
    db.run("UPDATE clients SET alert = '' WHERE id = ?", client_id)


# ----------------------------------------------------------------- the agent

def advance(client_id):
    """Run every automatic step this file is ready for.

    Each step saves its result before the next one starts, so this can be run again at any
    time (after a failure, a restart or a new upload) and it continues where the file stopped.
    """
    # Document reader: read every file that has not been read yet.
    for document in db.query("SELECT * FROM documents WHERE client_id = ? AND type IS NULL", client_id):
        content = base64.b64decode(tools.call("Google Drive", "download_file", client_id=client_id,
                                              filename=document["filename"]))
        reading = steps.read_document(document["filename"], content, oldest_year_accepted())
        db.run("UPDATE documents SET type = ?, year = ?, problem = ?, text = ? WHERE id = ?",
               reading["type"], reading["year"], reading["problem"], reading["text"], document["id"])
        db.log(client_id, "Document reader",
               f"{document['filename']}: {steps.describe(reading)} (model: {steps.MODEL})")

    client = get(client_id)
    status = client["status"]
    documents = read_documents(client_id)

    # Completeness check: the file waits here until the three documents are in.
    if status in ("started", "awaiting_documents"):
        checklist = steps.checklist(documents, oldest_year_accepted())
        if status == "started":
            emails.send_welcome(client, checklist)
        if not all(item["received"] for item in checklist):
            if status == "started":
                db.run("UPDATE clients SET waiting_since = ? WHERE id = ?", db.now().date().isoformat(), client_id)
                set_status(client_id, "awaiting_documents")
            return
        status = set_status(client_id, "documents_complete")

    # Form filler and verifier: draft the 30 answers, each with its source.
    if status == "documents_complete":
        usable = [document for document in documents if document["problem"] is None]
        answers = steps.draft_form(usable)
        for answer in answers:
            db.run("INSERT OR REPLACE INTO answers (client_id, question_id, flag, value, agent_value, source,"
                   " quote, note, options) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                   client_id, answer["id"], answer["flag"], answer["value"], answer["value"],
                   answer["source"], answer["quote"], answer["note"], json.dumps(answer["options"]))
        flags = [answer["flag"] for answer in answers]
        db.log(client_id, "Form filler", f"Drafted the form from {len(usable)} documents (model: {steps.MODEL})")
        db.log(client_id, "Verifier",
               f"{flags.count('ok')} answers verified against their source, {flags.count('unverified')} could not "
               f"be verified, {flags.count('conflict')} where documents disagree, "
               f"{flags.count('not_found')} not in the documents")
        log.info("Answers left to a person: %s", ", ".join(
            f"{answer['id']} ({answer['flag']})" for answer in answers if answer["flag"] != "ok") or "none",
            extra={"client": client_id})
        status = set_status(client_id, "form_drafted")

    # Email drafter: answers that are not in the documents become questions to the client.
    if status == "form_drafted":
        not_found = {row["question_id"] for row in db.query(
            "SELECT question_id FROM answers WHERE client_id = ? AND flag = 'not_found'", client_id)}
        missing = [question["text"] for question in steps.QUESTIONS if question["id"] in not_found]
        if missing:
            body = steps.draft_client_email(client["name"], missing, DETAILS_MISSING)
            emails.save_draft(client, "questions", "A few details to complete your file", body)
        set_status(client_id, "in_review")


def send_reminders():
    """Scheduled job (once a day in production): chase the files that are waiting for documents."""
    today = db.now().date()
    for client in db.query("SELECT * FROM clients WHERE status = 'awaiting_documents'"):
        days_waiting = (today - date.fromisoformat(client["waiting_since"])).days
        sent = client["reminders_sent"]
        if sent < len(REMINDER_DAYS) and days_waiting >= REMINDER_DAYS[sent]:
            checklist = steps.checklist(read_documents(client["id"]), oldest_year_accepted())
            emails.send_reminder(client, checklist, last=sent + 1 == len(REMINDER_DAYS))
            db.run("UPDATE clients SET reminders_sent = ? WHERE id = ?", sent + 1, client["id"])
        elif sent == len(REMINDER_DAYS) and days_waiting >= CALL_CLIENT_DAY and not client["alert"]:
            db.run("UPDATE clients SET alert = ? WHERE id = ?",
                   f"No answer after {sent} reminders. Please call the client.", client["id"])
            db.log(client["id"], "Workflow", "No answer after the last reminder: employee asked to call the client")


def read_bank_reply(client_id):
    """Bank reply reader: say what the bank decided and list what it asks for."""
    client = get(client_id)
    reading = steps.read_bank_reply(client["bank_reply"])
    db.log(client_id, "Bank reply reader",
           f"Read the bank's reply as: {reading['outcome'].replace('_', ' ')} (model: {steps.MODEL})")
    if reading["outcome"] == "unclear":
        db.run("UPDATE clients SET alert = ? WHERE id = ?",
               "The agent could not tell what the bank decided. Please read the reply and choose.", client_id)
    else:
        set_bank_outcome(client_id, reading["outcome"], reading["requests"], "Workflow")


def agent_failed(client_id, error):
    """The agent is unavailable: keep everything and hand the file to the employee."""
    db.run("UPDATE clients SET alert = ? WHERE id = ?",
           "The agent could not finish its work on this file. Nothing is lost: let it try again, "
           "or continue by hand from the documents.", client_id)
    db.log(client_id, "Workflow", f"Agent unavailable: {error}")


def resume(client_id):
    """Pick the file up where it stopped."""
    client = get(client_id)
    db.run("UPDATE clients SET alert = '' WHERE id = ?", client_id)
    if client["status"] == "sent_to_bank" and client["bank_reply"]:
        read_bank_reply(client_id)
    else:
        advance(client_id)


# -------------------------------------------------------------- the employee

def needs_attention(answer):
    """True while the employee still has something to do on this answer."""
    if not answer["value"].strip():
        return True         # not in the documents, or documents disagree and no value chosen yet
    return answer["flag"] == "unverified" and not answer["checked"] and answer["value"] == answer["agent_value"]


def save_review(client_id, values, checked):
    """Store the employee's edits on the review screen.

    values = {question_id: text}, checked = ids ticked as "this answer is correct".
    """
    client = get(client_id)
    if client["status"] != "in_review" or client["form_approved"]:
        return
    for answer in db.query("SELECT * FROM answers WHERE client_id = ?", client_id):
        question_id = answer["question_id"]
        value, source, quote = values.get(question_id, answer["value"]).strip(), answer["source"], answer["quote"]
        for option in json.loads(answer["options"]):
            if option["value"] == value:        # the employee chose one of the values the documents disagree on
                source, quote = option["source"], option["quote"]
        if value != answer["value"]:
            db.log(client_id, "Employee",
                   f"{QUESTION_TEXT[question_id]}: changed from '{answer['value']}' to '{value}'")
        db.run("UPDATE answers SET value = ?, source = ?, quote = ?, checked = ? WHERE client_id = ? AND question_id = ?",
               value, source, quote, answer["checked"] or question_id in checked, client_id, question_id)


def approve_form(client_id):
    """The employee approves the form. Returns the questions that still need attention (none = approved)."""
    answers = db.query("SELECT * FROM answers WHERE client_id = ?", client_id)
    waiting = {answer["question_id"] for answer in answers if needs_attention(answer)}
    still_open = [question["text"] for question in steps.QUESTIONS if question["id"] in waiting]
    if still_open or get(client_id)["status"] != "in_review":
        return still_open
    drafted = [answer for answer in answers if answer["agent_value"]]
    corrected = [answer for answer in drafted if answer["value"] != answer["agent_value"]]
    db.run("UPDATE clients SET form_approved = 1 WHERE id = ?", client_id)
    tools.call("Gmail", "delete_drafts", client_id=client_id, label="questions")     # no longer needed
    db.log(client_id, "Employee", f"Approved the form, after correcting {len(corrected)} of the "
                                  f"{len(drafted)} answers drafted by the agent")
    return []


def reopen_form(client_id):
    client = get(client_id)
    if client["status"] == "in_review" and client["form_approved"]:
        db.run("UPDATE clients SET form_approved = 0 WHERE id = ?", client_id)
        db.log(client_id, "Employee", "Reopened the form for changes")


def mark_sent_to_bank(client_id):
    """The employee has sent the exported form to the bank. The agent has no way to do this itself."""
    client = get(client_id)
    if client["status"] == "in_review" and client["form_approved"]:
        db.run("UPDATE clients SET bank_reply = '', bank_requests = '[]' WHERE id = ?", client_id)
        set_status(client_id, "sent_to_bank", "Employee")


def record_bank_reply(client_id, text):
    """The bank's reply arrives (pasted by the employee in the POC, read from the mailbox in production)."""
    db.run("UPDATE clients SET bank_reply = ?, bank_requests = '[]', alert = '' WHERE id = ?", text, client_id)
    db.log(client_id, "Bank", "Reply received")


def set_bank_outcome(client_id, outcome, requests=(), actor="Employee"):
    """Apply the bank's decision: the agent's reading of the reply, or the employee's own."""
    client = get(client_id)
    if client["status"] not in ("sent_to_bank", "bank_accepted", "bank_needs_information"):
        return
    tools.call("Gmail", "delete_drafts", client_id=client_id, label="bank_request")
    if outcome == "accepted":
        status = "bank_accepted"
    else:
        if requests:
            body = steps.draft_client_email(client["name"], list(requests), BANK_ASKS)
        else:       # the employee decided without a list from the agent: they fill it in
            body = f"Dear {client['name'].split()[0]},\n\n{BANK_ASKS}\n\n1. \n\nThank you,\nThe onboarding team"
        emails.save_draft(client, "bank_request", "The bank needs a little more information", body)
        status = "bank_needs_information"
    db.run("UPDATE clients SET alert = '', bank_requests = ? WHERE id = ?", json.dumps(list(requests)), client_id)
    set_status(client_id, status, actor)


def send_draft(email_id, body):
    """The employee approves an email drafted by the agent, edited or not. Returns the client's id."""
    email = db.one("SELECT * FROM emails WHERE id = ? AND sent_at IS NULL", email_id)
    if not email:
        return None
    client = get(email["client_id"])
    tools.call("Gmail", "send_draft", client_id=client["id"], draft_id=email_id, body=body)
    db.log(client["id"], "Employee", f"Approved and sent to {client['email']}: {email['subject']}")
    if email["label"] == "bank_request" and client["status"] == "bank_needs_information":
        db.run("UPDATE clients SET form_approved = 0 WHERE id = ?", client["id"])   # the form is open again
        set_status(client["id"], "in_review", "Employee")
    return client["id"]


def confirm_onboarded(client_id):
    """Only the employee can close an onboarding. Signing follows the current process."""
    if get(client_id)["status"] == "bank_accepted":
        set_status(client_id, "onboarded", "Employee")
