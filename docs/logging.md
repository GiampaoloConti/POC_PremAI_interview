# Traceability: the audit trail and the log

Everything that happens to a client's file is recorded twice, for two kinds of reader.

| | Audit trail | Log |
|---|---|---|
| Where | The `audit` table of the database, shown on each client's page | The terminal and `logs/onboarding.log` |
| For whom | The employee and whoever reviews the process | Whoever runs or debugs the system |
| What it holds | Every business event: who did what on this file, and when | Every audit entry, plus the technical events around it |

## What is recorded

| Event | Audit trail | Log | Written by |
|---|---|---|---|
| The client registers, signs in or uploads a file | yes | yes | `db.log` |
| A status change, with who caused it | yes | yes | `workflow.set_status` |
| What each agent step concluded, with the model and prompt version | yes | yes | `workflow.advance`, `workflow.read_bank_reply` |
| What the verifier decided, and which answers it left to a person | counts | counts and question ids | `workflow.advance` |
| Every MCP tool call: server, tool and short arguments | yes | yes | `tools.call` |
| Every email sent or drafted | yes | yes | `emails.py` |
| Every employee action: an answer changed (old and new value), approval, export, bank decision | yes | yes | `workflow.py` |
| Every action in the browser, even one that changed nothing | no | yes | `web.log_action` |
| A job of the agent queued, started and finished, with its duration | no | yes | `web.enqueue`, `web.worker` |
| Every call to the real model: job, provider's request id, tokens in and out, duration | no | yes | `llm_anthropic.ask` |
| A failure, with the full error trace | one line | yes | `web.worker` |
| The demo clock moved, the demo was reset | no | yes | `web.py`, `db.reset` |

`db.log()` is the single door to the audit trail, and it writes each entry to the log as well.
That is why the log is always a superset of the audit trail.

## Reading the log

One event per line: time, level, client number, the part of the code, the message.

```
2026-10-13 10:02:14 INFO    client=2   onboarding.audit: Client: Uploaded tax_return.pdf
2026-10-13 10:02:14 INFO    client=2   onboarding.web: advance queued
2026-10-13 10:02:14 INFO    client=2   onboarding.web: advance started
2026-10-13 10:02:14 INFO    client=-   onboarding.web: POST /portal/<token> -> 302
2026-10-13 10:02:14 INFO    client=2   onboarding.audit: Google Drive (MCP): download_file(client_id=2, filename='tax_return.pdf')
2026-10-13 10:02:16 INFO    client=2   onboarding.llm_anthropic: classify_document: request req_01..., 812 tokens in, 21 tokens out, 1.9 s, end_turn (claude-opus-5-5, prompts v1)
2026-10-13 10:02:16 INFO    client=2   onboarding.audit: Document reader: tax_return.pdf: Tax return, 2025 (model: claude-opus-5-5, prompts v1)
2026-10-13 10:02:16 INFO    client=2   onboarding.web: advance finished in 2.1 s
```

Every line about a client carries the client's number, so one file can be followed from
registration to onboarding with a search. The one exception is the browser action of a client
in the portal: its address holds a token, not a number, so it shows `client=-`, and the audit
line next to it names the client.

```bash
grep "client=2 " logs/onboarding.log          # the whole story of client 2
grep "onboarding.audit" logs/onboarding.log   # business events only
grep "llm_anthropic" logs/onboarding.log      # every model call, with tokens and duration
grep -A 30 "ERROR" logs/onboarding.log        # failures, with the error trace
```

The request id on a model call is the provider's own reference: with it, a single call can be
found again on the provider's side.

Libraries write to the same log only when they warn or fail.

## What is never written to the log

- The text of a document, a prompt or a model's reply.
- The body of an email or the content of a file.
- The model key.
- The token of a client's personal link. Page views are not logged for that reason; actions
  are, with the token replaced by `<token>`.

Audit entries do hold names, email addresses, file names and, when an employee corrects an
answer, the old and the new value. The log therefore needs the same protection as the database.

## In the code

| Piece | Where |
|---|---|
| Format, terminal and file output, the client number on each line | `config.start_logging`, `config.ClientNumber` |
| Audit entry and its log line | `db.log` |
| Jobs and failures | `web.worker` |
| Browser actions | `web.log_action` |
| Model calls | `llm_anthropic.ask` |

## What is simplified

- The log is one file that grows. In production it is rotated and sent to the fund's central
  log store.
- There is no login, so the audit trail says "Employee" and not who. With single sign-on it
  holds the person's name, and page views can be logged too.
- **Start again from empty** empties the audit trail with everything else. The log file is kept and
  records the reset.
