"""Boutons « Fait » et « Snooze » de chaque tâche."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import TaskEntity
from .manager import TaskDef, TaskPopupManager


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    """Deux boutons par tâche."""
    manager: TaskPopupManager = entry.runtime_data
    for task_id, task in manager.tasks.items():
        async_add_entities(
            [AckButton(manager, task), SnoozeButton(manager, task)],
            config_subentry_id=task_id,
        )


class AckButton(TaskEntity, ButtonEntity):
    """Marque la tâche comme faite."""

    def __init__(self, manager: TaskPopupManager, task: TaskDef) -> None:
        """Initialise."""
        super().__init__(manager, task, "ack")

    async def async_press(self) -> None:
        self.manager.async_ack(self.task.task_id)


class SnoozeButton(TaskEntity, ButtonEntity):
    """Reporte la tâche de sa durée de snooze."""

    def __init__(self, manager: TaskPopupManager, task: TaskDef) -> None:
        """Initialise."""
        super().__init__(manager, task, "snooze")

    async def async_press(self) -> None:
        self.manager.async_snooze(self.task.task_id)
