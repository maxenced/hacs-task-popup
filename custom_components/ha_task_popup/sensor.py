"""Capteur d'état de chaque tâche."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_MESSAGE, TASK_STATES
from .entity import TaskEntity
from .manager import TaskDef, TaskPopupManager


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    """Un capteur par tâche."""
    manager: TaskPopupManager = entry.runtime_data
    for task_id, task in manager.tasks.items():
        async_add_entities([TaskStateSensor(manager, task)], config_subentry_id=task_id)


class TaskStateSensor(TaskEntity, SensorEntity):
    """État : inactive / active / snoozed / done."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = TASK_STATES

    def __init__(self, manager: TaskPopupManager, task: TaskDef) -> None:
        """Initialise."""
        super().__init__(manager, task, "state")

    @property
    def native_value(self) -> str:
        return self.manager.runtimes[self.task.task_id].state

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        runtime = self.manager.runtimes[self.task.task_id]
        window = runtime.window
        return {
            "task_id": self.task.task_id,
            "trigger": self.task.trigger,
            "message": self.task.data.get(CONF_MESSAGE, ""),
            "window_start": window.start.isoformat() if window else None,
            "window_end": window.end.isoformat() if window and window.end else None,
            "snoozed_until": runtime.snoozed_until.isoformat() if runtime.snoozed_until else None,
        }
