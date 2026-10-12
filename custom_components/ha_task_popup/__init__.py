"""HA Task Popup : tâches affichées en plein écran sur la tablette."""

from __future__ import annotations

from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, FRONTEND_URL
from .manager import TaskPopupManager, notify_frontend
from .services import async_register_services
from .websocket import async_register_websocket

PLATFORMS = [Platform.BUTTON, Platform.SENSOR]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

VERSION = "0.1.0"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Enregistre le module JS global, le websocket et les services."""
    hass.data.setdefault(DOMAIN, {})
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                FRONTEND_URL,
                str(Path(__file__).parent / "frontend" / "ha-task-popup.js"),
                cache_headers=False,
            )
        ]
    )
    add_extra_js_url(hass, f"{FRONTEND_URL}?v={VERSION}")
    async_register_websocket(hass)
    async_register_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Démarre le gestionnaire de tâches."""
    manager = TaskPopupManager(hass, entry)
    hass.data[DOMAIN]["manager"] = manager
    entry.runtime_data = manager
    await manager.async_start()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Arrête le gestionnaire."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        manager: TaskPopupManager = entry.runtime_data
        await manager.async_stop()
        if hass.data[DOMAIN].get("manager") is manager:
            hass.data[DOMAIN].pop("manager")
        notify_frontend(hass)
    return unloaded


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Recharge après modification des options ou des tâches."""
    await hass.config_entries.async_reload(entry.entry_id)
