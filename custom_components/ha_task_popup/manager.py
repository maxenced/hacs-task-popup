"""Gestionnaire des tâches : déclencheurs, états persistants, écran, popup."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import CALLBACK_TYPE, Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    CALENDAR_REFRESH_SECONDS,
    CONF_CALENDAR,
    CONF_COLOR,
    CONF_DAYS,
    CONF_DISPLAY_MODE,
    CONF_DISPLAY_ON,
    CONF_DURATION_MINUTES,
    CONF_END_TIME,
    CONF_ENTITY,
    CONF_FULLY_DEVICES,
    CONF_ICON,
    CONF_MANAGE_SCREEN,
    CONF_MAX_BRIGHTNESS,
    CONF_MESSAGE,
    CONF_NAME,
    CONF_SNOOZE_MINUTES,
    CONF_START_TIME,
    CONF_TARGET_STATE,
    CONF_TITLE_FILTER,
    CONF_TRIGGER,
    DEFAULT_COLOR,
    DEFAULT_DURATION_MINUTES,
    DEFAULT_ICON,
    DEFAULT_SNOOZE_MINUTES,
    DEFAULT_TARGET_STATE,
    DISPLAY_MODE_FULLSCREEN,
    DISPLAY_ON_FULLY,
    DOMAIN,
    SIGNAL_UPDATE,
    STATE_ACTIVE,
    SUBENTRY_TYPE_TASK,
    TICK_SECONDS,
    TRIGGER_CALENDAR,
    TRIGGER_DETECTION,
    TRIGGER_SIMPLE,
)
from .logic import (
    CalendarEvent,
    TaskRuntime,
    Window,
    acknowledge,
    calendar_window,
    detection_window,
    evaluate,
    parse_calendar_events,
    parse_time,
    simple_window,
    snooze,
)
from .screen import ScreenManager, fully_device_ids

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1

type FrontendListener = Callable[[dict[str, Any]], None]


@dataclass(frozen=True)
class TaskDef:
    """Configuration d'une tâche (issue d'une sous-entrée)."""

    task_id: str
    data: dict[str, Any]

    @property
    def name(self) -> str:
        return self.data.get(CONF_NAME, "")

    @property
    def trigger(self) -> str:
        return self.data.get(CONF_TRIGGER, TRIGGER_SIMPLE)

    @property
    def snooze_minutes(self) -> float:
        return float(self.data.get(CONF_SNOOZE_MINUTES, DEFAULT_SNOOZE_MINUTES))

    def color_hex(self) -> str:
        red, green, blue = self.data.get(CONF_COLOR) or DEFAULT_COLOR
        return f"#{int(red):02x}{int(green):02x}{int(blue):02x}"


def frontend_listeners(hass: HomeAssistant) -> set[FrontendListener]:
    """Abonnés websocket du module JS (survivent aux rechargements)."""
    return hass.data.setdefault(DOMAIN, {}).setdefault("listeners", set())


def get_manager(hass: HomeAssistant) -> TaskPopupManager | None:
    """Gestionnaire chargé (une seule entrée de configuration)."""
    return hass.data.get(DOMAIN, {}).get("manager")


def empty_payload() -> dict[str, Any]:
    """Charge utile envoyée quand l'intégration n'est pas chargée."""
    return {"tasks": [], "display_on": DISPLAY_ON_FULLY, "fully_ids": []}


@callback
def notify_frontend(hass: HomeAssistant) -> None:
    """Pousse la file des tâches affichables à tous les navigateurs abonnés."""
    manager = get_manager(hass)
    payload = manager.frontend_payload() if manager else empty_payload()
    for listener in list(frontend_listeners(hass)):
        listener(payload)


class TaskPopupManager:
    """Évalue les tâches et diffuse leur état."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialise depuis l'entrée et ses sous-entrées."""
        self.hass = hass
        self.entry = entry
        self.options: dict[str, Any] = {**entry.data, **entry.options}
        self.tasks: dict[str, TaskDef] = {
            sub_id: TaskDef(sub_id, dict(sub.data))
            for sub_id, sub in entry.subentries.items()
            if sub.subentry_type == SUBENTRY_TYPE_TASK
        }
        self.runtimes: dict[str, TaskRuntime] = {}
        # Métadonnées persistées : date de création, dernière détection
        self.meta: dict[str, dict[str, Any]] = {}
        self.calendar_events: dict[str, list[CalendarEvent]] = {}
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")
        self._unsubs: list[CALLBACK_TYPE] = []
        self._visible: list[str] = []
        self.screen = ScreenManager(
            hass,
            self.options.get(CONF_FULLY_DEVICES, []),
            wake=self.options.get(CONF_MANAGE_SCREEN, True),
            max_brightness=self.options.get(CONF_MAX_BRIGHTNESS, False),
        )

    # ------------------------------------------------------------------ cycle

    async def async_start(self) -> None:
        """Charge l'état persistant et branche les déclencheurs."""
        stored = await self._store.async_load() or {}
        now = dt_util.now()
        for task_id in self.tasks:
            saved = stored.get("tasks", {}).get(task_id, {})
            self.runtimes[task_id] = TaskRuntime.from_dict(saved.get("runtime"))
            self.meta[task_id] = {
                "since": saved.get("since") or now.isoformat(),
                "triggered_at": saved.get("triggered_at"),
            }
        self.screen.saved.update(stored.get("screen", {}))
        self.screen.saved_brightness.update(stored.get("brightness", {}))

        detection_entities = {
            task.data[CONF_ENTITY]
            for task in self.tasks.values()
            if task.trigger == TRIGGER_DETECTION and task.data.get(CONF_ENTITY)
        }
        if detection_entities:
            self._unsubs.append(
                async_track_state_change_event(self.hass, list(detection_entities), self._async_detection_changed)
            )
        calendars = self._calendars()
        if calendars:
            self._unsubs.append(
                async_track_state_change_event(self.hass, list(calendars), self._async_calendar_changed)
            )
            self._unsubs.append(
                async_track_time_interval(
                    self.hass, self._async_refresh_calendars, timedelta(seconds=CALENDAR_REFRESH_SECONDS)
                )
            )
            await self._async_refresh_calendars()
        self._unsubs.append(async_track_time_interval(self.hass, self._async_tick, timedelta(seconds=TICK_SECONDS)))
        self.async_evaluate(force=True)

    async def async_stop(self) -> None:
        """Débranche tout ; restaure l'écran sauf à l'arrêt de HA."""
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        if not self.hass.is_stopping and self.screen.holding:
            await self.screen.async_release()
        await self._store.async_save(self._store_data())

    # ------------------------------------------------------------ évaluation

    @callback
    def _async_tick(self, _now: datetime) -> None:
        self.async_evaluate()

    def _calendars(self) -> set[str]:
        return {
            task.data[CONF_CALENDAR]
            for task in self.tasks.values()
            if task.trigger == TRIGGER_CALENDAR and task.data.get(CONF_CALENDAR)
        }

    def _window(self, task: TaskDef, now: datetime) -> Window | None:
        data = task.data
        meta = self.meta.get(task.task_id, {})
        if task.trigger == TRIGGER_SIMPLE:
            start = parse_time(data.get(CONF_START_TIME))
            if start is None:
                return None
            since = meta.get("since")
            return simple_window(
                now,
                data.get(CONF_DAYS, []),
                start,
                parse_time(data.get(CONF_END_TIME)),
                since=datetime.fromisoformat(since) if since else None,
            )
        if task.trigger == TRIGGER_CALENDAR:
            events = self.calendar_events.get(data.get(CONF_CALENDAR, ""), [])
            return calendar_window(now, events, data.get(CONF_TITLE_FILTER))
        if task.trigger == TRIGGER_DETECTION:
            triggered = meta.get("triggered_at")
            return detection_window(
                now,
                datetime.fromisoformat(triggered) if triggered else None,
                timedelta(minutes=float(data.get(CONF_DURATION_MINUTES, DEFAULT_DURATION_MINUTES))),
            )
        return None

    @callback
    def async_evaluate(self, force: bool = False) -> None:
        """Recalcule l'état de chaque tâche et diffuse les changements."""
        now = dt_util.now()
        changed = force
        for task_id, task in self.tasks.items():
            runtime = self.runtimes[task_id]
            before = runtime.as_dict()
            evaluate(runtime, self._window(task, now), now)
            if runtime.as_dict() != before:
                changed = True
        if not changed:
            return
        self._store.async_delay_save(self._store_data, 1)
        async_dispatcher_send(self.hass, f"{SIGNAL_UPDATE}_{self.entry.entry_id}")
        notify_frontend(self.hass)
        self._update_screen()

    def visible_tasks(self) -> list[str]:
        """Tâches actives, dans l'ordre d'affichage (la plus ancienne d'abord)."""
        active = [
            (runtime.active_since or dt_util.utcnow(), task_id)
            for task_id, runtime in self.runtimes.items()
            if runtime.state == STATE_ACTIVE
        ]
        return [task_id for _, task_id in sorted(active)]

    @callback
    def _update_screen(self) -> None:
        if not self.screen.enabled:
            return
        visible = self.visible_tasks()
        previous, self._visible = self._visible, visible
        if visible and set(visible) - set(previous):
            self.hass.async_create_task(self._async_show_screen())
        elif not visible and self.screen.holding:
            self.hass.async_create_task(self._async_release_screen())

    async def _async_show_screen(self) -> None:
        await self.screen.async_show()
        self._store.async_delay_save(self._store_data, 1)

    async def _async_release_screen(self) -> None:
        await self.screen.async_release()
        self._store.async_delay_save(self._store_data, 1)

    # ----------------------------------------------------------- déclencheurs

    @callback
    def _async_detection_changed(self, event: Event[EventStateChangedData]) -> None:
        old_state = event.data["old_state"]
        new_state = event.data["new_state"]
        if old_state is None or new_state is None:
            return
        if old_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return
        now = dt_util.now()
        for task in self.tasks.values():
            if task.trigger != TRIGGER_DETECTION or task.data.get(CONF_ENTITY) != new_state.entity_id:
                continue
            target = str(task.data.get(CONF_TARGET_STATE, DEFAULT_TARGET_STATE))
            if new_state.state == target and old_state.state != target:
                self.meta[task.task_id]["triggered_at"] = now.isoformat()
        self.async_evaluate()

    @callback
    def _async_calendar_changed(self, _event: Event[EventStateChangedData]) -> None:
        self.hass.async_create_task(self._async_refresh_calendars())

    async def _async_refresh_calendars(self, _now: datetime | None = None) -> None:
        """Récupère les événements en cours et à venir de chaque calendrier."""
        now = dt_util.now()
        for calendar in self._calendars():
            try:
                response = await self.hass.services.async_call(
                    "calendar",
                    "get_events",
                    {
                        "entity_id": calendar,
                        "start_date_time": now - timedelta(seconds=1),
                        "end_date_time": now + timedelta(seconds=2 * CALENDAR_REFRESH_SECONDS),
                    },
                    blocking=True,
                    return_response=True,
                )
            except (HomeAssistantError, ValueError) as err:
                _LOGGER.warning("Lecture du calendrier %s impossible : %s", calendar, err)
                continue
            raw = (response or {}).get(calendar, {}).get("events", [])
            self.calendar_events[calendar] = parse_calendar_events(raw, now.tzinfo)
        self.async_evaluate()

    # --------------------------------------------------------------- actions

    def _runtime(self, task_id: str) -> TaskRuntime:
        if task_id not in self.runtimes:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="unknown_task", translation_placeholders={"task": task_id}
            )
        return self.runtimes[task_id]

    @callback
    def async_ack(self, task_id: str) -> None:
        """Marque la tâche comme faite."""
        if not acknowledge(self._runtime(task_id)):
            _LOGGER.debug("Tâche %s non active : acquittement ignoré", task_id)
        self.async_evaluate(force=True)

    @callback
    def async_snooze(self, task_id: str, minutes: float | None = None) -> None:
        """Reporte la tâche (durée de la tâche par défaut)."""
        runtime = self._runtime(task_id)
        delay = minutes if minutes is not None else self.tasks[task_id].snooze_minutes
        if not snooze(runtime, dt_util.now(), delay):
            _LOGGER.debug("Tâche %s non active : snooze ignoré", task_id)
        self.async_evaluate(force=True)

    # ------------------------------------------------------------- exports

    def frontend_payload(self) -> dict[str, Any]:
        """File des tâches à afficher pour le module JS."""
        tasks = []
        for task_id in self.visible_tasks():
            task = self.tasks[task_id]
            tasks.append(
                {
                    "id": task_id,
                    "name": task.name,
                    "message": task.data.get(CONF_MESSAGE, ""),
                    "icon": task.data.get(CONF_ICON) or DEFAULT_ICON,
                    "color": task.color_hex(),
                    "display_mode": task.data.get(CONF_DISPLAY_MODE, DISPLAY_MODE_FULLSCREEN),
                    "snooze_minutes": task.snooze_minutes,
                }
            )
        return {
            "tasks": tasks,
            "display_on": self.options.get(CONF_DISPLAY_ON, DISPLAY_ON_FULLY),
            "fully_ids": fully_device_ids(self.hass, self.options.get(CONF_FULLY_DEVICES, [])),
        }

    def _store_data(self) -> dict[str, Any]:
        return {
            "tasks": {
                task_id: {
                    "runtime": self.runtimes[task_id].as_dict(),
                    "since": self.meta[task_id].get("since"),
                    "triggered_at": self.meta[task_id].get("triggered_at"),
                }
                for task_id in self.runtimes
            },
            "screen": dict(self.screen.saved),
            "brightness": dict(self.screen.saved_brightness),
        }
