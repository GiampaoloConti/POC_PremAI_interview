"""Offline stand-in for the language model, so the POC runs without a key or a network.

It does the same jobs as llm_anthropic.py with simple rules. The rules only understand
documents written as "Label: value" lines, like the samples; a real model reads any layout.
"""
import re

MODEL = "offline mock"

DOCUMENT_KEYWORDS = {
    "bank_statement": "bank statement",
    "tax_return": "tax return",
    "portfolio_statement": "portfolio statement",
}

# The labels under which each form answer is written in a document.
LABELS = {
    "full_name": ["Account holder", "Taxpayer", "Client"],
    "tax_id": ["Tax identification number"],
    "date_of_birth": ["Date of birth"],
    "address": ["Residential address"],
    "tax_residence": ["Country of tax residence"],
    "marital_status": ["Marital status"],
    "dependants": ["Number of dependants"],
    "occupation": ["Occupation"],
    "employer": ["Employer"],
    "gross_income": ["Gross annual income"],
    "net_income": ["Net annual income"],
    "rental_income": ["Rental income", "Rental income received"],
    "capital_gains": ["Capital gains"],
    "tax_paid": ["Total income tax paid"],
    "bank_name": ["Bank"],
    "iban": ["IBAN"],
    "closing_balance": ["Closing balance"],
    "total_credits": ["Total incoming payments"],
    "total_debits": ["Total outgoing payments"],
    "physical_assets_spend": ["Purchases of physical assets"],
    "loan_balance": ["Outstanding loans and mortgages"],
    "custodian": ["Custodian"],
    "portfolio_value": ["Total portfolio value"],
    "cash_in_portfolio": ["Cash held in the portfolio"],
    "unrealised_gains": ["Unrealised gains"],
    "investment_income": ["Dividends and interest received"],
}

# The mock makes one mistake on purpose: it invents this answer, with a quote that is in no
# document. It is here so that the demo and the evaluation show the verifier catching it.
INVENTED_ANSWER = {"id": "source_of_wealth", "value": "Family inheritance",
                   "quote": "Source of wealth: family inheritance"}

BANK_ASKS = ["please provide", "please send", "we need", "we require", "until we receive", "before we can"]
BANK_ACCEPTS = ["accepted", "approved", "pleased to confirm"]


def classify_document(text):
    lower = text.lower()
    doc_type = next((t for t, keyword in DOCUMENT_KEYWORDS.items() if keyword in lower), "other")
    year = re.search(r"\b20\d\d\b", text)
    return {"type": doc_type, "year": int(year.group()) if year else None}


def extract_answers(text, questions):
    answers = []
    for question in questions:
        for label in LABELS.get(question["id"], []):
            # A line "Label: value", with an optional "(note)" after the label.
            line = re.search(rf"^\s*({re.escape(label)}(?: \([^)]*\))?\s*:\s*(.+?))\s*$", text, re.I | re.M)
            if line:
                answers.append({"id": question["id"], "value": line.group(2), "quote": line.group(1)})
                break
    return answers + [INVENTED_ANSWER]


def draft_client_email(client_name, items, reason):
    numbered = "\n".join(f"{n}. {item}" for n, item in enumerate(items, 1))
    return (f"Dear {client_name.split()[0]},\n\n{reason} Could you reply to this email with the following?\n\n"
            f"{numbered}\n\nThank you,\nThe onboarding team")


def read_bank_reply(text):
    lower = text.lower()
    if any(phrase in lower for phrase in BANK_ASKS):
        listed = re.findall(r"^\s*(?:-|\d+\.)\s*(.+)$", text, re.M)      # bullet or numbered lines
        return {"outcome": "information_requested", "requests": listed or [text.strip()]}
    if any(phrase in lower for phrase in BANK_ACCEPTS):
        return {"outcome": "accepted", "requests": []}
    return {"outcome": "unclear", "requests": []}


def transcribe(filename, content):
    return ""       # the mock cannot read scans or photos; a vision model can
