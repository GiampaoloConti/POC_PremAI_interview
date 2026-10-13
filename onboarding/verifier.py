"""Verifier: rules, not a model.

The form filler must quote the sentence each answer comes from. The checks here are plain
code, so no wording in a document or in a model reply can talk them into accepting an answer.
"""
import re

CURRENCY = re.compile(r"euro|eur|€|\s|,")


def words(text):
    """Lower case, without punctuation or line breaks: 'EUR 84,000.00' -> 'eur 84 000 00'."""
    return re.sub(r"\W+", " ", text.casefold()).strip()


def contains(text, part):
    """True if `part` appears in `text` word for word, ignoring case, punctuation and layout."""
    return bool(words(part)) and f" {words(part)} " in f" {words(text)} "


def check(value, quote, document_text):
    """What is wrong with an answer, or None when the document backs it."""
    if not contains(document_text, quote):
        return "The quoted text is not in the document"
    if not contains(quote, value):
        return "The answer is not in the quoted text"
    return None


def as_amount(value):
    """'EUR 84,000.00' -> 84000.0, or None when the value is not an amount."""
    try:
        return float(CURRENCY.sub("", value.casefold()))
    except ValueError:
        return None


def same_value(a, b):
    """Do two answers say the same thing? Amounts are compared as numbers, the rest as words."""
    x, y = as_amount(a), as_amount(b)
    if x is not None and y is not None:
        return abs(x - y) < 0.005
    return words(a) == words(b)


def merge(candidates):
    """Turn what the documents say about one question into one form answer.

    candidates = [{"value", "quote", "source", "problem"}], one per document that answers it.
    """
    empty = {"value": "", "source": "", "quote": "", "note": "", "options": []}
    if not candidates:
        return {**empty, "flag": "not_found"}

    distinct = []
    for candidate in sorted(candidates, key=lambda c: c["problem"] is not None):   # verified first
        if not any(same_value(candidate["value"], other["value"]) for other in distinct):
            distinct.append(candidate)

    if len(distinct) > 1:       # documents disagree: the employee decides
        return {**empty, "flag": "conflict", "options": distinct}

    best = distinct[0]
    return {**empty, "flag": "unverified" if best["problem"] else "ok", "value": best["value"],
            "source": best["source"], "quote": best["quote"], "note": best["problem"] or ""}
