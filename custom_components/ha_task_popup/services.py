"""Services ``ha_task_popup.ack`` et ``ha_task_popup.snooze``."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er

from .const import ATTR_MINUTES, ATTR_TASK_ID, DOMAIN, SERVICE_ACK, SERVICE_SNOOZE
from .manager import TaskPopupManager, get_manager

_TARGET = {
    vol.Optional(ATTR_ENTITY_ID): cv.entity_ids,
    vol.Optional(ATTR_TASK_ID): vol.All(cv.ensure_list, [cv.string]),
}
ACK_SCHEMA = vol.All(vol.Schema(_TARGET), cv.has_at_least_one_key(ATTR_ENTITY_ID, ATTR_TASK_ID))
SNOOZE_SCHEMA = vol.All(
    vol.Schema({**_TARGET, vol.Optional(ATTR_MINUTES): vol.All(vol.Coerce(float), vol.Range(min=0.1))}),
    cv.has_at_least_one_key(ATTR_ENTITY_ID, ATTR_TASK_ID),
)


def _resolve(hass: HomeAssistant, call: ServiceCall) -> tuple[TaskPopupManager, list[str]]:
    """Traduit entity_id / task_id en identifiants de tâches."""
    manager = get_manager(hass)
    if manager is None:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="not_loaded")
    task_ids = list(call.data.get(ATTR_TASK_ID, []))
    registry = er.async_get(hass)
    for entity_id in call.data.get(ATTR_ENTITY_ID, []):
        entry = registry.async_get(entity_id)
        if entry is None or entry.platform != DOMAIN or entry.config_subentry_id is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unknown_task",
                translation_placeholders={"task": entity_id},
            )
        task_ids.append(entry.config_subentry_id)
    return manager, list(dict.fromkeys(task_ids))


@callback
def async_register_services(hass: HomeAssistant) -> None:
    """Enregistre les services de l'intégration."""

    @callback
    def handle_ack(call: ServiceCall) -> None:
        manager, task_ids = _resolve(hass, call)
        for task_id in task_ids:
            manager.async_ack(task_id)

    @callback
    def handle_snooze(call: ServiceCall) -> None:
        manager, task_ids = _resolve(hass, call)
        for task_id in task_ids:
            manager.async_snooze(task_id, call.data.get(ATTR_MINUTES))

    hass.services.async_register(DOMAIN, SERVICE_ACK, handle_ack, schema=ACK_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_SNOOZE, handle_snooze, schema=SNOOZE_SCHEMA)
