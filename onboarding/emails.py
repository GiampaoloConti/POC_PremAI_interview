"""Email drafter: the emails to the client.

Welcome and reminder emails are fixed templates and go out on their own. Anything else is a
draft that an employee approves. Everything leaves through the Gmail MCP server, which only
knows how to write to a client's registered address.
"""
from onboarding import config, db, tools

PORTAL_LINK = config.PUBLIC_URL + "/portal/{token}"

WELCOME = """Dear {first_name},

Welcome, and thank you for starting your onboarding with us.

This is where your file stands:
{checklist}

{next_step}

The onboarding team"""

STILL_MISSING = """You do not need to have everything at once. Add the missing documents whenever you have them, using your personal link:
{link}"""

NOTHING_MISSING = "We have all the documents we need. We will prepare your file and contact you if a detail is missing."

REMINDER = """Dear {first_name},

A quick reminder: to continue your onboarding we still need the following.
{checklist}

It takes a minute with your personal link:
{link}

The onboarding team"""


def checklist_text(checklist):
    lines = []
    for item in checklist:
        mark = "x" if item["received"] else " "
        lines.append(f"  [{mark}] {item['label']}" + (f" - {item['note']}" if item["note"] else ""))
    return "\n".join(lines)


def send_welcome(client, checklist):
    link = PORTAL_LINK.format(token=client["token"])
    complete = all(item["received"] for item in checklist)
    body = WELCOME.format(first_name=client["name"].split()[0], checklist=checklist_text(checklist),
                          next_step=NOTHING_MISSING if complete else STILL_MISSING.format(link=link))
    tools.call("Gmail", "send_email", client_id=client["id"], label="welcome",
               subject="Welcome: your onboarding has started", body=body)
    db.log(client["id"], "Email drafter", f"Welcome email sent to {client['email']} (fixed template)")


def send_reminder(client, checklist, last):
    missing = [item for item in checklist if not item["received"]]
    body = REMINDER.format(first_name=client["name"].split()[0], checklist=checklist_text(missing),
                           link=PORTAL_LINK.format(token=client["token"]))
    subject = "Last reminder: documents for your onboarding" if last else "Reminder: documents for your onboarding"
    tools.call("Gmail", "send_email", client_id=client["id"], label="reminder", subject=subject, body=body)
    db.log(client["id"], "Email drafter", f"Reminder sent to {client['email']} (fixed template)")


def save_draft(client, label, subject, body):
    """An email written by the agent. It stays a draft until an employee approves it."""
    tools.call("Gmail", "create_draft", client_id=client["id"], label=label, subject=subject, body=body)
    db.log(client["id"], "Email drafter", f"Drafted for approval: {subject}")
