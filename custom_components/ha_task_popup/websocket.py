"""Commande websocket utilisée par le module JS pour suivre la file des tâches."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN
from .manager import empty_payload, frontend_listeners, get_manager


@callback
def async_register_websocket(hass: HomeAssistant) -> None:
    """Enregistre ``ha_task_popup/subscribe``."""
    websocket_api.async_register_command(hass, ws_subscribe)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/subscribe"})
@callback
def ws_subscribe(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """Envoie la file des tâches à afficher, puis chaque mise à jour."""
    msg_id = msg["id"]

    @callback
    def forward(payload: dict[str, Any]) -> None:
        connection.send_message(websocket_api.event_message(msg_id, payload))

    listeners = frontend_listeners(hass)
    listeners.add(forward)

    @callback
    def unsubscribe() -> None:
        listeners.discard(forward)

    connection.subscriptions[msg_id] = unsubscribe
    connection.send_result(msg_id)
    manager = get_manager(hass)
    forward(manager.frontend_payload() if manager else empty_payload())
