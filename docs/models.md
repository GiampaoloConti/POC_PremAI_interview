# The two model modes

`onboarding/steps.py` picks one of two modules when the app starts: the offline mock, or Claude
when a key is set (see *Settings* in the [README](../README.md)). Both expose the same five
functions: `classify_document`, `extract_answers`, `draft_client_email`, `read_bank_reply` and
`transcribe`.

**`llm_mock.py`** uses keyword rules. It understands documents written as `Label: value` lines,
like the samples. It makes **one mistake on purpose**: it invents an answer to "Main source of
wealth" with a quote that is in no document. That is why every form in mock mode has one answer
under *The agent could not prove these*: it shows the verifier doing its job. Remove
`INVENTED_ANSWER` to turn this off.

**`llm_anthropic.py`** sends each job to Claude. All calls go through one function, `ask()`,
which also writes one log line per call (see [logging.md](logging.md)).

## Moving to Prem

Prem's confidential inference speaks the OpenAI chat format through a local proxy that encrypts
requests before they leave the machine. To switch: copy `llm_anthropic.py` to `llm_prem.py`,
replace `ask()`, and import the new module in `steps.py`. The prompts stay the same. A sketch,
not tested:

```python
from openai import OpenAI

client = OpenAI(api_key=os.environ["PREM_API_KEY"], base_url="http://127.0.0.1:8787/v1")

def ask(job, prompt, schema=None, attachment=None):
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
