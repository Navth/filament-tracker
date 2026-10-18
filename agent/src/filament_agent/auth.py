"""Sign in to the Filament Tracker Supabase project and keep the session fresh.

The CLI asks for your email and password once, exchanges them for a
Supabase session (access + refresh token), and stores only the session
under ~/.filament-agent. The password is never stored.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

import httpx

from .config import config_dir, supabase_key, supabase_url
from .repository import SupabaseBackend


def _session_path():
    return config_dir() / "session.json"


def _auth(path: str, body: dict[str, Any]) -> dict[str, Any]:
    r = httpx.post(
        f"{supabase_url().rstrip('/')}/auth/v1/{path}",
        json=body,
        headers={"apikey": supabase_key()},
        timeout=15,
    )
    if r.status_code >= 400:
        try:
            msg = r.json().get("msg") or r.json().get("error_description") or r.text
        except ValueError:
            msg = r.text
        raise RuntimeError(f"Supabase sign-in failed: {msg}")
    return r.json()


def _save(session: dict[str, Any]) -> dict[str, Any]:
    data = {
        "access_token": session["access_token"],
        "refresh_token": session["refresh_token"],
        "expires_at": session.get("expires_at") or int(time.time()) + int(session.get("expires_in", 3600)),
        "email": (session.get("user") or {}).get("email", ""),
    }
    path = _session_path()
    path.write_text(json.dumps(data), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return data


def login(email: str, password: str) -> str:
    """Password sign-in. Returns the signed-in email."""
    return _save(_auth("token?grant_type=password", {"email": email, "password": password}))["email"]


def logout() -> None:
    _session_path().unlink(missing_ok=True)


def current_email() -> str | None:
    path = _session_path()
    return json.loads(path.read_text(encoding="utf-8")).get("email") if path.is_file() else None


def access_token() -> str:
    """A valid access token, refreshed when it is within a minute of expiry."""
    path = _session_path()
    if not path.is_file():
        raise RuntimeError("Not signed in. Run: ft-agent login")
    data = json.loads(path.read_text(encoding="utf-8"))
    if data["expires_at"] - time.time() < 60:
        data = _save(_auth("token?grant_type=refresh_token", {"refresh_token": data["refresh_token"]}))
    return data["access_token"]


def supabase_backend() -> SupabaseBackend:
    return SupabaseBackend(supabase_url(), supabase_key(), access_token)
