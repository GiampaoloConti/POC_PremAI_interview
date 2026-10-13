# Putting it online

The app runs as it is on any service that hosts a Python web app from a GitHub repository, for
example a free web service on Render:

- Build command: `pip install -r requirements.txt`
- Start command: `PUBLIC_URL=$RENDER_EXTERNAL_URL python app.py`
- Environment: `PYTHON_VERSION` = `3.12.8`, and `ANTHROPIC_API_KEY` for the real model

The hosting service sets `PORT`; the app then listens on it and accepts visitors from outside.
`PUBLIC_URL` is the address used for the links in the emails.

Things to know:

- **The key** is typed into the hosting service's settings and never goes into the repository.
- **Anyone with the address can use the app, and so the key.** Use a key made for the demo, with
  a spending limit, and delete it afterwards. Without a key the hosted app runs on the mock.
- **A free service goes to sleep when nobody visits**, and its disk is emptied when it does, so
  the demo starts from an empty status board.
- **The log** is also written to the terminal, so it appears in the hosting service's log viewer.
