"""Data access for the agent.

Two backends implement the same small protocol:

* ``SupabaseBackend`` talks to the app's Supabase project through PostgREST
  with the signed-in user's access token, so row-level security decides what
  the agent can see and change, exactly as in the web app.
* ``FixtureBackend`` keeps data in memory. Tests and evals use it so they are
  deterministic and never touch real accounts.

``FilamentService`` holds the domain logic (feasibility checks, usage stats)
on top of either backend. The MCP tools are thin wrappers around it.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

import httpx

from .models import (
    Candidate,
    Feasibility,
    Print,
    PrintList,
    Settings,
    Spool,
    SpoolList,
    SpoolUsage,
    UsageSummary,
    WriteResult,
)

# ------------------------------------------------------------------ helpers

_NAMED_COLORS = {
    "black": (0, 0, 0),
    "white": (255, 255, 255),
    "grey": (128, 128, 128),
    "red": (220, 30, 30),
    "orange": (255, 140, 0),
    "yellow": (250, 215, 0),
    "green": (40, 160, 60),
    "blue": (30, 90, 220),
    "purple": (130, 50, 170),
    "pink": (240, 120, 170),
    "brown": (120, 75, 40),
    "beige": (225, 205, 165),
}


def color_name(hex_color: str) -> str:
    """Nearest plain colour name for a '#rrggbb' value ('' if not a hex colour)."""
    h = hex_color.strip().lstrip("#")
    if len(h) != 6:
        return hex_color.strip().lower()
    try:
        rgb = tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return hex_color.strip().lower()
    return min(_NAMED_COLORS, key=lambda n: sum((a - b) ** 2 for a, b in zip(rgb, _NAMED_COLORS[n], strict=True)))


def spool_label(s: Spool) -> str:
    parts = [s.color_name, s.brand if s.brand and s.brand.lower() != "generic" else "", s.material]
    return " ".join(p for p in parts if p) + f" (slot {s.slot}, spool #{s.id})"


def _dt(v: Any) -> datetime | None:
    if v in (None, ""):
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=UTC)
    return datetime.fromisoformat(str(v).replace("Z", "+00:00"))


def _num(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def make_spool(row: dict[str, Any]) -> Spool:
    initial = _num(row.get("initial_g"))
    remaining = _num(row.get("remaining_g"))
    color = str(row.get("color") or "")
    return Spool(
        id=int(row["id"]),
        slot=int(row.get("slot") or 1),
        brand=str(row.get("brand") or ""),
        material=str(row.get("material") or "PLA"),
        color=color,
        color_name=color_name(color) if color else "",
        initial_g=round(initial, 2),
        used_g=round(_num(row.get("used_g")), 2),
        remaining_g=round(remaining, 2),
        pct_left=max(0, min(100, round(remaining / initial * 100))) if initial > 0 else 0,
        active=bool(row.get("active")),
        started_at=_dt(row.get("started_at")),
        ended_at=_dt(row.get("ended_at")),
        print_count=int(row.get("print_count") or 0),
        note=str(row.get("note") or ""),
    )


def make_print(row: dict[str, Any]) -> Print:
    return Print(
        id=int(row["id"]),
        title=str(row.get("title") or "Untitled"),
        weight_g=round(_num(row.get("weight")), 2),
        slot=int(row.get("slot") or 1),
        spool_id=None if row.get("spool_id") is None else int(row["spool_id"]),
        counted=bool(row.get("counted", True)),
        source="manual" if row.get("source") == "manual" else "cloud",
        start_time=_dt(row.get("start_time")),
        end_time=_dt(row.get("end_time")),
    )


# ------------------------------------------------------------------ backends


class Backend(Protocol):
    def settings(self) -> Settings: ...
    def spools(self, include_archived: bool) -> list[Spool]: ...
    def prints(self, limit: int, spool_id: int | None, since: datetime | None, include_ignored: bool) -> list[Print]: ...
    def add_manual_print(self, title: str, grams: float, slot: int, spool_id: int | None) -> Print: ...
    def set_remaining(self, spool_id: int, measured_g: float, note: str) -> float: ...


class FixtureBackend:
    """In-memory backend that mirrors the SQL view and functions in the migration."""

    def __init__(self, data: dict[str, Any]):
        self._settings = data.get("settings", {})
        self._spools = [dict(s) for s in data.get("spools", [])]
        self._prints = [dict(p) for p in data.get("prints", [])]
        self._adjustments = [dict(a) for a in data.get("adjustments", [])]

        # Fixtures may pin "now" so date-window answers are reproducible.
        self.now = _dt(data.get("now"))

    @classmethod
    def from_file(cls, path: str | Path) -> FixtureBackend:
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def _stats(self, s: dict[str, Any]) -> Spool:
        counted = [p for p in self._prints if p.get("spool_id") == s["id"] and p.get("counted", True)]
        adj = sum(_num(a["grams"]) for a in self._adjustments if a["spool_id"] == s["id"])
        used = sum(_num(p["weight"]) for p in counted) + adj
        return make_spool({**s, "used_g": used, "remaining_g": _num(s["initial_g"]) - used, "print_count": len(counted)})

    def settings(self) -> Settings:
        return Settings(slot_count=int(self._settings.get("slot_count", 1)), last_sync=_dt(self._settings.get("last_sync")))

    def spools(self, include_archived: bool) -> list[Spool]:
        rows = [self._stats(s) for s in self._spools if include_archived or s.get("active")]
        return sorted(rows, key=lambda s: (not s.active, -s.id))

    def prints(self, limit, spool_id, since, include_ignored):
        rows = [make_print(p) for p in self._prints]
        if spool_id is not None:
            rows = [p for p in rows if p.spool_id == spool_id]
        if since is not None:
            rows = [p for p in rows if p.start_time and p.start_time >= since]
        if not include_ignored:
            rows = [p for p in rows if p.counted]
        rows.sort(key=lambda p: (p.start_time or datetime.min.replace(tzinfo=UTC), p.id), reverse=True)
        return rows[:limit]

    def add_manual_print(self, title, grams, slot, spool_id):
        row = {
            "id": max((p["id"] for p in self._prints), default=0) + 1,
            "title": title,
            "weight": grams,
            "slot": slot,
            "spool_id": spool_id,
            "counted": True,
            "source": "manual",
            "start_time": (self.now or datetime.now(UTC)).isoformat(),
        }
        self._prints.append(row)
        return make_print(row)

    def set_remaining(self, spool_id, measured_g, note):
        spool = next((s for s in self._spools if s["id"] == spool_id), None)
        if spool is None:
            raise LookupError(f"spool {spool_id} not found")
        diff = round(self._stats(spool).remaining_g - measured_g, 2)
        if diff != 0:
            self._adjustments.append({"spool_id": spool_id, "grams": diff, "note": note})
        return diff


class SupabaseBackend:
    """PostgREST client that runs every request as the signed-in user (RLS applies)."""

    def __init__(self, url: str, publishable_key: str, access_token: Callable[[], str], timeout: float = 15.0):
        self._base = url.rstrip("/") + "/rest/v1"
        self._key = publishable_key
        self._token = access_token
        self._http = httpx.Client(timeout=timeout)

    def _headers(self, **extra: str) -> dict[str, str]:
        return {"apikey": self._key, "Authorization": f"Bearer {self._token()}", **extra}

    def _get(self, path: str, params: dict[str, str]) -> list[dict[str, Any]]:
        r = self._http.get(f"{self._base}/{path}", params=params, headers=self._headers())
        r.raise_for_status()
        return r.json()

    def settings(self) -> Settings:
        rows = self._get("user_settings", {"select": "slot_count,last_sync"})
        return Settings(**rows[0]) if rows else Settings()

    def spools(self, include_archived):
        params = {"select": "*", "order": "active.desc,id.desc"}
        if not include_archived:
            params["active"] = "is.true"
        return [make_spool(r) for r in self._get("spool_stats", params)]

    def prints(self, limit, spool_id, since, include_ignored):
        params = {"select": "*", "order": "start_time.desc.nullslast,id.desc", "limit": str(limit)}
        if spool_id is not None:
            params["spool_id"] = f"eq.{spool_id}"
        if since is not None:
            params["start_time"] = f"gte.{since.isoformat()}"
        if not include_ignored:
            params["counted"] = "is.true"
        return [make_print(r) for r in self._get("prints", params)]

    def add_manual_print(self, title, grams, slot, spool_id):
        body = {
            "title": title,
            "weight": grams,
            "slot": slot,
            "spool_id": spool_id,
            "source": "manual",
            "start_time": datetime.now(UTC).isoformat(),
        }
        r = self._http.post(
            f"{self._base}/prints", json=body, headers=self._headers(Prefer="return=representation")
        )
        r.raise_for_status()
        return make_print(r.json()[0])

    def set_remaining(self, spool_id, measured_g, note):
        r = self._http.post(
            f"{self._base}/rpc/set_remaining",
            json={"p_spool_id": spool_id, "p_measured_g": measured_g, "p_note": note},
            headers=self._headers(),
        )
        if r.status_code == 404 or "P0002" in r.text:
            raise LookupError(f"spool {spool_id} not found")
        r.raise_for_status()
        return _num(r.json())


# ------------------------------------------------------------------ service


class FilamentService:
    """Domain logic shared by every backend. All arithmetic lives here, not in the LLM."""

    def __init__(self, backend: Backend, now: Callable[[], datetime] | None = None):
        self.backend = backend
        pinned = getattr(backend, "now", None)
        self._now = now or (lambda: pinned or datetime.now(UTC))

    def now(self) -> datetime:
        return self._now()

    # ---------- reads

    def list_spools(self, include_archived: bool = False) -> SpoolList:
        return SpoolList(
            as_of=self._now(),
            spools=self.backend.spools(include_archived),
            slot_count=self.backend.settings().slot_count,
        )

    def get_spool(self, spool_id: int) -> Spool:
        for s in self.backend.spools(include_archived=True):
            if s.id == spool_id:
                return s
        raise LookupError(f"spool {spool_id} not found")

    def list_prints(
        self, limit: int = 20, spool_id: int | None = None, days: int | None = None, include_ignored: bool = False
    ) -> PrintList:
        since = self._now() - timedelta(days=days) if days else None
        rows = self.backend.prints(max(1, min(limit, 200)), spool_id, since, include_ignored)
        return PrintList(prints=rows, total_returned=len(rows))

    def usage_summary(self, days: int = 30) -> UsageSummary:
        days = max(1, min(days, 365))
        since = self._now() - timedelta(days=days)
        prints = self.backend.prints(1000, None, since, include_ignored=False)
        spools = self.backend.spools(include_archived=True)
        by_id = {s.id: s for s in spools}
        by_material: dict[str, float] = {}
        per_spool: dict[int, float] = {}
        for p in prints:
            mat = by_id[p.spool_id].material if p.spool_id in by_id else "unassigned"
            by_material[mat] = round(by_material.get(mat, 0) + p.weight_g, 2)
            if p.spool_id is not None:
                per_spool[p.spool_id] = per_spool.get(p.spool_id, 0) + p.weight_g
        usage = []
        for s in spools:
            if not s.active:
                continue
            used = round(per_spool.get(s.id, 0.0), 2)
            # Only count the days the spool has actually been loaded.
            loaded_days = days
            if s.started_at:
                loaded_days = max(1.0, min(days, (self._now() - s.started_at).total_seconds() / 86400))
            avg = round(used / loaded_days, 2)
            usage.append(
                SpoolUsage(
                    spool_id=s.id,
                    label=spool_label(s),
                    remaining_g=s.remaining_g,
                    used_in_window_g=used,
                    avg_g_per_day=avg,
                    days_until_empty=round(s.remaining_g / avg, 1) if avg > 0 else None,
                )
            )
        return UsageSummary(
            window_days=days,
            total_used_g=round(sum(p.weight_g for p in prints), 2),
            print_count=len(prints),
            by_material=by_material,
            spools=usage,
        )

    def check_feasibility(
        self,
        grams: float,
        material: str | None = None,
        color: str | None = None,
        spool_id: int | None = None,
        safety_margin_pct: float = 10.0,
    ) -> Feasibility:
        if grams <= 0:
            raise ValueError("grams must be positive")
        active = self.backend.spools(include_archived=False)
        pool = active
        if spool_id is not None:
            pool = [s for s in active if s.id == spool_id]
        if material:
            pool = [s for s in pool if s.material.lower() == material.strip().lower()]
        if color:
            c = color.strip().lower()
            pool = [s for s in pool if c in (s.color_name, s.color.lower())]
        needed_with_margin = grams * (1 + safety_margin_pct / 100)
        candidates = []
        for s in pool:
            if s.remaining_g >= needed_with_margin:
                verdict = "yes"
            elif s.remaining_g >= grams:
                verdict = "tight"
            else:
                verdict = "no"
            candidates.append(
                Candidate(
                    spool_id=s.id,
                    label=spool_label(s),
                    remaining_g=s.remaining_g,
                    margin_g=round(s.remaining_g - grams, 2),
                    verdict=verdict,
                )
            )
        candidates.sort(key=lambda c: c.remaining_g, reverse=True)
        if not candidates:
            return Feasibility(
                grams_needed=grams,
                safety_margin_pct=safety_margin_pct,
                material=material,
                color=color,
                verdict="no_matching_spool",
                best_spool_id=None,
                candidates=[],
                note="No loaded spool matches. Archived spools are not considered.",
            )
        best = candidates[0]
        return Feasibility(
            grams_needed=grams,
            safety_margin_pct=safety_margin_pct,
            material=material,
            color=color,
            verdict=best.verdict,
            best_spool_id=best.spool_id,
            candidates=candidates,
            note=(
                f"'yes' needs {safety_margin_pct:g}% headroom over the slicer estimate "
                "(purge and failed prints make real usage drift); 'tight' means it fits only without it."
            ),
        )

    # ---------- writes

    def log_print(self, title: str, grams: float, slot: int) -> WriteResult:
        if grams <= 0:
            raise ValueError("grams must be positive")
        settings = self.backend.settings()
        if not 1 <= slot <= settings.slot_count:
            raise ValueError(f"slot must be between 1 and {settings.slot_count}")
        spool = next((s for s in self.backend.spools(False) if s.slot == slot), None)
        p = self.backend.add_manual_print(title.strip() or "Manual entry", grams, slot, spool.id if spool else None)
        updated = self.get_spool(spool.id) if spool else None
        target = spool_label(spool) if spool else f"slot {slot} (no spool loaded, saved as unassigned)"
        return WriteResult(ok=True, message=f"Logged print #{p.id} ({grams:g} g) on {target}.", spool=updated)

    def correct_spool(self, spool_id: int, measured_g: float, note: str = "corrected via agent") -> WriteResult:
        if measured_g < 0:
            raise ValueError("measured_g can't be negative")
        before = self.get_spool(spool_id)
        diff = self.backend.set_remaining(spool_id, measured_g, note)
        after = self.get_spool(spool_id)
        return WriteResult(
            ok=True,
            message=f"Spool #{spool_id} corrected from {before.remaining_g:g} g to {after.remaining_g:g} g "
            f"(adjustment {diff:+g} g).",
            spool=after,
        )
