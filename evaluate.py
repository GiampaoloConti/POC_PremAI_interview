"""Evaluation: run the agent's steps on the test set and compare with what a person would do.

    python evaluate.py

The test set here is the four sample clients (samples/expected.json) and six bank replies.
In production it is past onboardings: the client's documents and the form the employee sent.
Run it after every change to a prompt, a model or a rule, and compare the numbers.
"""
import json
from pathlib import Path

import steps
import verifier

SAMPLES = Path(__file__).parent / "samples"
test_set = json.loads((SAMPLES / "expected.json").read_text())
bank_replies = json.loads((SAMPLES / "bank_replies.json").read_text())
oldest_year = test_set["as_of_year"] - 1

METRICS = {
    "Document recognition": "documents identified with the right type and year",
    "Completeness check": "clients whose missing documents were detected",
    "Form answers": "answers equal to the employee's",
    "Conflicts": "disagreements between documents that were flagged",
    "Not-found answers": "answers absent from the documents that were left empty",
    "Invented answers": "invented answers that the verifier flagged",
    "Evidence": "answers whose quoted source is really in the document",
    "Bank replies": "bank replies read correctly",
}
results = {metric: [] for metric in METRICS}
mistakes = []


def score(metric, correct, detail):
    results[metric].append(correct)
    if not correct:
        mistakes.append(f"{metric}: {detail}")


for folder, expected in test_set["clients"].items():
    readings = {}
    for filename, truth in expected["documents"].items():
        reading = steps.read_document(filename, (SAMPLES / folder / filename).read_bytes(), oldest_year)
        readings[filename] = {**reading, "filename": filename}
        score("Document recognition", (reading["type"], reading["year"]) == (truth["type"], truth["year"]),
              f"{folder}/{filename} read as {reading['type']} {reading['year']}")

    first_upload = [readings[filename] for filename in expected["first_upload"]]
    missing = [item["type"] for item in steps.checklist(first_upload, oldest_year) if not item["received"]]
    score("Completeness check", missing == expected["missing_after_first_upload"], f"{folder}: found missing {missing}")

    usable = [reading for reading in readings.values() if reading["problem"] is None]
    for answer in steps.draft_form(usable):
        truth = expected["answers"][answer["id"]]
        where = f"{folder}/{answer['id']}: expected {truth!r}, got {answer['value']!r} ({answer['flag']})"
        if answer["id"] in expected["conflicts"]:
            score("Conflicts", answer["flag"] == "conflict", where)
        elif truth is None:
            score("Not-found answers", answer["flag"] == "not_found", where)
            if answer["flag"] != "not_found":       # the agent invented a value: did the verifier notice?
                score("Invented answers", answer["flag"] == "unverified", where)
        else:
            score("Form answers", answer["flag"] != "conflict" and verifier.same_value(answer["value"], truth), where)
        if answer["flag"] in ("ok", "unverified"):
            score("Evidence", answer["flag"] == "ok", where)

for reply in bank_replies:
    outcome = steps.read_bank_reply(reply["text"])["outcome"]
    score("Bank replies", outcome == reply["outcome"], f"expected {reply['outcome']}, got {outcome}: {reply['text'][:60]!r}")


print(f"\nModel: {steps.MODEL}")
print(f"Test set: {len(test_set['clients'])} clients, {len(bank_replies)} bank replies\n")
for metric, description in METRICS.items():
    outcomes = results[metric]
    share = f"{sum(outcomes)}/{len(outcomes)}" if outcomes else "none"
    percent = f"{100 * sum(outcomes) / len(outcomes):.0f}%" if outcomes else ""
    print(f"{metric:<22}{description:<56}{share:>8}{percent:>6}")
if mistakes:
    print("\nWhat went wrong:")
    for mistake in mistakes:
        print("  " + mistake)
