"""The agent's steps: document reader, completeness check, form filler, email drafter, bank reply reader.

Each step is a plain function (input in, result out, no database), so the workflow and the
evaluation run exactly the same code. A model is used only where the input varies; whatever
it returns is checked by ordinary code before anything else relies on it.
"""
import io
import json
from pathlib import Path

from pypdf import PdfReader

from onboarding import config, verifier

if config.USE_MOCK:
    from onboarding import llm_mock as llm
else:
    from onboarding import llm_anthropic as llm

MODEL = llm.MODEL

# The bank form is configuration, not code: a new version of the form is a new JSON file.
FORM = json.loads(Path(__file__).with_name("bank_form.json").read_text())
QUESTIONS = FORM["questions"]

REQUIRED_DOCUMENTS = {
    "bank_statement": "Bank statement",
    "tax_return": "Tax return",
    "portfolio_statement": "Investment portfolio statement",
}


def extract_text(filename, content):
    """The text of a file. Digital PDFs are read directly; scans and photos go to the vision model."""
    kind = Path(filename).suffix.lower()
    if kind == ".txt":
        return content.decode(errors="replace")
    if kind == ".pdf":
        try:
            text = "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(content)).pages)
        except Exception:       # damaged or password-protected file
            return ""
        if text.strip():
            return text
    return llm.transcribe(filename, content)


def read_document(filename, content, oldest_year):
    """Document reader: extract the text, then identify the document type and year."""
    text = extract_text(filename, content)
    if len(text.strip()) < 20:
        return {"text": "", "type": "other", "year": None, "problem": "unreadable"}

    found = llm.classify_document(text)
    doc_type = found.get("type") if found.get("type") in REQUIRED_DOCUMENTS else "other"
    year = found.get("year") if isinstance(found.get("year"), int) else None

    problem = None
    if doc_type == "other":
        problem = "not_needed"
    elif year and year < oldest_year:
        problem = "outdated"
    return {"text": text, "type": doc_type, "year": year, "problem": problem}


def describe(document):
    """A document in a few words, for the screens and the audit log."""
    if document["problem"] == "unreadable":
        return "Could not be read"
    if document["problem"] == "not_needed":
        return "Not one of the documents we need"
    label = REQUIRED_DOCUMENTS[document["type"]]
    if document["year"]:
        label += f", {document['year']}"
    return label + (" (too old)" if document["problem"] == "outdated" else "")


def checklist(documents, oldest_year):
    """Completeness check: for each required document, do we have a usable one?"""
    items = []
    for doc_type, label in REQUIRED_DOCUMENTS.items():
        same_type = [d for d in documents if d["type"] == doc_type]
        received = any(d["problem"] is None for d in same_type)
        note = ""
        if not received:
            note = "Not received yet"
            if same_type:       # we have one, but it is too old
                note = f"The one we received is from {same_type[-1]['year']}; we need {oldest_year} or later"
        items.append({"type": doc_type, "label": label, "received": received, "note": note})
    return items


def draft_form(documents):
    """Form filler: ask the model what each document says, verify every answer, merge per question.

    Returns one answer per question of the form, each flagged ok, unverified, conflict or not_found.
    """
    candidates = {question["id"]: [] for question in QUESTIONS}
    for document in documents:
        for answer in llm.extract_answers(document["text"], QUESTIONS):
            # Fixed schema: anything that is not {id of a real question, value, quote} is dropped.
            if not isinstance(answer, dict) or answer.get("id") not in candidates:
                continue
            value, quote = answer.get("value"), answer.get("quote")
            if not isinstance(value, str) or not isinstance(quote, str) or not value.strip():
                continue
            candidates[answer["id"]].append({
                "value": value.strip(),
                "quote": quote.strip(),
                "source": document["filename"],
                "problem": verifier.check(value, quote, document["text"]),
            })
    return [{"id": question_id, **verifier.merge(found)} for question_id, found in candidates.items()]


def draft_client_email(client_name, items, reason):
    """Email drafter: a message asking the client for specific items. Always approved by an employee."""
    return llm.draft_client_email(client_name, items, reason).strip()


def read_bank_reply(text):
    """Bank reply reader: accepted, information requested or unclear, plus what the bank asks for."""
    reading = llm.read_bank_reply(text)
    requests = [r.strip() for r in reading.get("requests", []) if isinstance(r, str) and r.strip()]
    outcome = reading.get("outcome")
    if outcome not in ("accepted", "information_requested"):
        outcome = "unclear"
    if outcome == "accepted" and requests:      # contradictory reading: let the employee decide
        outcome = "unclear"
    return {"outcome": outcome, "requests": requests}
