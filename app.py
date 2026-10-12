"""Web pages: the client portal, the status board and the employee's page for one client.

    python app.py        then open http://localhost:8000

Pages only show data and call workflow actions. The agent's work runs on a background
worker (the job queue), so nobody waits for a model while a page loads.
"""
import base64
import io
import json
import queue
import re
import secrets
import threading
from datetime import datetime
from pathlib import Path

from flask import Flask, abort, flash, redirect, render_template, request, send_file, url_for
from markupsafe import Markup, escape

import db
import steps
import tools
import workflow

app = Flask(__name__)
app.secret_key = secrets.token_hex()
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024      # uploads up to 20 MB

ALLOWED_FILES = {".pdf", ".txt", ".png", ".jpg", ".jpeg"}
SAMPLES = Path(__file__).parent / "samples"
DEMO_CLIENTS = json.loads((SAMPLES / "expected.json").read_text())["clients"]
SAMPLE_BANK_REPLIES = {}                                  # one example per outcome, for the demo buttons
for reply in json.loads((SAMPLES / "bank_replies.json").read_text()):
    SAMPLE_BANK_REPLIES.setdefault(reply["outcome"], reply["text"])

# How the three required documents are presented to a client.
DOCUMENTS_NEEDED = {
    "bank_statement": {"icon": "bank", "hint": "A recent statement of your main bank account"},
    "tax_return": {"icon": "file", "hint": "Your latest income tax return"},
    "portfolio_statement": {"icon": "chart", "hint": "A current statement of your investments"},
}

ANSWER_STATES = {
    "verified": "Verified in the document",
    "check": "Could not be verified",
    "conflict": "Documents disagree",
    "missing": "Not in the documents",
    "edited": "Entered by you",
    "checked": "Checked by you",
}

ICONS = {       # line icons, drawn on a 24 x 24 grid
    "bank": '<path d="M3 10l9-6 9 6M5 10v8M9.5 10v8M14.5 10v8M19 10v8M3 20h18"/>',
    "file": '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h6"/>',
    "chart": '<path d="M4 20V4M4 20h16M8 16v-4M12 16V8M16 16v-6"/>',
    "check": '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "mail": '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 7l9 6 9-6"/>',
    "user": '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 4-6 8-6s8 2 8 6"/>',
    "board": '<rect x="3" y="4" width="5" height="16" rx="1"/><rect x="10" y="4" width="5" height="10" rx="1"/>'
             '<rect x="17" y="4" width="4" height="13" rx="1"/>',
    "alert": '<path d="M12 4l9 16H3z"/><path d="M12 10v4M12 17h.01"/>',
    "upload": '<path d="M12 16V5M7 10l5-5 5 5M5 19h14"/>',
    "shield": '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/><path d="M9 12l2 2 4-4"/>',
    "search": '<circle cx="11" cy="11" r="6"/><path d="M20 20l-4.5-4.5"/>',
    "flow": '<circle cx="5" cy="6" r="2"/><circle cx="19" cy="6" r="2"/><circle cx="12" cy="18" r="2"/>'
            '<path d="M7 6h10M6 8l5 8M18 8l-5 8"/>',
    "plug": '<path d="M9 3v5M15 3v5M7 8h10v3a5 5 0 0 1-10 0zM12 16v5"/>',
    "spark": '<path d="M12 3l2 6 6 2-6 2-2 6-2-6-6-2 6-2z"/>',
}


@app.template_global()
def icon(name):
    return Markup('<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
                  f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{ICONS[name]}</svg>')


@app.template_filter("when")
def when(timestamp):
    return datetime.fromisoformat(timestamp).strftime("%d %b, %H:%M") if timestamp else ""


@app.template_filter("initials")
def initials(name):
    return "".join(word[0] for word in name.split()[:2]).upper()


app.jinja_env.globals.update(statuses=workflow.STATUSES, stages=workflow.STAGES, model=steps.MODEL,
                             answer_states=ANSWER_STATES, describe=steps.describe)


# ------------------------------------------------------------- the job queue

jobs = queue.Queue()


def enqueue(client_id, step, *arguments):
    """Ask the worker to run one of the agent's steps for a client."""
    db.run("UPDATE clients SET busy = 1 WHERE id = ?", client_id)
    jobs.put((client_id, step, arguments))


def worker():
    """One background worker takes the jobs in order. If a step fails, the file goes to the employee."""
    while True:
        client_id, step, arguments = jobs.get()
        try:
            step(client_id, *arguments)
        except Exception as error:      # model down, bad key, network: whatever the cause, nothing is lost
            workflow.agent_failed(client_id, error)
        finally:
            db.run("UPDATE clients SET busy = 0 WHERE id = ?", client_id)


# ------------------------------------------------------------- demo clients

def open_demo_client(folder):
    """A demo client's file. The first time, it is created with the documents prepared for them."""
    sample = DEMO_CLIENTS[folder]
    client = workflow.find_by_email(sample["email"])
    if not client:
        client = workflow.start_onboarding(sample["name"], sample["email"])
        workflow.add_documents(client["id"], [(name, (SAMPLES / folder / name).read_bytes())
                                              for name in sample["first_upload"]])
        enqueue(client["id"], workflow.advance)
    return client


def prepared_samples(client):
    """For a demo client: the prepared documents not sent yet, as (folder, {document type: file name})."""
    for folder, sample in DEMO_CLIENTS.items():
        if sample["email"] == client["email"]:
            sent = {row["filename"] for row in db.query("SELECT filename FROM documents WHERE client_id = ?",
                                                        client["id"])}
            return folder, {document["type"]: name for name, document in sample["documents"].items()
                            if name not in sent}
    return None, {}


# --------------------------------------------------------- the client portal

def uploaded_files():
    """The files of the current upload as (name, content), leaving out types we cannot read."""
    files = []
    for upload in request.files.getlist("files"):
        if not upload.filename:
            continue
        if Path(upload.filename).suffix.lower() not in ALLOWED_FILES:
            flash(f"{upload.filename} was not added: please send a PDF, a photo (JPG or PNG) or a text file.")
            continue
        files.append((upload.filename, upload.read()))
    return files


def document_slots(client):
    """The three required documents as a client sees them: received or not, and what to do next."""
    documents = workflow.read_documents(client["id"])
    _, prepared = prepared_samples(client)
    slots = []
    for item in steps.checklist(documents, workflow.oldest_year_accepted()):
        files = [d["filename"] for d in documents if d["type"] == item["type"] and d["problem"] is None]
        slots.append({**item, **DOCUMENTS_NEEDED[item["type"]], "files": files, "sample": prepared.get(item["type"])})
    return slots


@app.get("/")
def home():
    return render_template("home.html")


@app.route("/portal", methods=["GET", "POST"])
def portal_start():
    if request.method == "POST":
        name, email = request.form.get("name", "").strip(), request.form.get("email", "").strip()
        if not name or "@" not in email:
            flash("Please enter your name and your email address.")
        else:
            client = workflow.find_by_email(email)
            if client:
                flash("You already have a file with us. Here it is.")
            else:
                client = workflow.start_onboarding(name, email)
                enqueue(client["id"], workflow.advance)
            return redirect(url_for("portal", token=client["token"]))
    needed = [{"label": label, **DOCUMENTS_NEEDED[doc_type]} for doc_type, label in steps.REQUIRED_DOCUMENTS.items()]
    return render_template("portal_start.html", needed=needed, demo_clients=DEMO_CLIENTS)


@app.post("/portal/sign-in")
def portal_sign_in():
    """A returning client opens their file with their email address.

    Demo shortcut: the real service would email a one-time sign-in link instead of opening the file.
    """
    client = workflow.find_by_email(request.form.get("email", ""))
    if not client:
        flash("We have no file for that email address. Check the spelling, or register as a new client.")
        return redirect(url_for("portal_start"))
    return redirect(url_for("portal", token=client["token"]))


@app.post("/portal/demo/<folder>")
def portal_demo(folder):
    if folder not in DEMO_CLIENTS:
        abort(404)
    return redirect(url_for("portal", token=open_demo_client(folder)["token"]))


@app.route("/portal/<token>", methods=["GET", "POST"])
def portal(token):
    client = db.one("SELECT * FROM clients WHERE token = ?", token)
    if not client:
        abort(404)
    if request.method == "POST":
        files = uploaded_files()
        if files:
            workflow.add_documents(client["id"], files)
            enqueue(client["id"], workflow.advance)
        return redirect(url_for("portal", token=token))
    slots = document_slots(client)
    unusable = [d for d in workflow.read_documents(client["id"]) if d["problem"] in ("unreadable", "not_needed")]
    messages = db.query("SELECT * FROM emails WHERE client_id = ? AND sent_at IS NOT NULL ORDER BY id DESC", client["id"])
    return render_template("portal.html", client=client, refresh=client["busy"], slots=slots, unusable=unusable,
                           messages=messages, received=sum(slot["received"] for slot in slots))


@app.post("/portal/<token>/sample/<doc_type>")
def portal_sample(token, doc_type):
    """Demo only: send the document prepared for this demo client instead of choosing a file."""
    client = db.one("SELECT * FROM clients WHERE token = ?", token)
    if not client:
        abort(404)
    folder, prepared = prepared_samples(client)
    if doc_type in prepared:
        name = prepared[doc_type]
        workflow.add_documents(client["id"], [(name, (SAMPLES / folder / name).read_bytes())])
        enqueue(client["id"], workflow.advance)
    return redirect(url_for("portal", token=token))


# ---------------------------------------------------------- the status board

def board_detail(client):
    """One line for the status board: what this file is waiting for."""
    status = client["status"]
    if client["busy"]:
        return "The agent is working on this file"
    if client["alert"]:
        return client["alert"]
    if status == "awaiting_documents":
        checklist = steps.checklist(workflow.read_documents(client["id"]), workflow.oldest_year_accepted())
        missing = ", ".join(item["label"] for item in checklist if not item["received"])
        return f"Missing: {missing}. Reminders sent: {client['reminders_sent']} of {len(workflow.REMINDER_DAYS)}"
    if status == "in_review":
        if client["form_approved"]:
            return "Form approved: download it and send it to the bank"
        answers = db.query("SELECT * FROM answers WHERE client_id = ?", client["id"])
        return f"{sum(workflow.needs_attention(a) for a in answers)} answers need your attention"
    return {"sent_to_bank": "Waiting for the bank's reply",
            "bank_needs_information": "Approve the request to the client",
            "bank_accepted": "Confirm the onboarding",
            "onboarded": "Onboarding complete"}.get(status, "")


@app.get("/board")
def board():
    columns = {"Needs you": [], "Waiting on others": [], "Onboarded": []}
    for client in db.query("SELECT * FROM clients ORDER BY id"):
        waiting_on = workflow.STATUSES[client["status"]]["waiting_on"]
        if client["busy"]:
            waiting_on = "Agent"
        elif client["alert"]:
            waiting_on = "Employee"
        if client["status"] == "onboarded":
            column = "Onboarded"
        elif waiting_on == "Employee":
            column = "Needs you"
        else:
            column = "Waiting on others"
        columns[column].append({**client, "waiting_on": waiting_on, "detail": board_detail(client)})
    busy = any(client["busy"] for clients in columns.values() for client in clients)
    return render_template("board.html", columns=columns, today=db.now(), refresh=busy)


# ------------------------------------------------- the employee's client page

def answer_state(answer):
    """Where an answer stands for the employee (the keys of ANSWER_STATES)."""
    if workflow.needs_attention(answer):
        return {"unverified": "check", "conflict": "conflict"}.get(answer["flag"], "missing")
    if answer["value"] != answer["agent_value"]:
        return "edited"
    return "verified" if answer["flag"] == "ok" else "checked"


def review_rows(client_id):
    """The questions of the form with this client's answers, in the order of the form."""
    answers = {a["question_id"]: a for a in db.query("SELECT * FROM answers WHERE client_id = ?", client_id)}
    rows = []
    for number, question in enumerate(steps.QUESTIONS, 1):
        answer = answers.get(question["id"])
        if answer:
            rows.append({**question, **answer, "number": number, "state": answer_state(answer),
                         "options": json.loads(answer["options"])})
    return rows


@app.get("/clients/<int:client_id>")
def client_page(client_id):
    client = workflow.get(client_id)
    if not client:
        abort(404)
    rows = review_rows(client_id)
    history = db.query("SELECT * FROM audit WHERE client_id = ? ORDER BY id DESC", client_id)
    reached = db.query("SELECT status, MIN(at) AS at FROM audit WHERE client_id = ? AND status IS NOT NULL "
                       "GROUP BY status", client_id)
    return render_template(
        "client.html", client=client, refresh=client["busy"],
        stage=workflow.STAGES.index(workflow.STATUSES[client["status"]]["stage"]),
        editable=client["status"] == "in_review" and not client["form_approved"],
        # The review screen: answers that need the employee, grouped by reason, then the rest.
        conflicts=[row for row in rows if row["state"] == "conflict"],
        unverified=[row for row in rows if row["state"] == "check"],
        missing=[row for row in rows if row["state"] == "missing"],
        settled=[row for row in rows if row["state"] not in ("conflict", "check", "missing")],
        drafts=db.query("SELECT * FROM emails WHERE client_id = ? AND sent_at IS NULL", client_id),
        bank_requests=json.loads(client["bank_requests"]),
        reminders=len(workflow.REMINDER_DAYS),
        # The side panels.
        checklist=steps.checklist(workflow.read_documents(client_id), workflow.oldest_year_accepted()),
        documents=db.query("SELECT * FROM documents WHERE client_id = ? ORDER BY id", client_id),
        sent=db.query("SELECT * FROM emails WHERE client_id = ? AND sent_at IS NOT NULL ORDER BY id DESC", client_id),
        reached={row["status"]: row["at"] for row in reached},
        log=[entry for entry in history if not entry["actor"].endswith("(MCP)")],
        tool_calls=[entry for entry in history if entry["actor"].endswith("(MCP)")])


def back_to(client_id, anchor=""):
    return redirect(url_for("client_page", client_id=client_id) + anchor)


@app.post("/clients/<int:client_id>/form")
def save_form(client_id):
    values = {key.removeprefix("value_"): text for key, text in request.form.items() if key.startswith("value_")}
    checked = {key.removeprefix("checked_") for key in request.form if key.startswith("checked_")}
    workflow.save_review(client_id, values, checked)
    if request.form.get("action") == "approve":
        still_open = workflow.approve_form(client_id)
        if still_open:
            flash(f"Not approved yet. {len(still_open)} answers still need you: " + "; ".join(still_open))
            return back_to(client_id, "#form")
    return back_to(client_id)


@app.post("/clients/<int:client_id>/reopen")
def reopen(client_id):
    workflow.reopen_form(client_id)
    return back_to(client_id, "#form")


@app.get("/clients/<int:client_id>/bank-form.xlsx")
def export(client_id):
    """The approved form as an Excel workbook. Sending it to the bank is the employee's job."""
    client = workflow.get(client_id)
    if not client or not client["form_approved"]:
        abort(404)
    rows = [["No.", "Section", "Question", "Answer"]]
    rows += [[str(row["number"]), row["section"], row["text"], row["value"]] for row in review_rows(client_id)]
    name = tools.call("Excel", "create_workbook", client_id=client_id, filename="bank_form_approved.xlsx", rows=rows)
    content = base64.b64decode(tools.call("Google Drive", "download_file", client_id=client_id, filename=name))
    db.log(client_id, "Employee", "Exported the approved form for the bank")
    return send_file(io.BytesIO(content), as_attachment=True,
                     download_name="bank_form_" + re.sub(r"\W+", "_", client["name"]).lower() + ".xlsx")


@app.post("/clients/<int:client_id>/sent-to-bank")
def sent_to_bank(client_id):
    workflow.mark_sent_to_bank(client_id)
    return back_to(client_id)


@app.post("/clients/<int:client_id>/bank-reply")
def bank_reply(client_id):
    text = SAMPLE_BANK_REPLIES.get(request.form.get("sample"), request.form.get("text", "")).strip()
    if text:
        workflow.record_bank_reply(client_id, text)
        enqueue(client_id, workflow.read_bank_reply)
    return back_to(client_id)


@app.post("/clients/<int:client_id>/bank-outcome")
def bank_outcome(client_id):
    """The employee decides what the bank's reply means (the agent was unsure, or wrong)."""
    if request.form.get("outcome") in ("accepted", "information_requested"):
        enqueue(client_id, workflow.set_bank_outcome, request.form["outcome"])
    return back_to(client_id)


@app.post("/clients/<int:client_id>/onboarded")
def onboarded(client_id):
    workflow.confirm_onboarded(client_id)
    return back_to(client_id)


@app.post("/clients/<int:client_id>/retry")
def retry(client_id):
    enqueue(client_id, workflow.resume)
    return back_to(client_id)


@app.post("/emails/<int:email_id>/send")
def send_email(email_id):
    client_id = workflow.send_draft(email_id, request.form.get("body", "").strip())
    return back_to(client_id) if client_id else redirect(url_for("board"))


@app.get("/clients/<int:client_id>/documents/<filename>")
def document(client_id, filename):
    """A document as the agent read it, with the sentence an answer comes from highlighted."""
    found = db.one("SELECT * FROM documents WHERE client_id = ? AND filename = ?", client_id, filename)
    if not found:
        abort(404)
    text, quote = found["text"] or "", request.args.get("quote", "")
    pattern = r"\s+".join(re.escape(word) for word in quote.split())      # same words, any spacing
    match = re.search(pattern, text, re.I) if pattern else None
    if match:
        body = (escape(text[:match.start()]) + Markup('<mark id="quote">') + escape(match.group())
                + Markup("</mark>") + escape(text[match.end():]))
    else:
        body = escape(text)
    return render_template("document.html", client=workflow.get(client_id), document=found, body=body,
                           quote=quote, found=bool(match))


@app.get("/clients/<int:client_id>/files/<filename>")
def original_file(client_id, filename):
    """The file exactly as the client sent it, fetched from their Google Drive folder."""
    if not db.one("SELECT id FROM documents WHERE client_id = ? AND filename = ?", client_id, filename):
        abort(404)
    content = base64.b64decode(tools.call("Google Drive", "download_file", client_id=client_id, filename=filename))
    return send_file(io.BytesIO(content), download_name=filename)


# ------------------------------------------------------------- demo controls

@app.post("/demo/clients")
def demo_clients():
    """Open the file of every demo client, through the same path as a real client."""
    for folder in DEMO_CLIENTS:
        open_demo_client(folder)
    return redirect(url_for("board"))


@app.post("/demo/next-day")
def demo_next_day():
    """Move the clock one day forward and run the daily reminder job."""
    db.skip_day()
    workflow.send_reminders()
    return redirect(url_for("board"))


@app.post("/demo/reset")
def demo_reset():
    db.reset()
    return redirect(url_for("board"))


if __name__ == "__main__":
    db.init()
    threading.Thread(target=worker, daemon=True).start()
    for interrupted in db.query("SELECT id FROM clients WHERE busy = 1"):    # work cut short by a restart
        enqueue(interrupted["id"], workflow.resume)
    print(f"Model: {steps.MODEL}")
    app.run(port=8000)
