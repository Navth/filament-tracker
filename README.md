# 🧵 Filament Tracker for Bambu Lab

A small, self-hosted web app that tracks how much filament each of your
spools has used, by syncing your print history (estimated grams per print)
from Bambu Cloud. Built for the A1 mini, works with any Bambu Cloud printer.

No database server, no accounts, no telemetry — one Flask app and a local
SQLite file.

## Features

- **Automatic tracking** — pulls your print jobs from Bambu Cloud; each job
  carries the slicer's estimated filament weight in grams.
- **Spool management** — when you change a spool, the old one is archived
  with its totals and you enter the new spool's quantity, material, color,
  and brand. The counter resets automatically.
- **AMS Lite support** — configure 1 slot (single external spool) up to
  4 slots; prints with AMS data are split per slot.
- **Corrections** — weigh a spool and enter the real remaining grams;
  toggle failed prints off, or reassign a print to a different spool.
- **Local & private** — everything lives in `tracker.db` on your machine.
  Your Bambu password is never stored, only the login token.

## Quick start

```bash
git clone https://github.com/Navth/filament-tracker.git
cd filament-tracker
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000, then:

1. **Settings** → log in with your Bambu account. Bambu emails you a
   6-digit verification code — enter it when prompted. Pick your slot
   count and (optionally) a specific printer.
2. **Dashboard** → *Load a spool* and enter its details.
3. Hit **⟳ Sync prints** whenever you like.

## How the math works

```
remaining = spool quantity − Σ(counted prints) − Σ(corrections)
```

- Prints are only charged to a spool if they **started after the spool was
  loaded**. Older history is imported as *unassigned* so it never deducts
  from the wrong spool.
- Jobs still printing are skipped and imported on the next sync after they
  finish.
- Grams are *slicer estimates* — purges and failures cause drift. Use
  **Correct** on the Spools page after weighing a spool. (Empty spool
  weights: ~250 g cardboard, ~130–250 g plastic.)
- Times are stored in UTC and displayed in your local timezone.

## Important disclaimers

- **Unofficial API.** This project uses Bambu Lab's cloud API, which is
  undocumented and may change or break at any time. It is not affiliated
  with or endorsed by Bambu Lab.
- **Login token.** Your cloud token (valid roughly 1–3 months) is stored in
  the local `tracker.db`. Don't share that file, and never commit it —
  it's in `.gitignore`.
- **Local use only.** The app binds to `127.0.0.1` and has no
  authentication of its own. Don't expose it to the internet as-is.

## Project layout

```
app.py              Flask app: routes, SQLite schema, tracking logic
bambu_cloud.py      Minimal Bambu Cloud API client (login + 2FA, tasks)
templates/          Jinja2 templates (no JS frameworks, no build step)
requirements.txt    flask, requests
```

## Roadmap ideas

- Pull live printer status over local MQTT (LAN mode)
- Per-material / per-month usage stats and charts
- Cost tracking (price per spool → cost per print)
- Low-filament warnings before starting a print

Contributions welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE)
