"""Settings: where the files live, what the environment asks for, and how the log is written.

Settings are read from a .env file at the top of the project (see .env.example) or from
environment variables. An environment variable wins over the file.
"""
import logging
import os
import threading
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA = ROOT / "data"            # the database and the clients' files, created when the app runs
LOGS = ROOT / "logs"            # the log file, created when the app runs
SAMPLES = ROOT / "samples"      # the demo clients and the test set

if (ROOT / ".env").exists():
    for line in (ROOT / ".env").read_text().splitlines():
        name, equals, value = line.partition("=")
        if equals and value.strip() and not name.lstrip().startswith("#"):
            os.environ.setdefault(name.strip(), value.strip().strip("\"'"))

# Claude when a key is set, the offline mock otherwise. LLM_MODE=mock forces the mock.
USE_MOCK = not os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("LLM_MODE") == "mock"
MODEL_ID = os.environ.get("ANTHROPIC_MODEL", "claude-opus-5-5")
PORT = os.environ.get("PORT")       # set by a hosting service; not set on your own machine
PUBLIC_URL = os.environ.get("PUBLIC_URL", "http://localhost:8000")      # used for the links in the emails


# ------------------------------------------------------------------- the log

current = threading.local()     # current.client_id: the file this thread is working on


class ClientNumber(logging.Filter):
    """Puts the client's number on every log line, so one file can be followed with a search."""

    def filter(self, record):
        if not hasattr(record, "client"):
            record.client = getattr(current, "client_id", "-")
        return True


def start_logging():
    """Write the log to the terminal and to logs/onboarding.log."""
    LOGS.mkdir(exist_ok=True)
    handlers = [logging.StreamHandler(), logging.FileHandler(LOGS / "onboarding.log")]
    for handler in handlers:
        handler.addFilter(ClientNumber())
    logging.basicConfig(handlers=handlers, level=logging.WARNING, force=True, datefmt="%Y-%m-%d %H:%M:%S",
                        format="%(asctime)s %(levelname)-7s client=%(client)-3s %(name)s: %(message)s")
    logging.getLogger("onboarding").setLevel(logging.INFO)      # our own events in full
    logging.getLogger("werkzeug").setLevel(logging.WARNING)     # no line per page view: links hold tokens
