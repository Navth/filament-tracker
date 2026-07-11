# Security

## Model

- The app is designed for **localhost use only** (`127.0.0.1`). It has no
  authentication of its own — anyone who can reach the port can read your
  print history and trigger syncs. Do not expose it to the internet or an
  untrusted LAN without putting an authenticating reverse proxy in front.
- Your Bambu Cloud **login token is stored in plain text** in the local
  SQLite database (`tracker.db`). Treat that file like a password. It is
  git-ignored; never commit or share it.
- Your Bambu **password is never stored** — it is sent once, directly to
  Bambu's login endpoint over HTTPS.
- Never run with `FLASK_DEBUG=1` on a port reachable by other machines —
  the Werkzeug debugger allows arbitrary code execution.

## Reporting a vulnerability

Open a GitHub issue without exploit details and ask for a private contact,
or use GitHub's private vulnerability reporting if enabled on the repo.
