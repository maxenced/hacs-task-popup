"""Tests du flux de configuration et des sous-entrées « tâche »."""

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.ha_task_popup.const import (
    CONF_CALENDAR,
    CONF_COLOR,
    CONF_DAYS,
    CONF_DISPLAY_MODE,
    CONF_DISPLAY_ON,
    CONF_DURATION_MINUTES,
    CONF_END_TIME,
    CONF_ENTITY,
    CONF_EVERY_WEEKS,
    CONF_FULLY_DEVICES,
    CONF_ICON,
    CONF_MANAGE_SCREEN,
    CONF_MESSAGE,
    CONF_NAME,
    CONF_REFERENCE_DATE,
    CONF_SNOOZE_MINUTES,
    CONF_START_TIME,
    CONF_TARGET_STATE,
    CONF_TITLE_FILTER,
    CONF_TRIGGER,
    DOMAIN,
    SUBENTRY_TYPE_TASK,
)

COMMON = {
    CONF_NAME: "Poubelles",
    CONF_MESSAGE: "Sortir les poubelles",
    CONF_ICON: "mdi:trash-can",
    CONF_COLOR: [200, 40, 40],
    CONF_DISPLAY_MODE: "fullscreen",
    CONF_SNOOZE_MINUTES: 10,
}


async def _create_entry(hass: HomeAssistant):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_FULLY_DEVICES: [], CONF_DISPLAY_ON: "all", CONF_MANAGE_SCREEN: False}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    return result["result"]


async def test_user_flow_single_instance(hass: HomeAssistant) -> None:
    entry = await _create_entry(hass)
    assert entry.options[CONF_DISPLAY_ON] == "all"
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


async def test_options_flow(hass: HomeAssistant) -> None:
    entry = await _create_entry(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_FULLY_DEVICES: [], CONF_DISPLAY_ON: "fully", CONF_MANAGE_SCREEN: True}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options[CONF_DISPLAY_ON] == "fully"


async def test_add_simple_task_then_reconfigure_to_detection(hass: HomeAssistant) -> None:
    entry = await _create_entry(hass)
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_TYPE_TASK), context={"source": config_entries.SOURCE_USER}
    )
    assert result["step_id"] == "user"
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {**COMMON, CONF_TRIGGER: "simple"})
    assert result["step_id"] == "simple"

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {CONF_DAYS: [], CONF_START_TIME: "20:00:00"}
    )
    assert result["errors"] == {CONF_DAYS: "no_days"}
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {CONF_DAYS: ["mon", "thu"], CONF_START_TIME: "20:00:00", CONF_END_TIME: "23:00:00"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    subentry = next(iter(entry.subentries.values()))
    assert subentry.title == "Poubelles"
    assert subentry.data[CONF_DAYS] == ["mon", "thu"]
    assert subentry.data[CONF_EVERY_WEEKS] == 1
    assert subentry.data[CONF_REFERENCE_DATE]
    assert subentry.subentry_id in entry.runtime_data.tasks

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_TYPE_TASK),
        context={"source": config_entries.SOURCE_RECONFIGURE, "subentry_id": subentry.subentry_id},
    )
    assert result["step_id"] == "reconfigure"
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {**COMMON, CONF_NAME: "Chaises", CONF_TRIGGER: "detection"}
    )
    assert result["step_id"] == "detection"
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {CONF_ENTITY: "input_boolean.menage", CONF_TARGET_STATE: "on", CONF_DURATION_MINUTES: 20},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()

    subentry = entry.subentries[subentry.subentry_id]
    assert subentry.title == "Chaises"
    # Les champs de l'ancien déclencheur ont disparu
    assert CONF_DAYS not in subentry.data
    assert CONF_EVERY_WEEKS not in subentry.data
    assert subentry.data[CONF_ENTITY] == "input_boolean.menage"


async def test_add_task_every_two_weeks(hass: HomeAssistant) -> None:
    entry = await _create_entry(hass)
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_TYPE_TASK), context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {**COMMON, CONF_TRIGGER: "simple"})
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {CONF_DAYS: ["tue"], CONF_START_TIME: "19:00:00", CONF_EVERY_WEEKS: 2.0, CONF_REFERENCE_DATE: "2026-10-13"},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    subentry = next(iter(entry.subentries.values()))
    assert subentry.data[CONF_EVERY_WEEKS] == 2
    assert subentry.data[CONF_REFERENCE_DATE] == "2026-10-13"


async def test_add_calendar_task(hass: HomeAssistant) -> None:
    entry = await _create_entry(hass)
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_TYPE_TASK), context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {**COMMON, CONF_TRIGGER: "calendar"}
    )
    assert result["step_id"] == "calendar"
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {CONF_CALENDAR: "calendar.maison", CONF_TITLE_FILTER: "poubelle"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
