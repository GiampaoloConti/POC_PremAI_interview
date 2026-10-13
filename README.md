# Client onboarding agent: proof of concept

This is phase 0 of the design document ([docs/design_document.pdf](docs/design_document.pdf)):
the full onboarding flow on sample clients, to agree on the design before anything touches real
data.

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

## Settings

It starts in **mock mode**: no key, no network, same result every time. To use a real model,
copy the example settings and put your key in the copy:

```bash
cp .env.example .env
```

The app reads `.env` when it starts. The file is ignored by git. The side menu always shows
which model is in use.

| Setting | Effect |
|---|---|
| `ANTHROPIC_API_KEY` | When set, the agent uses Claude. When empty, it uses the offline mock. |
| `ANTHROPIC_MODEL` | Which Claude model (default `claude-opus-5-5`). A smaller one, such as `claude-haiku-5-5`, answers faster. |
| `LLM_MODE=mock` | Forces the mock even when a key is set. |
| `PUBLIC_URL` | The address of the hosted app, used for the links in the emails (default `http://localhost:8000`). |
| `PORT` | Set by a hosting service. The app then listens on that port and accepts visitors from outside. |

A setting given on the command line wins over the file, so `LLM_MODE=mock python app.py` runs
the mock once without editing anything.

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

**The trace and the numbers**

9. Open `logs/onboarding.log`, or look at the terminal: every step above left a line. To read
   the story of one client, run `grep "client=1 " logs/onboarding.log`.
10. In a terminal, run `python evaluate.py`.

## Documentation

| Document | What it covers |
|---|---|
| [docs/design_document.pdf](docs/design_document.pdf) | The design this POC supports |
| [docs/architecture.md](docs/architecture.md) | How the POC maps to the design, the statuses, who may do what, the MCP servers, what is simplified |
| [docs/logging.md](docs/logging.md) | The audit trail and the log: what is recorded, and how to follow one client |
| [docs/models.md](docs/models.md) | The mock and the real model, and how to move to Prem |
| [docs/evaluation.md](docs/evaluation.md) | The test set, the metrics and the results |
| [docs/hosting.md](docs/hosting.md) | Putting the app online |

## Project layout

```
app.py                  starts the app
evaluate.py             runs the evaluation on the test set
requirements.txt        the Python packages needed
.env.example            the settings, to copy to .env
onboarding/             the application
    config.py           settings, folders and the log
    web.py              web pages and the job queue
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
    db.py               database, audit trail, demo clock
    bank_form.json      the 30 questions (configuration, not code)
    templates/, static/ the pages and their style
tests/                  checks of the verifier
samples/                demo clients, expected results, bank replies
docs/                   the design document and the notes on this POC
data/                   created when the app runs: database and uploaded files
logs/                   created when the app runs: the log file
```
