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
SCREEN_BRIGHTNESS_SUFFIX = "-screenBrightness"
# Réglage Fully restauré à vide (luminosité système) si la valeur d'origine est inconnue
SCREEN_BRIGHTNESS_SETTING = "screenBrightness"
MAX_BRIGHTNESS = 255


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
    En option, la luminosité est poussée au maximum puis restaurée.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        device_ids: list[str],
        *,
        wake: bool = True,
        max_brightness: bool = False,
    ) -> None:
        """Initialise. ``saved`` et ``saved_brightness`` sont persistés par le gestionnaire."""
        self.hass = hass
        self.device_ids = device_ids
        self.wake = wake
        self.max_brightness = max_brightness
        # {device_id: valeur du minuteur avant affichage}
        self.saved: dict[str, float] = {}
        # {device_id: luminosité avant affichage, None si inconnue}
        self.saved_brightness: dict[str, float | None] = {}

    @property
    def enabled(self) -> bool:
        """Vrai si l'écran des tablettes est piloté."""
        return bool(self.device_ids) and (self.wake or self.max_brightness)

    @property
    def holding(self) -> bool:
        """Vrai si l'écran est actuellement maintenu allumé ou forcé en luminosité."""
        return bool(self.saved) or bool(self.saved_brightness)

    def _value(self, entity_id: str) -> float | None:
        state = self.hass.states.get(entity_id)
        try:
            return float(state.state) if state else None
        except ValueError:
            return None

    async def async_show(self) -> None:
        """Allume l'écran (nouvelle tâche affichée), bloque la veille, force la luminosité."""
        for device_id in self.device_ids:
            if self.max_brightness:
                await self._async_max_brightness(device_id)
            if not self.wake:
                continue
            switch = _find_entity(self.hass, device_id, "switch", SCREEN_SWITCH_SUFFIX)
            timer = _find_entity(self.hass, device_id, "number", SCREEN_OFF_TIMER_SUFFIX)
            if timer and device_id not in self.saved:
                value = self._value(timer)
                if value is not None and value > 0:
                    self.saved[device_id] = value
                    await self._call("number", "set_value", timer, {"value": 0})
            if switch:
                await self._call("switch", "turn_on", switch)

    async def _async_max_brightness(self, device_id: str) -> None:
        brightness = _find_entity(self.hass, device_id, "number", SCREEN_BRIGHTNESS_SUFFIX)
        if not brightness:
            return
        if device_id not in self.saved_brightness:
            self.saved_brightness[device_id] = self._value(brightness)
        await self._call("number", "set_value", brightness, {"value": MAX_BRIGHTNESS})

    async def async_release(self) -> None:
        """Restaure le minuteur de mise en veille et la luminosité."""
        for device_id, value in list(self.saved.items()):
            timer = _find_entity(self.hass, device_id, "number", SCREEN_OFF_TIMER_SUFFIX)
            if timer:
                await self._call("number", "set_value", timer, {"value": value})
            self.saved.pop(device_id, None)
        for device_id, value in list(self.saved_brightness.items()):
            brightness = _find_entity(self.hass, device_id, "number", SCREEN_BRIGHTNESS_SUFFIX)
            if brightness and value is not None:
                await self._call("number", "set_value", brightness, {"value": value})
            elif brightness:
                # Luminosité d'origine inconnue (réglage Fully vide) : retour à la luminosité système.
                await self._call_service(
                    FULLY_DOMAIN,
                    "set_config",
                    {"device_id": [device_id], "key": SCREEN_BRIGHTNESS_SETTING, "value": ""},
                    brightness,
                )
            self.saved_brightness.pop(device_id, None)

    async def _call(self, domain: str, service: str, entity_id: str, data: dict[str, Any] | None = None) -> None:
        await self._call_service(domain, service, {"entity_id": entity_id, **(data or {})}, entity_id)

    async def _call_service(self, domain: str, service: str, data: dict[str, Any], target: str) -> None:
        try:
            await self.hass.services.async_call(domain, service, data, blocking=True)
        except (HomeAssistantError, ValueError) as err:
            _LOGGER.warning("Échec de %s.%s sur %s : %s", domain, service, target, err)
