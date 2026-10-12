# Client onboarding agent: proof of concept

This is phase 0 of the design document (*Client Onboarding Agent: Design Document*): the full
onboarding flow on sample clients, to agree on the design before anything touches real data.

A client registers and sends documents in any order. The agent reads them, tells the client what
is missing, and drafts the bank's 30-question form with the source of every answer. The employee
reviews only the answers that need a person, and approves. Only the employee sends anything to a
bank.

## Run it

Python 3.10 or later.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open http://localhost:8000.

Use a virtual environment as above rather than a shared one such as Anaconda: an old `brotli`
package there breaks the HTTP library of the Anthropic SDK, and every model call fails with a
connection error.

It starts in **mock mode**: no key, no network, same result every time. To use a real model:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python app.py
```

The key can also live in a `.env` file (ignored by git) holding that one line without `export`;
load it with `set -a; source .env; set +a` before starting the app. The side menu always shows
which model is in use.

| Setting | Effect |
|---|---|
| `ANTHROPIC_API_KEY` | When set, the agent uses Claude. When not set, it uses the offline mock. |
| `ANTHROPIC_MODEL` | Which Claude model (default `claude-opus-5-5`). A smaller one, such as `claude-haiku-5-5`, answers faster. |
| `LLM_MODE=mock` | Forces the mock even when a key is set. |

## A five-minute demo

The home page has two doors: the client portal and the onboarding desk.

**The employee's side**

1. Open the **onboarding desk** and click **Add the demo clients**. Four clients go through the
   same path as a real one.
2. The status board shows who needs the employee and who is waiting on someone else. Giulia and
   Luca are ready for review. Marco sent one document out of three. Elena sent a tax return
   from 2023.
3. Open **Luca Romano**. The card at the top says what to do next. Below it, only the answers
   that need a person are shown, grouped by reason:
   - *The documents disagree*: the bank statement and the tax return give different addresses
     and rental incomes. Pick one.
   - *The agent could not prove these* (mock mode only): click the source to see that the quoted
     sentence is not in the document.
   - *Not in the documents*: the agent has drafted a message asking the client for them.

   The other answers are folded under *24 answers are filled and checked*. Open it and click a
   source to see the sentence highlighted in the document.
4. Open **Giulia Bianchi**. Fill what is missing and click **Approve the form**. Download the
   Excel file, click **I have sent it to the bank**, then try the sample bank replies: *Needs
   information* (the agent lists what the bank wants and drafts a message to the client),
   *Unclear* (the employee decides), *Accepted* (the employee confirms the onboarding).
5. In the side menu, click **Skip to the next day** a few times. Clients who still owe documents
   get a reminder after 1 and 3 days. On day 5 the employee is asked to call them.

**The client's side**

6. Open the **client portal** and sign in as **Marco Rossi**. The page shows the three documents
   and which ones are missing. Click **Demo: send the prepared tax_return.pdf**, or choose a
   file from `samples/marco_rossi/`. When the third document is in, the form is drafted and
   Marco moves to *Needs you* on the status board.
7. Register a **new client** with a name and an email. The page lists the three documents; send
   any of them, in any order, now or later.
8. Go back to the client portal and type the same email under **Already registered?**. The file
   opens where it was left.

**The numbers**

9. In a terminal, run `python evaluate.py`.

## How it maps to the design document

| In the design document | In the POC | Code |
|---|---|---|
| Upload portal, partial submissions, saved progress | Register, then one slot per document; come back with your email or your personal link | `app.py`, `templates/portal*.html` |
| Onboarding workflow: fixed steps, one status per client | The nine statuses and the order of the steps | `workflow.py` |
| Job queue | One background worker that runs the agent's steps | `app.py` (`enqueue`, `worker`) |
| Document reader | Text from PDFs, vision for scans, then type and year | `steps.read_document` |
| Form filler, fixed schema | One model call per document; anything off-schema is dropped | `steps.draft_form`, `bank_form.json` |
| Verifier: rules, not a model | Quote must be in the document, answer must be in the quote, documents must agree | `verifier.py` |
| Email drafter | Fixed templates for welcome and reminders; drafts for everything else | `emails.py`, `steps.draft_client_email` |
| Bank reply reader | Accepted, information requested or unclear, plus the list of requests | `steps.read_bank_reply` |
| Tools: MCP servers for Google Drive, Gmail and Excel | Three MCP servers with mock storage; the workflow calls them for every file, email and export | `mcp_drive.py`, `mcp_gmail.py`, `mcp_excel.py`, `tools.py` |
| Models | Offline mock or Claude today, Prem next | `llm_mock.py`, `llm_anthropic.py` |
| Status board | The onboarding desk | `templates/board.html` |
| Review screen | A client's page: next step, answers that need a person, sources | `templates/client.html` |
| Audit log | *Steps followed*, the activity log and the tool calls on each client's page | `db.log` |
| Evaluation | A test set and a metric per step | `evaluate.py`, `samples/expected.json` |

### Statuses

`Started` → `Awaiting documents` → `Documents complete` → `Form drafted` → `In review` →
`Sent to bank` → `Bank needs information` (back to `In review`) or `Bank accepted` → `Onboarded`

The screens show these as four stages: Documents, Review, Bank, Onboarded. The agent moves a
file up to `In review` on its own. Every step after that is an employee action. *Steps followed*
on a client's page lists the nine statuses with the time each was reached; it is read from the
audit log, so it is also the reviewers' checklist.

### Who may do what

| Action | In the POC |
|---|---|
| Welcome email and reminders | Automatic, from fixed templates |
| Questions to the client | Drafted by the agent, sent when the employee clicks *Approve and send* |
| Sending the form to a bank | The employee, outside the system. There is no code that contacts a bank. |
| Deciding what a bank reply means | The agent proposes; the employee can overrule, and decides when the agent is unsure |
| Marking a client as onboarded | The employee only |

### Edge cases you can try

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
| The agent is unavailable | Start with a wrong key: `ANTHROPIC_API_KEY=wrong python app.py`. Files wait with a *Let the agent try again* button and nothing is lost. |

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

They are real MCP servers: each one starts on its own with `python mcp_gmail.py` and answers any
MCP client. Only what is behind them is fake. In the app they run in the same process, and
`tools.py` connects to them with `Client(server)`. To use real servers, pass the client an
address instead; the workflow does not change.

Two things are worth pointing out:

- **Least privilege is in the tool list.** The Gmail tools take a client id, never a recipient,
  so there is nothing the agent could call to write to a bank or a stranger.
- **Every call is recorded.** *Tool calls through MCP* on a client's page lists them, without
  file contents or email bodies.

The workflow calls the tools itself, in a fixed order. The model never chooses a tool: it only
reads a document or writes a draft inside a step.

## The two model modes

Both modules expose the same five functions: `classify_document`, `extract_answers`,
`draft_client_email`, `read_bank_reply` and `transcribe`.

**`llm_mock.py`** uses keyword rules. It understands documents written as `Label: value` lines,
like the samples. It makes **one mistake on purpose**: it invents an answer to "Main source of
wealth" with a quote that is in no document. That is why every form in mock mode has one answer
under *The agent could not prove these*: it shows the verifier doing its job. Remove
`INVENTED_ANSWER` to turn this off.

**`llm_anthropic.py`** sends each job to Claude. All calls go through one function, `ask()`.

### Moving to Prem

Prem's confidential inference speaks the OpenAI chat format through a local proxy that encrypts
requests before they leave the machine. To switch: copy `llm_anthropic.py` to `llm_prem.py`,
replace `ask()`, and import the new module in `steps.py`. The prompts stay the same. A sketch,
not tested:

```python
from openai import OpenAI

client = OpenAI(api_key=os.environ["PREM_API_KEY"], base_url="http://127.0.0.1:8787/v1")

def ask(prompt, schema=None, attachment=None):
    if schema:
        prompt += "\n\nReply with JSON only, in this shape:\n" + json.dumps(schema)
    reply = client.chat.completions.create(
        model=MODEL_ID,
        messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
    )
    text = reply.choices[0].message.content
    return json.loads(text) if schema else text
```

The rest of the code does not rely on the provider to enforce the schema: `steps.py` checks
every reply itself.

## Evaluation

```bash
python evaluate.py
```

It runs the agent's steps on the test set and prints one line per metric of the design document:

| Metric | What it measures |
|---|---|
| Document recognition | Documents identified with the right type and year |
| Completeness check | Clients whose missing documents were detected |
| Form answers | Answers equal to the form the employee sent |
| Conflicts | Disagreements between documents that were flagged |
| Not-found answers | Answers absent from the documents that were left empty |
| Invented answers | Invented answers that the verifier flagged |
| Evidence | Answers whose quoted source is really in the document |
| Bank replies | Bank replies read correctly |

The test set is four synthetic clients (13 documents, 120 answers) and six bank replies.
`samples/make_samples.py` writes the documents and the expected form from one description of
each client, so the two cannot drift apart. In production the test set is past onboardings.

In mock mode the numbers mostly show that the harness works, because the mock's rules were
written for these documents. Its deliberate mistake shows up as 16/20 on *Not-found answers* and
4/4 on *Invented answers*: wrong four times, caught four times. With a key set, the same command
measures the real model in about 30 calls. Run it with two values of `ANTHROPIC_MODEL` to
compare a large and a small model, as the rollout plan suggests.

A run on `claude-opus-5-5` scored 100% on every metric in about a minute and a half: nothing
invented, both disagreements flagged, and the instruction hidden in Luca's portfolio statement
ignored. That shows the pipeline works on clean documents. It says nothing yet about real ones.

`python test_verifier.py` checks the verifier's rules on their own.

## What is simplified

| In the POC | In production |
|---|---|
| Mock MCP servers: a local folder, a database table, a local Excel file | Real MCP servers for Google Drive, Gmail and Sheets, with a service account limited to onboarding |
| The employee pastes the bank's reply and types the client's answers | The agent reads the onboarding mailbox |
| One worker thread in the web process | A queue and a worker, so that work survives a crash |
| A button moves the clock forward | A scheduled job runs the reminders once a day |
| No passwords. A client opens their file with their email address or their personal link; demo clients with one click. Anyone can open the onboarding desk. | A one-time sign-in link sent to the client's email, single sign-on for employees, and expiry on client links |
| SQLite | A managed database |
| Claude or a mock | Open-weight models on Prem's confidential inference, in the EU |
| Simple English documents with one layout | Real statements from many banks, in Italian, tested per layout |

## Project layout

```
app.py              web pages and the job queue
workflow.py         statuses and steps: what the client, the agent and the employee do
steps.py            the agent's steps, without database or web code
verifier.py         the rules that check every answer
tools.py            calls a tool on an MCP server and records the call
mcp_drive.py        mock Google Drive MCP server
mcp_gmail.py        mock Gmail MCP server
mcp_excel.py        mock Excel MCP server
llm_mock.py         offline stand-in for the model
llm_anthropic.py    the same jobs done by Claude
emails.py           email templates
db.py               database, audit log, demo clock
bank_form.json      the 30 questions (configuration, not code)
evaluate.py         evaluation on the test set
test_verifier.py    checks of the verifier
templates/, static/ the pages and their style
samples/            demo clients, expected results, bank replies
data/               created when the app runs: database and uploaded files
```
