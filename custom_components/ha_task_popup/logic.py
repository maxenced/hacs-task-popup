"""Logique pure (sans Home Assistant) : fenêtres de déclenchement et états.

Une tâche est « ouverte » pendant une fenêtre (``Window``) calculée à partir de
son déclencheur. Dans une fenêtre ouverte, la tâche est active, snoozée ou
faite ; hors fenêtre elle est inactive.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any

from .const import (
    STATE_ACTIVE,
    STATE_DONE,
    STATE_INACTIVE,
    STATE_SNOOZED,
    WEEKDAYS,
)


@dataclass(frozen=True)
class Window:
    """Fenêtre pendant laquelle une tâche doit être faite."""

    key: str
    start: datetime
    end: datetime | None = None  # None : ouverte jusqu'à « Fait »

    def is_open(self, now: datetime) -> bool:
        """Retourne vrai si la fenêtre couvre ``now``."""
        return self.start <= now and (self.end is None or now < self.end)


@dataclass(frozen=True)
class CalendarEvent:
    """Événement de calendrier réduit à ce qui nous sert."""

    summary: str
    start: datetime
    end: datetime


def parse_time(value: str | None) -> time | None:
    """Convertit « HH:MM[:SS] » en ``time``."""
    if not value:
        return None
    return time.fromisoformat(value)


def simple_window(
    now: datetime,
    days: list[str],
    start: time,
    end: time | None,
    since: datetime | None = None,
) -> Window | None:
    """Fenêtre du déclencheur « simple » (jours + heure de départ).

    La dernière occurrence démarrée (et postérieure à ``since``, date de
    création de la tâche) ouvre la fenêtre. Sans heure de fin, elle reste
    ouverte jusqu'à l'acquittement ; une nouvelle occurrence la remplace.
    """
    weekdays = {WEEKDAYS.index(day) for day in days if day in WEEKDAYS}
    if not weekdays:
        return None
    for back in range(8):
        day: date = now.date() - timedelta(days=back)
        if day.weekday() not in weekdays:
            continue
        occ_start = datetime.combine(day, start, tzinfo=now.tzinfo)
        if occ_start > now:
            continue
        if since is not None and occ_start < since:
            return None
        occ_end = None
        if end is not None:
            occ_end = datetime.combine(day, end, tzinfo=now.tzinfo)
            if occ_end <= occ_start:
                occ_end += timedelta(days=1)
            if now >= occ_end:
                return None
        return Window(key=f"simple:{occ_start.isoformat()}", start=occ_start, end=occ_end)
    return None


def _event_datetime(value: Any, tzinfo: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=tzinfo)
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=tzinfo)
    text = str(value)
    if "T" in text or " " in text:
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=tzinfo)
    return datetime.combine(date.fromisoformat(text), time.min, tzinfo=tzinfo)


def parse_calendar_events(raw: list[dict[str, Any]], tzinfo: Any) -> list[CalendarEvent]:
    """Convertit la réponse de ``calendar.get_events`` (dates ou date-heures)."""
    events = []
    for item in raw:
        try:
            events.append(
                CalendarEvent(
                    summary=str(item.get("summary") or ""),
                    start=_event_datetime(item["start"], tzinfo),
                    end=_event_datetime(item["end"], tzinfo),
                )
            )
        except (KeyError, ValueError, TypeError):
            continue
    return events


def calendar_window(now: datetime, events: list[CalendarEvent], title_filter: str | None) -> Window | None:
    """Fenêtre du déclencheur « planning » : l'événement en cours le plus ancien."""
    needle = (title_filter or "").strip().casefold()
    ongoing = [event for event in events if event.start <= now < event.end and needle in event.summary.casefold()]
    if not ongoing:
        return None
    event = min(ongoing, key=lambda ev: (ev.start, ev.summary))
    return Window(
        key=f"calendar:{event.summary}|{event.start.isoformat()}",
        start=event.start,
        end=event.end,
    )


def detection_window(now: datetime, triggered_at: datetime | None, duration: timedelta) -> Window | None:
    """Fenêtre du déclencheur « détection » : ``duration`` après la transition."""
    if triggered_at is None:
        return None
    window = Window(
        key=f"detection:{triggered_at.isoformat()}",
        start=triggered_at,
        end=triggered_at + duration,
    )
    return window if window.is_open(now) else None


@dataclass
class TaskRuntime:
    """État persistant d'une tâche."""

    window_key: str | None = None
    done_key: str | None = None
    snoozed_until: datetime | None = None
    active_since: datetime | None = None
    state: str = STATE_INACTIVE
    window: Window | None = field(default=None, compare=False)

    def as_dict(self) -> dict[str, Any]:
        """Sérialise pour le stockage."""
        return {
            "window_key": self.window_key,
            "done_key": self.done_key,
            "snoozed_until": _iso(self.snoozed_until),
            "active_since": _iso(self.active_since),
            "state": self.state,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> TaskRuntime:
        """Désérialise depuis le stockage."""
        data = data or {}
        return cls(
            window_key=data.get("window_key"),
            done_key=data.get("done_key"),
            snoozed_until=_from_iso(data.get("snoozed_until")),
            active_since=_from_iso(data.get("active_since")),
            state=data.get("state", STATE_INACTIVE),
        )


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _from_iso(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def evaluate(runtime: TaskRuntime, window: Window | None, now: datetime) -> str:
    """Met à jour ``runtime`` pour la fenêtre courante et retourne l'état."""
    runtime.window = window
    if window is None or not window.is_open(now):
        runtime.window_key = None
        runtime.snoozed_until = None
        runtime.active_since = None
        runtime.state = STATE_INACTIVE
        return runtime.state

    if window.key != runtime.window_key:
        # Nouvelle occurrence : on repart de zéro.
        runtime.window_key = window.key
        runtime.snoozed_until = None
        runtime.active_since = None

    if runtime.done_key == window.key:
        state = STATE_DONE
    elif runtime.snoozed_until is not None and now < runtime.snoozed_until:
        state = STATE_SNOOZED
    else:
        runtime.snoozed_until = None
        state = STATE_ACTIVE

    if state == STATE_ACTIVE and runtime.state != STATE_ACTIVE:
        # Une tâche qui (re)devient active passe en fin de file.
        runtime.active_since = now
    elif state != STATE_ACTIVE:
        runtime.active_since = None
    runtime.state = state
    return state


def acknowledge(runtime: TaskRuntime) -> bool:
    """Marque l'occurrence courante comme faite. Faux si rien n'est ouvert."""
    if runtime.window_key is None:
        return False
    runtime.done_key = runtime.window_key
    runtime.snoozed_until = None
    return True


def snooze(runtime: TaskRuntime, now: datetime, minutes: float) -> bool:
    """Reporte la tâche de ``minutes``. Faux si elle n'est pas active/snoozée."""
    if runtime.window_key is None or runtime.done_key == runtime.window_key:
        return False
    runtime.snoozed_until = now + timedelta(minutes=minutes)
    return True
