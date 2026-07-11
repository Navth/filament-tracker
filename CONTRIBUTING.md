# Contributing

Thanks for your interest! This is a small hobby project — keep it simple.

## Setup

```bash
pip install -r requirements.txt
FLASK_DEBUG=1 python app.py    # auto-reload on save
```

## Guidelines

- Keep the stack minimal: Flask + SQLite + plain Jinja templates. No JS
  frameworks or build steps, please.
- One feature or fix per pull request.
- Test your change against a real Bambu Cloud account if it touches
  `bambu_cloud.py` — the API is unofficial and behavior matters more than
  docs.
- Never include real tokens, emails, serial numbers, or `tracker.db`
  contents in code, tests, issues, or screenshots.

## Reporting bugs

Use the bug report template. Include your printer model, whether you use
AMS Lite, and the full error/traceback — with any tokens or emails redacted.
