"""Filament Tracker — local web app for Bambu Lab A1 mini.

Tracks filament usage per spool by syncing print history (estimated grams
per print) from Bambu Cloud. When you change a spool, the old one is
archived and you enter the new spool's weight, material, color, and brand.
Supports 1 external spool or up to 4 AMS Lite slots.

Run:  python app.py   then open http://127.0.0.1:5000
"""

import json
import os
import sqlite3
from datetime import datetime, timezone

from flask import (Flask, flash, g, redirect, render_template, request,
                   url_for)

from bambu_cloud import BambuCloud, BambuCloudError, NeedsVerifyCode

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(APP_DIR, "tracker.db")

app = Flask(__name__)
app.secret_key = os.urandom(24)


# ---------------------------------------------------------------- database

SCHEMA = """
CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS spools (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slot INTEGER NOT NULL DEFAULT 1,
    brand TEXT DEFAULT '',
    material TEXT DEFAULT 'PLA',
    color TEXT DEFAULT '',
    initial_g REAL NOT NULL,
    note TEXT DEFAULT '',
    started_at TEXT,
    ended_at TEXT,
    active INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS prints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_key TEXT UNIQUE,
    title TEXT,
    device_id TEXT,
    status INTEGER,
    start_time TEXT,
    end_time TEXT,
    weight REAL NOT NULL DEFAULT 0,
    slot INTEGER DEFAULT 1,
    spool_id INTEGER,
    counted INTEGER DEFAULT 1,
    source TEXT DEFAULT 'cloud'
);
CREATE TABLE IF NOT EXISTS adjustments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    spool_id INTEGER NOT NULL,
    grams REAL NOT NULL,
    note TEXT DEFAULT '',
    created_at TEXT
);
"""


def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.executescript(SCHEMA)
    return g.db


@app.teardown_appcontext
def close_db(exc):
    d = g.pop("db", None)
    if d:
        d.close()


def cfg_get(key, default=None):
    row = db().execute("SELECT value FROM config WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def cfg_set(key, value):
    db().execute("INSERT INTO config(key,value) VALUES(?,?) "
                 "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
    db().commit()


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@app.template_filter("localtime")
def localtime(iso):
    """Render a UTC ISO timestamp in the computer's local timezone."""
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone()
        return dt.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return iso[:16].replace("T", " ")


# ---------------------------------------------------------------- helpers

def slot_count():
    return int(cfg_get("slot_count", "1"))


def active_spool(slot):
    return db().execute(
        "SELECT * FROM spools WHERE slot=? AND active=1 ORDER BY id DESC LIMIT 1",
        (slot,)).fetchone()


def spool_used(spool_id):
    """Grams consumed on a spool = counted prints + manual adjustments."""
    p = db().execute("SELECT COALESCE(SUM(weight),0) u FROM prints "
                     "WHERE spool_id=? AND counted=1", (spool_id,)).fetchone()["u"]
    a = db().execute("SELECT COALESCE(SUM(grams),0) u FROM adjustments "
                     "WHERE spool_id=?", (spool_id,)).fetchone()["u"]
    return round(p + a, 2)


def spool_stats(spool):
    used = spool_used(spool["id"])
    remaining = round(spool["initial_g"] - used, 2)
    pct = max(0, min(100, round(remaining / spool["initial_g"] * 100))) if spool["initial_g"] else 0
    nprints = db().execute("SELECT COUNT(*) c FROM prints WHERE spool_id=? AND counted=1",
                           (spool["id"],)).fetchone()["c"]
    return {"used": used, "remaining": remaining, "pct": pct, "prints": nprints}


def get_client():
    token = cfg_get("token")
    return BambuCloud(region=cfg_get("region", "global"), token=token)


# ---------------------------------------------------------------- dashboard

@app.route("/")
def dashboard():
    slots = []
    for s in range(1, slot_count() + 1):
        sp = active_spool(s)
        slots.append({"slot": s, "spool": sp, "stats": spool_stats(sp) if sp else None})
    recent = db().execute(
        "SELECT p.*, s.color scolor, s.material smaterial FROM prints p "
        "LEFT JOIN spools s ON s.id=p.spool_id "
        "ORDER BY COALESCE(p.start_time, '') DESC, p.id DESC LIMIT 10").fetchall()
    unassigned = db().execute(
        "SELECT COUNT(*) c FROM prints WHERE spool_id IS NULL AND counted=1").fetchone()["c"]
    return render_template("dashboard.html", slots=slots, recent=recent,
                           unassigned=unassigned,
                           logged_in=bool(cfg_get("token")),
                           last_sync=cfg_get("last_sync"))


# ---------------------------------------------------------------- settings / login

@app.route("/settings", methods=["GET", "POST"])
def settings():
    if request.method == "POST":
        n = max(1, min(4, int(request.form.get("slot_count", 1))))
        cfg_set("slot_count", str(n))
        cfg_set("device_id", request.form.get("device_id", "").strip())
        flash("Settings saved.")
        return redirect(url_for("settings"))
    devices = []
    if cfg_get("token"):
        try:
            devices = get_client().get_devices()
        except Exception:
            pass
    return render_template("settings.html", slot_count=slot_count(),
                           device_id=cfg_get("device_id", ""),
                           email=cfg_get("email", ""),
                           logged_in=bool(cfg_get("token")),
                           devices=devices)


@app.route("/bambu/login", methods=["POST"])
def bambu_login():
    email = request.form["email"].strip()
    password = request.form["password"]
    region = request.form.get("region", "global")
    cfg_set("email", email)
    cfg_set("region", region)
    api = BambuCloud(region=region)
    try:
        token = api.login(email, password)
        cfg_set("token", token)
        flash("Logged in to Bambu Cloud.")
    except NeedsVerifyCode:
        flash("A 6-digit verification code was sent to your email. Enter it below.")
        return render_template("verify.html", email=email)
    except BambuCloudError as e:
        flash(f"Login failed: {e}")
    return redirect(url_for("settings"))


@app.route("/bambu/verify", methods=["POST"])
def bambu_verify():
    email = cfg_get("email")
    code = request.form["code"].strip()
    api = get_client()
    try:
        token = api.login_with_code(email, code)
        cfg_set("token", token)
        flash("Logged in to Bambu Cloud.")
    except BambuCloudError as e:
        flash(f"Verification failed: {e}")
        return render_template("verify.html", email=email)
    return redirect(url_for("settings"))


@app.route("/bambu/logout", methods=["POST"])
def bambu_logout():
    cfg_set("token", "")
    flash("Logged out.")
    return redirect(url_for("settings"))


# ---------------------------------------------------------------- sync

def ams_entries(task):
    """Extract per-slot (slot, grams) pairs from amsDetailMapping, if usable."""
    out = []
    for m in task.get("amsDetailMapping") or []:
        w = m.get("weight") or 0
        slot = m.get("ams")
        if w and slot is not None and 0 <= int(slot) <= 3:
            out.append((int(slot) + 1, float(w)))
    return out


@app.route("/sync", methods=["POST"])
def sync():
    api = get_client()
    if not api.token:
        flash("Log in to Bambu Cloud first (Settings).")
        return redirect(url_for("settings"))
    try:
        tasks = api.get_tasks(device_id=cfg_get("device_id") or None, limit=100)
    except BambuCloudError as e:
        flash(str(e))
        return redirect(url_for("dashboard"))

    added = 0
    for t in tasks:
        # Skip jobs still printing (no end time yet) — they'll be imported
        # on the next sync after they finish, so a job at 0% doesn't get
        # its full estimate deducted (and failed jobs keep their status).
        if not t.get("endTime"):
            continue
        rows = []  # (task_key, slot, grams)
        per_slot = ams_entries(t) if slot_count() > 1 else []
        if per_slot:
            for slot, grams in per_slot:
                rows.append((f"{t['id']}-s{slot}", slot, grams))
        else:
            rows.append((str(t["id"]), 1, float(t.get("weight") or 0)))
        for task_key, slot, grams in rows:
            # Only charge the active spool for prints that started AFTER
            # it was loaded. Older history is imported as "unassigned" so
            # it never deducts from the wrong spool (you can assign it to
            # an archived spool manually on the Prints page).
            sp = active_spool(slot)
            spool_id = None
            started = t.get("startTime") or ""
            if sp and started and (not sp["started_at"] or started >= sp["started_at"]):
                spool_id = sp["id"]
            cur = db().execute(
                "INSERT OR IGNORE INTO prints "
                "(task_key,title,device_id,status,start_time,end_time,weight,slot,spool_id,source) "
                "VALUES (?,?,?,?,?,?,?,?,?,'cloud')",
                (task_key, t.get("title") or "Untitled", t.get("deviceId"),
                 t.get("status"), t.get("startTime"), t.get("endTime"),
                 grams, slot, spool_id))
            added += cur.rowcount
            if cur.rowcount == 0:
                # already imported (e.g. while it was printing) — refresh
                # its status/end time from the cloud
                db().execute(
                    "UPDATE prints SET status=?, end_time=? "
                    "WHERE task_key=? AND source='cloud'",
                    (t.get("status"), t.get("endTime"), task_key))
    db().commit()
    cfg_set("last_sync", now_iso())
    flash(f"Sync complete — {added} new print(s) imported." if added
          else "Sync complete — no new prints.")
    return redirect(url_for("dashboard"))


# ---------------------------------------------------------------- spools

@app.route("/spools")
def spools():
    rows = db().execute("SELECT * FROM spools ORDER BY active DESC, id DESC").fetchall()
    return render_template("spools.html",
                           spools=[(r, spool_stats(r)) for r in rows])


@app.route("/spool/change/<int:slot>", methods=["GET", "POST"])
def spool_change(slot):
    current = active_spool(slot)
    if request.method == "POST":
        # retire the old spool — its usage count "resets" because the new
        # spool starts its own tally from zero
        if current:
            db().execute("UPDATE spools SET active=0, ended_at=? WHERE id=?",
                         (now_iso(), current["id"]))
        db().execute(
            "INSERT INTO spools (slot,brand,material,color,initial_g,note,started_at,active) "
            "VALUES (?,?,?,?,?,?,?,1)",
            (slot, request.form.get("brand", "").strip(),
             request.form.get("material", "PLA").strip(),
             request.form.get("color", "").strip(),
             float(request.form.get("initial_g", 1000)),
             request.form.get("note", "").strip(), now_iso()))
        db().commit()
        flash(f"New spool loaded in slot {slot}. Counter reset.")
        return redirect(url_for("dashboard"))
    return render_template("spool_change.html", slot=slot, current=current,
                           stats=spool_stats(current) if current else None)


@app.route("/spool/<int:spool_id>/adjust", methods=["POST"])
def spool_adjust(spool_id):
    """Correct remaining weight (e.g. after weighing the spool)."""
    sp = db().execute("SELECT * FROM spools WHERE id=?", (spool_id,)).fetchone()
    if not sp:
        flash("Spool not found.")
        return redirect(url_for("spools"))
    measured = float(request.form["remaining_g"])
    diff = round((sp["initial_g"] - spool_used(spool_id)) - measured, 2)
    if diff:
        db().execute("INSERT INTO adjustments (spool_id,grams,note,created_at) "
                     "VALUES (?,?,?,?)",
                     (spool_id, diff, request.form.get("note", "manual correction"),
                      now_iso()))
        db().commit()
    flash("Spool corrected.")
    return redirect(request.referrer or url_for("spools"))


# ---------------------------------------------------------------- prints

@app.route("/prints")
def prints():
    rows = db().execute(
        "SELECT p.*, s.color scolor, s.material smaterial, s.slot sslot FROM prints p "
        "LEFT JOIN spools s ON s.id=p.spool_id "
        "ORDER BY COALESCE(p.start_time,'') DESC, p.id DESC LIMIT 200").fetchall()
    spool_opts = db().execute(
        "SELECT * FROM spools ORDER BY active DESC, id DESC").fetchall()
    return render_template("prints.html", prints=rows, spool_opts=spool_opts)


@app.route("/prints/add", methods=["POST"])
def print_add():
    slot = int(request.form.get("slot", 1))
    sp = active_spool(slot)
    db().execute(
        "INSERT INTO prints (title,weight,slot,spool_id,start_time,source) "
        "VALUES (?,?,?,?,?,'manual')",
        (request.form.get("title", "Manual entry"),
         float(request.form["weight"]), slot,
         sp["id"] if sp else None, now_iso()))
    db().commit()
    flash("Print added.")
    return redirect(url_for("prints"))


@app.route("/prints/<int:pid>/toggle", methods=["POST"])
def print_toggle(pid):
    db().execute("UPDATE prints SET counted = 1-counted WHERE id=?", (pid,))
    db().commit()
    return redirect(request.referrer or url_for("prints"))


@app.route("/prints/<int:pid>/assign", methods=["POST"])
def print_assign(pid):
    spool_id = request.form.get("spool_id") or None
    db().execute("UPDATE prints SET spool_id=? WHERE id=?", (spool_id, pid))
    db().commit()
    return redirect(request.referrer or url_for("prints"))


if __name__ == "__main__":
    # Bind to localhost only. Set FLASK_DEBUG=1 for development — never
    # run with debug on if the port is reachable from other machines
    # (the Werkzeug debugger allows arbitrary code execution).
    app.run(host="127.0.0.1", port=5000,
            debug=os.environ.get("FLASK_DEBUG") == "1")
