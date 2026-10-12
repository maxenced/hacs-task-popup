"""Constantes de l'intégration HA Task Popup."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "ha_task_popup"

SUBENTRY_TYPE_TASK: Final = "task"

# Options de l'entrée principale
CONF_FULLY_DEVICES: Final = "fully_devices"
CONF_DISPLAY_ON: Final = "display_on"
CONF_MANAGE_SCREEN: Final = "manage_screen"

DISPLAY_ON_FULLY: Final = "fully"
DISPLAY_ON_ALL: Final = "all"
DISPLAY_ON_OPTIONS: Final = [DISPLAY_ON_FULLY, DISPLAY_ON_ALL]

# Champs d'une tâche (sous-entrée)
CONF_NAME: Final = "name"
CONF_MESSAGE: Final = "message"
CONF_ICON: Final = "icon"
CONF_COLOR: Final = "color"
CONF_DISPLAY_MODE: Final = "display_mode"
CONF_SNOOZE_MINUTES: Final = "snooze_minutes"
CONF_TRIGGER: Final = "trigger"

CONF_DAYS: Final = "days"
CONF_START_TIME: Final = "start_time"
CONF_END_TIME: Final = "end_time"

CONF_CALENDAR: Final = "calendar_entity"
CONF_TITLE_FILTER: Final = "title_filter"

CONF_ENTITY: Final = "entity"
CONF_TARGET_STATE: Final = "target_state"
CONF_DURATION_MINUTES: Final = "duration_minutes"

TRIGGER_SIMPLE: Final = "simple"
TRIGGER_CALENDAR: Final = "calendar"
TRIGGER_DETECTION: Final = "detection"
TRIGGERS: Final = [TRIGGER_SIMPLE, TRIGGER_CALENDAR, TRIGGER_DETECTION]

DISPLAY_MODE_FULLSCREEN: Final = "fullscreen"
DISPLAY_MODES: Final = [DISPLAY_MODE_FULLSCREEN]

WEEKDAYS: Final = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

DEFAULT_ICON: Final = "mdi:clipboard-check-outline"
DEFAULT_COLOR: Final = [21, 101, 192]
DEFAULT_SNOOZE_MINUTES: Final = 15
DEFAULT_DURATION_MINUTES: Final = 30
DEFAULT_TARGET_STATE: Final = "on"

# États exposés par le capteur de chaque tâche
STATE_INACTIVE: Final = "inactive"
STATE_ACTIVE: Final = "active"
STATE_SNOOZED: Final = "snoozed"
STATE_DONE: Final = "done"
TASK_STATES: Final = [STATE_INACTIVE, STATE_ACTIVE, STATE_SNOOZED, STATE_DONE]

SERVICE_ACK: Final = "ack"
SERVICE_SNOOZE: Final = "snooze"
ATTR_TASK_ID: Final = "task_id"
ATTR_MINUTES: Final = "minutes"

SIGNAL_UPDATE: Final = f"{DOMAIN}_update"

FRONTEND_URL: Final = f"/{DOMAIN}/ha-task-popup.js"

# Réévaluation périodique (début de fenêtre, fin de snooze, fin de détection)
TICK_SECONDS: Final = 10
CALENDAR_REFRESH_SECONDS: Final = 60
