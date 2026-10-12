"""Tests d'intégration (gestionnaire, entités, services, websocket, écran)."""

from datetime import datetime, timedelta
from types import MappingProxyType

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    async_mock_service,
)

from custom_components.ha_task_popup.const import (
    CONF_CALENDAR,
    CONF_COLOR,
    CONF_DAYS,
    CONF_DISPLAY_ON,
    CONF_DURATION_MINUTES,
    CONF_ENTITY,
    CONF_FULLY_DEVICES,
    CONF_MANAGE_SCREEN,
    CONF_MESSAGE,
    CONF_NAME,
    CONF_SNOOZE_MINUTES,
    CONF_START_TIME,
    CONF_TARGET_STATE,
    CONF_TITLE_FILTER,
    CONF_TRIGGER,
    DOMAIN,
    SUBENTRY_TYPE_TASK,
    TRIGGER_CALENDAR,
    TRIGGER_DETECTION,
    TRIGGER_SIMPLE,
)

SIMPLE = {
    CONF_NAME: "Poubelles",
    CONF_MESSAGE: "Sortir les poubelles",
    CONF_COLOR: [200, 40, 40],
    CONF_SNOOZE_MINUTES: 10,
    CONF_TRIGGER: TRIGGER_SIMPLE,
    CONF_DAYS: ["mon"],
    CONF_START_TIME: "20:00:00",
}
DETECTION = {
    CONF_NAME: "Chaises",
    CONF_MESSAGE: "Chaises sur la table",
    CONF_SNOOZE_MINUTES: 5,
    CONF_TRIGGER: TRIGGER_DETECTION,
    CONF_ENTITY: "input_boolean.menage",
    CONF_TARGET_STATE: "on",
    CONF_DURATION_MINUTES: 30,
}


def _entry(options=None, tasks=(("simple", SIMPLE),)) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Tâches",
        options=options or {CONF_DISPLAY_ON: "fully", CONF_MANAGE_SCREEN: True, CONF_FULLY_DEVICES: []},
        subentries_data=[
            ConfigSubentryData(
                data=MappingProxyType(data),
                subentry_id=sub_id,
                subentry_type=SUBENTRY_TYPE_TASK,
                title=data[CONF_NAME],
                unique_id=None,
            )
            for sub_id, data in tasks
        ],
    )


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def _local(year, month, day, hour, minute=0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=dt_util.get_default_time_zone())


def _entity(hass: HomeAssistant, domain: str, unique_id: str) -> str:
    return er.async_get(hass).async_get_entity_id(domain, DOMAIN, unique_id)


@pytest.fixture
async def tz(hass: HomeAssistant):
    await hass.config.async_set_time_zone("Europe/Paris")


async def test_simple_task_lifecycle(hass: HomeAssistant, freezer: FrozenDateTimeFactory, tz) -> None:
    """Inactive → active à l'heure → snooze → revient → fait."""
    freezer.move_to(_local(2026, 10, 12, 19, 0))  # lundi
    await _setup(hass, _entry())
    sensor = _entity(hass, "sensor", "simple_state")
    assert hass.states.get(sensor).state == "inactive"

    freezer.move_to(_local(2026, 10, 12, 20, 0))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(sensor).state == "active"

    await hass.services.async_call(DOMAIN, "snooze", {"entity_id": sensor}, blocking=True)
    assert hass.states.get(sensor).state == "snoozed"

    freezer.tick(timedelta(minutes=11))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(sensor).state == "active"

    ack = _entity(hass, "button", "simple_ack")
    await hass.services.async_call("button", "press", {"entity_id": ack}, blocking=True)
    assert hass.states.get(sensor).state == "done"

    # Reste faite le lendemain, se réactive le lundi suivant
    freezer.move_to(_local(2026, 10, 13, 9, 0))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(sensor).state == "done"
    freezer.move_to(_local(2026, 10, 19, 20, 1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(sensor).state == "active"


async def test_detection_and_websocket(hass: HomeAssistant, freezer: FrozenDateTimeFactory, hass_ws_client) -> None:
    """La détection ouvre une fenêtre limitée ; le websocket reçoit la file."""
    hass.states.async_set("input_boolean.menage", "off")
    entry = _entry(tasks=(("detect", DETECTION), ("simple", SIMPLE)))
    await _setup(hass, entry)
    manager = entry.runtime_data

    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": f"{DOMAIN}/subscribe"})
    assert (await client.receive_json())["success"]
    first = await client.receive_json()
    assert first["event"]["tasks"] == []

    hass.states.async_set("input_boolean.menage", "on")
    await hass.async_block_till_done()
    assert manager.runtimes["detect"].state == "active"
    event = await client.receive_json()
    assert [task["id"] for task in event["event"]["tasks"]] == ["detect"]
    assert event["event"]["tasks"][0]["message"] == "Chaises sur la table"

    freezer.tick(timedelta(minutes=31))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert manager.runtimes["detect"].state == "inactive"
    event = await client.receive_json()
    assert event["event"]["tasks"] == []


async def test_detection_ignores_unavailable(hass: HomeAssistant) -> None:
    hass.states.async_set("input_boolean.menage", "unavailable")
    entry = _entry(tasks=(("detect", DETECTION),))
    await _setup(hass, entry)
    hass.states.async_set("input_boolean.menage", "on")
    await hass.async_block_till_done()
    assert entry.runtime_data.runtimes["detect"].state == "inactive"


async def test_ack_by_task_id_and_unknown(hass: HomeAssistant) -> None:
    hass.states.async_set("input_boolean.menage", "off")
    entry = _entry(tasks=(("detect", DETECTION),))
    await _setup(hass, entry)
    hass.states.async_set("input_boolean.menage", "on")
    await hass.async_block_till_done()
    await hass.services.async_call(DOMAIN, "ack", {"task_id": "detect"}, blocking=True)
    assert entry.runtime_data.runtimes["detect"].state == "done"
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "ack", {"task_id": "nope"}, blocking=True)


async def test_screen_management(hass: HomeAssistant) -> None:
    """L'écran est allumé, la veille désactivée puis restaurée."""
    fully_entry = MockConfigEntry(domain="fully_kiosk")
    fully_entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=fully_entry.entry_id, identifiers={("fully_kiosk", "abc-123")}
    )
    ent_reg = er.async_get(hass)
    switch = ent_reg.async_get_or_create(
        "switch", "fully_kiosk", "abc-123-screenOn", device_id=device.id, config_entry=fully_entry
    )
    timer = ent_reg.async_get_or_create(
        "number", "fully_kiosk", "abc-123-timeToScreenOffV2", device_id=device.id, config_entry=fully_entry
    )
    hass.states.async_set(switch.entity_id, "off")
    hass.states.async_set(timer.entity_id, "30")
    turn_on = async_mock_service(hass, "switch", "turn_on")
    set_value = async_mock_service(hass, "number", "set_value")

    hass.states.async_set("input_boolean.menage", "off")
    entry = _entry(
        options={CONF_DISPLAY_ON: "fully", CONF_MANAGE_SCREEN: True, CONF_FULLY_DEVICES: [device.id]},
        tasks=(("detect", DETECTION),),
    )
    await _setup(hass, entry)
    assert entry.runtime_data.frontend_payload()["fully_ids"] == ["abc-123"]

    hass.states.async_set("input_boolean.menage", "on")
    await hass.async_block_till_done()
    assert len(turn_on) == 1
    assert set_value[-1].data["value"] == 0

    await hass.services.async_call(DOMAIN, "ack", {"task_id": "detect"}, blocking=True)
    await hass.async_block_till_done()
    assert set_value[-1].data["value"] == 30
    assert not entry.runtime_data.screen.holding


async def test_unload(hass: HomeAssistant) -> None:
    entry = _entry()
    await _setup(hass, entry)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert DOMAIN not in hass.data or "manager" not in hass.data[DOMAIN]


async def test_calendar_task(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    """Active pendant un événement dont le titre correspond au filtre."""
    now = dt_util.now()
    events = [
        {
            "summary": "Poubelle jaune",
            "start": (now - timedelta(hours=1)).isoformat(),
            "end": (now + timedelta(hours=1)).isoformat(),
        },
        {
            "summary": "Dentiste",
            "start": (now - timedelta(hours=1)).isoformat(),
            "end": (now + timedelta(hours=3)).isoformat(),
        },
    ]
    async_mock_service(
        hass,
        "calendar",
        "get_events",
        response={"calendar.maison": {"events": events}},
        supports_response=SupportsResponse.ONLY,
    )
    hass.states.async_set("calendar.maison", "on")
    entry = _entry(
        tasks=(
            (
                "cal",
                {
                    **SIMPLE,
                    CONF_TRIGGER: TRIGGER_CALENDAR,
                    CONF_CALENDAR: "calendar.maison",
                    CONF_TITLE_FILTER: "poubelle",
                },
            ),
        )
    )
    await _setup(hass, entry)
    runtime = entry.runtime_data.runtimes["cal"]
    assert runtime.state == "active"
    assert runtime.window.end == datetime.fromisoformat(events[0]["end"])

    freezer.tick(timedelta(hours=1, seconds=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert runtime.state == "inactive"
