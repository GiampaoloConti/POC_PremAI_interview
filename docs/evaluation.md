# Evaluation

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
measures the real model in about 30 calls, each written to the log with its tokens and duration.
Run it with two values of `ANTHROPIC_MODEL` to compare a large and a small model, as the rollout
plan suggests.

A run on `claude-opus-5-5` scored 100% on every metric in about a minute and a half: nothing
invented, both disagreements flagged, and the instruction hidden in Luca's portfolio statement
ignored. That shows the pipeline works on clean documents. It says nothing yet about real ones.

## Checks of the verifier

```bash
python -m tests.test_verifier
```

It checks the verifier's rules on their own, without a model. `python -m pytest` runs the same
checks if pytest is installed.
