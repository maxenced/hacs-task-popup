"""Pilotage de l'écran des tablettes Fully Kiosk via l'intégration fully_kiosk."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

_LOGGER = logging.getLogger(__name__)

FULLY_DOMAIN = "fully_kiosk"
# Suffixes des unique_id des entités créées par l'intégration fully_kiosk
SCREEN_SWITCH_SUFFIX = "-screenOn"
SCREEN_OFF_TIMER_SUFFIX = "-timeToScreenOffV2"


def fully_device_ids(hass: HomeAssistant, device_ids: list[str]) -> list[str]:
    """Retourne les identifiants Fully (``fully.getDeviceId()``) des appareils HA."""
    registry = dr.async_get(hass)
    result = []
    for device_id in device_ids:
        device = registry.async_get(device_id)
        if device is None:
            continue
        result.extend(ident for domain, ident in device.identifiers if domain == FULLY_DOMAIN)
    return result


def _find_entity(hass: HomeAssistant, device_id: str, domain: str, suffix: str) -> str | None:
    registry = er.async_get(hass)
    for entry in er.async_entries_for_device(registry, device_id):
        if entry.domain == domain and entry.unique_id.endswith(suffix):
            return entry.entity_id
    return None


class ScreenManager:
    """Allume l'écran et le garde allumé tant qu'une tâche est affichée.

    Le minuteur de mise en veille de Fully est mis à 0 (jamais) pendant
    l'affichage, puis restauré : l'écran s'éteint ensuite naturellement.
    """

    def __init__(self, hass: HomeAssistant, device_ids: list[str], saved: dict[str, Any]) -> None:
        """Initialise. ``saved`` est persisté par le gestionnaire."""
        self.hass = hass
        self.device_ids = device_ids
        # {device_id: valeur du minuteur avant affichage}
        self.saved = saved

    @property
    def holding(self) -> bool:
        """Vrai si l'écran est actuellement maintenu allumé."""
        return bool(self.saved)

    async def async_show(self) -> None:
        """Allume l'écran (nouvelle tâche affichée) et bloque la mise en veille."""
        for device_id in self.device_ids:
            switch = _find_entity(self.hass, device_id, "switch", SCREEN_SWITCH_SUFFIX)
            timer = _find_entity(self.hass, device_id, "number", SCREEN_OFF_TIMER_SUFFIX)
            if timer and device_id not in self.saved:
                state = self.hass.states.get(timer)
                try:
                    value = float(state.state) if state else None
                except ValueError:
                    value = None
                if value is not None and value > 0:
                    self.saved[device_id] = value
                    await self._call("number", "set_value", timer, {"value": 0})
            if switch:
                await self._call("switch", "turn_on", switch)

    async def async_release(self) -> None:
        """Restaure le minuteur de mise en veille."""
        for device_id, value in list(self.saved.items()):
            timer = _find_entity(self.hass, device_id, "number", SCREEN_OFF_TIMER_SUFFIX)
            if timer:
                await self._call("number", "set_value", timer, {"value": value})
            self.saved.pop(device_id, None)

    async def _call(self, domain: str, service: str, entity_id: str, data: dict[str, Any] | None = None) -> None:
        try:
            await self.hass.services.async_call(
                domain,
                service,
                {"entity_id": entity_id, **(data or {})},
                blocking=True,
            )
        except (HomeAssistantError, ValueError) as err:
            _LOGGER.warning("Échec de %s.%s sur %s : %s", domain, service, entity_id, err)
