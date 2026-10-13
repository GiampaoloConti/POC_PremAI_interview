"""Checks of the verifier's rules.    python -m tests.test_verifier    (or: python -m pytest)"""
from onboarding.verifier import check, merge, same_value

DOCUMENT = """Modello 730 - Income tax return (summary)
Tax year: 2025
Gross annual income: EUR 96,000.00
Net annual income: EUR 63,840.00
"""


def candidate(value, source, problem=None):
    return {"value": value, "quote": f"x: {value}", "source": source, "problem": problem}


def test_an_answer_quoted_from_the_document_is_accepted():
    assert check("EUR 96,000.00", "Gross annual income: EUR 96,000.00", DOCUMENT) is None


def test_layout_and_case_do_not_matter():
    assert check("eur 96,000.00", "gross annual income:\n   EUR 96,000.00", DOCUMENT) is None


def test_an_invented_quote_is_flagged():
    assert check("Family inheritance", "Source of wealth: family inheritance", DOCUMENT) == \
        "The quoted text is not in the document"


def test_a_real_quote_with_a_wrong_value_is_flagged():
    assert check("EUR 69,000.00", "Gross annual income: EUR 96,000.00", DOCUMENT) == \
        "The answer is not in the quoted text"


def test_a_number_is_not_matched_inside_a_longer_number():
    assert check("6,000.00", "Gross annual income: EUR 96,000.00", DOCUMENT) is not None


def test_amounts_are_compared_as_numbers_and_text_as_words():
    assert same_value("EUR 96,000.00", "96000")
    assert same_value("Via Torino 18, Milano", "via torino 18  milano")
    assert not same_value("Via Torino 18, Milano", "Via Roma 18, Milano")


def test_no_document_answers_the_question():
    assert merge([])["flag"] == "not_found"


def test_documents_that_agree_give_one_verified_answer():
    answer = merge([candidate("EUR 96,000.00", "tax_return.pdf"), candidate("96000", "bank_statement.pdf")])
    assert (answer["flag"], answer["value"]) == ("ok", "EUR 96,000.00")


def test_documents_that_disagree_are_left_to_the_employee():
    answer = merge([candidate("EUR 12,000.00", "tax_return.pdf"), candidate("EUR 14,400.00", "bank_statement.pdf")])
    assert answer["flag"] == "conflict" and answer["value"] == "" and len(answer["options"]) == 2


def test_an_unverified_answer_stays_flagged():
    answer = merge([candidate("Family inheritance", "tax_return.pdf", "The quoted text is not in the document")])
    assert answer["flag"] == "unverified"


if __name__ == "__main__":
    tests = [check_ for name, check_ in list(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
    print(f"{len(tests)} checks passed")
