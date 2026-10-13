# Architecture

How the POC maps to the design document ([design_document.pdf](design_document.pdf)), and where
it is simpler than the real system.

## How it maps to the design document

The code is in `onboarding/`, unless a path says otherwise.

| In the design document | In the POC | Code |
|---|---|---|
| Upload portal, partial submissions, saved progress | Register, then one slot per document; come back with your email or your personal link | `web.py`, `templates/portal*.html` |
| Onboarding workflow: fixed steps, one status per client | The nine statuses and the order of the steps | `workflow.py` |
| Job queue | One background worker that runs the agent's steps | `web.py` (`enqueue`, `worker`) |
| Document reader | Text from PDFs, vision for scans, then type and year | `steps.read_document` |
| Form filler, fixed schema | One model call per document; anything off-schema is dropped | `steps.draft_form`, `bank_form.json` |
| Verifier: rules, not a model | Quote must be in the document, answer must be in the quote, documents must agree | `verifier.py` |
| Email drafter | Fixed templates for welcome and reminders; drafts for everything else | `emails.py`, `steps.draft_client_email` |
| Bank reply reader | Accepted, information requested or unclear, plus the list of requests | `steps.read_bank_reply` |
| Tools: MCP servers for Google Drive, Gmail and Excel | Three MCP servers with mock storage; the workflow calls them for every file, email and export | `mcp_drive.py`, `mcp_gmail.py`, `mcp_excel.py`, `tools.py` |
| Models | Offline mock or Claude today, Prem next | `llm_mock.py`, `llm_anthropic.py` |
| Status board | The onboarding desk | `templates/board.html` |
| Review screen | A client's page: next step, answers that need a person, sources | `templates/client.html` |
| Audit log | *Steps followed*, the activity log and the tool calls on each client's page, and the log file. See [logging.md](logging.md). | `db.log`, `config.start_logging` |
| Evaluation | A test set and a metric per step. See [evaluation.md](evaluation.md). | `evaluate.py` and `samples/expected.json` at the top of the project |

## Statuses

`Started` → `Awaiting documents` → `Documents complete` → `Form drafted` → `In review` →
`Sent to bank` → `Bank needs information` (back to `In review`) or `Bank accepted` → `Onboarded`

The screens show these as four stages: Documents, Review, Bank, Onboarded. The agent moves a
file up to `In review` on its own. Every step after that is an employee action. *Steps followed*
on a client's page lists the nine statuses with the time each was reached; it is read from the
audit trail, so it is also the reviewers' checklist.

## Who may do what

| Action | In the POC |
|---|---|
| Welcome email and reminders | Automatic, from fixed templates |
| Questions to the client | Drafted by the agent, sent when the employee clicks *Approve and send* |
| Sending the form to a bank | The employee, outside the system. There is no code that contacts a bank. |
| Deciding what a bank reply means | The agent proposes; the employee can overrule, and decides when the agent is unsure |
| Marking a client as onboarded | The employee only |

## Edge cases you can try

| Case in the design document | How to see it |
|---|---|
| A document never arrives | Marco: *Skip to the next day* five times |
| An answer isn't in the documents | The *Not in the documents* group and the drafted message |
| Two documents disagree | Luca: address and rental income |
| Wrong or outdated document | Elena: a 2023 tax return. Sign in as Elena and send the prepared 2025 one. |
| Poor scan or photo | Upload `samples/extras/tax_return_photo.png` in a document slot. A real model reads it with vision. The mock cannot read images, so the client is asked for a better copy. |
| The client sends more documents later | Any client's portal page, at any time |
| A document contains text that looks like instructions | Luca's portfolio statement ends with one. It is read as data. |
| Ambiguous bank reply | The *Unclear* sample reply |
| The agent is unavailable | Start with a wrong key: `ANTHROPIC_API_KEY=wrong python app.py` (with no `LLM_MODE=mock` in `.env`). Files wait with a *Let the agent try again* button, nothing is lost, and the log holds the full error. |

## How the agent is kept honest

The risk the design document puts first is a wrong answer reaching a bank. Four layers sit
between the model and the bank:

1. **Every answer must quote its source.** The form filler returns a value and the sentence it
   comes from, or nothing.
2. **The quote is checked by code** (`verifier.py`). The sentence must be in the document and the
   value must be in the sentence. If two documents give different values, the answer is left
   empty and both are shown.
3. **The employee approves every form.** A form cannot be approved while an answer is empty or
   still flagged.
4. **The agent has no tool that reaches a bank.** The Gmail server only writes to a client's
   registered address, and only a fixed template or a message the employee approved.

Documents are untrusted input. Their text is passed to the model as data inside tags, the reply
is constrained to a schema, and the code drops anything that is not an answer to a real question.

## The MCP servers

The workflow never touches a file, an email or a spreadsheet directly. It calls a tool on one of
three MCP servers through `tools.call()`:

| Server | Tools | Mock storage |
|---|---|---|
| `mcp_drive.py` (Google Drive) | `upload_file`, `download_file` | A folder per client under `data/files/` |
| `mcp_gmail.py` (Gmail) | `send_email`, `create_draft`, `send_draft`, `delete_drafts` | The `emails` table |
| `mcp_excel.py` (Excel) | `create_workbook` | A real `.xlsx` file in the client's folder |

They are real MCP servers: each one starts on its own with `python -m onboarding.mcp_gmail` and
answers any MCP client. Only what is behind them is fake. In the app they run in the same
process, and `tools.py` connects to them with `Client(server)`. To use real servers, pass the
client an address instead; the workflow does not change.

Two things are worth pointing out:

- **Least privilege is in the tool list.** The Gmail tools take a client id, never a recipient,
  so there is nothing the agent could call to write to a bank or a stranger.
- **Every call is recorded.** *Tool calls through MCP* on a client's page lists them, without
  file contents or email bodies. The same lines are in the log file.

The workflow calls the tools itself, in a fixed order. The model never chooses a tool: it only
reads a document or writes a draft inside a step.

## What is simplified

| In the POC | In production |
|---|---|
| Mock MCP servers: a local folder, a database table, a local Excel file | Real MCP servers for Google Drive, Gmail and Sheets, with a service account limited to onboarding |
| The employee pastes the bank's reply and types the client's answers | The agent reads the onboarding mailbox |
| One worker thread in the web process | A queue and a worker, so that work survives a crash |
| A button moves the clock forward | A scheduled job runs the reminders once a day |
| No passwords. A client opens their file with their email address or their personal link; demo clients with one click. Anyone can open the onboarding desk. | A one-time sign-in link sent to the client's email, single sign-on for employees, and expiry on client links |
| The audit trail says "Employee"; the log is one file on the machine | The employee's name from single sign-on; logs sent to the fund's central log store |
| SQLite | A managed database |
| Claude or a mock | Open-weight models on Prem's confidential inference, in the EU |
| Simple English documents with one layout | Real statements from many banks, in Italian, tested per layout |
