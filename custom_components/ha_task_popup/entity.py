"""Entité de base rattachée à une tâche (un appareil par tâche)."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, SIGNAL_UPDATE
from .manager import TaskDef, TaskPopupManager


class TaskEntity(Entity):
    """Entité d'une tâche, mise à jour par le gestionnaire."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, manager: TaskPopupManager, task: TaskDef, key: str) -> None:
        """Initialise."""
        self.manager = manager
        self.task = task
        self._attr_unique_id = f"{task.task_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, task.task_id)},
            name=task.name,
            manufacturer="HA Task Popup",
            model="Tâche",
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_added_to_hass(self) -> None:
        """S'abonne aux mises à jour."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{SIGNAL_UPDATE}_{self.manager.entry.entry_id}",
                self.async_write_ha_state,
            )
        )
