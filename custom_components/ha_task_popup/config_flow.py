"""Configuration par l'interface : entrée principale + une sous-entrée par tâche."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    OptionsFlow,
    SubentryFlowResult,
)
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_CALENDAR,
    CONF_COLOR,
    CONF_DAYS,
    CONF_DISPLAY_MODE,
    CONF_DISPLAY_ON,
    CONF_DURATION_MINUTES,
    CONF_END_TIME,
    CONF_ENTITY,
    CONF_FULLY_DEVICES,
    CONF_ICON,
    CONF_MANAGE_SCREEN,
    CONF_MAX_BRIGHTNESS,
    CONF_MESSAGE,
    CONF_NAME,
    CONF_SNOOZE_MINUTES,
    CONF_START_TIME,
    CONF_TARGET_STATE,
    CONF_TITLE_FILTER,
    CONF_TRIGGER,
    DEFAULT_COLOR,
    DEFAULT_DURATION_MINUTES,
    DEFAULT_ICON,
    DEFAULT_SNOOZE_MINUTES,
    DEFAULT_TARGET_STATE,
    DISPLAY_MODE_FULLSCREEN,
    DISPLAY_MODES,
    DISPLAY_ON_FULLY,
    DISPLAY_ON_OPTIONS,
    DOMAIN,
    SUBENTRY_TYPE_TASK,
    TRIGGER_CALENDAR,
    TRIGGER_DETECTION,
    TRIGGER_SIMPLE,
    TRIGGERS,
    WEEKDAYS,
)

TRIGGER_FIELDS = {
    TRIGGER_SIMPLE: (CONF_DAYS, CONF_START_TIME, CONF_END_TIME),
    TRIGGER_CALENDAR: (CONF_CALENDAR, CONF_TITLE_FILTER),
    TRIGGER_DETECTION: (CONF_ENTITY, CONF_TARGET_STATE, CONF_DURATION_MINUTES),
}


def _select(options: list[str], key: str, multiple: bool = False) -> selector.SelectSelector:
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=options,
            translation_key=key,
            multiple=multiple,
            mode=selector.SelectSelectorMode.LIST,
        )
    )


def _minutes(minimum: float = 1) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=minimum, max=1440, step=1, unit_of_measurement="min", mode=selector.NumberSelectorMode.BOX
        )
    )


def _settings_schema(values: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Optional(CONF_FULLY_DEVICES, default=values.get(CONF_FULLY_DEVICES, [])): selector.DeviceSelector(
                selector.DeviceSelectorConfig(integration="fully_kiosk", multiple=True)
            ),
            vol.Required(CONF_DISPLAY_ON, default=values.get(CONF_DISPLAY_ON, DISPLAY_ON_FULLY)): _select(
                DISPLAY_ON_OPTIONS, CONF_DISPLAY_ON
            ),
            vol.Required(CONF_MANAGE_SCREEN, default=values.get(CONF_MANAGE_SCREEN, True)): bool,
            vol.Required(CONF_MAX_BRIGHTNESS, default=values.get(CONF_MAX_BRIGHTNESS, False)): bool,
        }
    )


class TaskPopupConfigFlow(ConfigFlow, domain=DOMAIN):
    """Création de l'entrée principale (une seule)."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Choix de la tablette et du mode d'affichage."""
        if user_input is not None:
            return self.async_create_entry(title="Tâches", data={}, options=user_input)
        return self.async_show_form(step_id="user", data_schema=_settings_schema({}))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Options : mêmes champs que la création."""
        return TaskPopupOptionsFlow()

    @classmethod
    @callback
    def async_get_supported_subentry_types(cls, config_entry: ConfigEntry) -> dict[str, type[ConfigSubentryFlow]]:
        """Une sous-entrée par tâche."""
        return {SUBENTRY_TYPE_TASK: TaskSubentryFlow}


class TaskPopupOptionsFlow(OptionsFlow):
    """Modification des réglages généraux."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Formulaire unique."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        return self.async_show_form(step_id="init", data_schema=_settings_schema(dict(self.config_entry.options)))


class TaskSubentryFlow(ConfigSubentryFlow):
    """Ajout / modification d'une tâche en deux étapes : commun puis déclencheur."""

    def __init__(self) -> None:
        """Initialise."""
        self._data: dict[str, Any] = {}

    def _is_reconfigure(self) -> bool:
        return self.source == "reconfigure"

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        """Nouvelle tâche."""
        return await self._async_step_common(user_input)

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        """Modification d'une tâche existante."""
        if not self._data:
            self._data = dict(self._get_reconfigure_subentry().data)
        return await self._async_step_common(user_input, step_id="reconfigure")

    async def _async_step_common(self, user_input: dict[str, Any] | None, step_id: str = "user") -> SubentryFlowResult:
        if user_input is not None:
            # On ne garde que les champs du déclencheur choisi.
            kept = {
                key: value
                for key, value in self._data.items()
                if key in TRIGGER_FIELDS.get(user_input[CONF_TRIGGER], ())
            }
            self._data = {**kept, **user_input}
            return await getattr(self, f"async_step_{user_input[CONF_TRIGGER]}")()

        values = self._data
        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=values.get(CONF_NAME, "")): selector.TextSelector(),
                vol.Required(CONF_MESSAGE, default=values.get(CONF_MESSAGE, "")): selector.TextSelector(
                    selector.TextSelectorConfig(multiline=True)
                ),
                vol.Optional(CONF_ICON, default=values.get(CONF_ICON, DEFAULT_ICON)): selector.IconSelector(),
                vol.Required(CONF_COLOR, default=values.get(CONF_COLOR, DEFAULT_COLOR)): selector.ColorRGBSelector(),
                vol.Required(
                    CONF_DISPLAY_MODE, default=values.get(CONF_DISPLAY_MODE, DISPLAY_MODE_FULLSCREEN)
                ): _select(DISPLAY_MODES, CONF_DISPLAY_MODE),
                vol.Required(
                    CONF_SNOOZE_MINUTES, default=values.get(CONF_SNOOZE_MINUTES, DEFAULT_SNOOZE_MINUTES)
                ): _minutes(),
                vol.Required(CONF_TRIGGER, default=values.get(CONF_TRIGGER, TRIGGER_SIMPLE)): _select(
                    TRIGGERS, CONF_TRIGGER
                ),
            }
        )
        return self.async_show_form(step_id=step_id, data_schema=schema)

    async def async_step_simple(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        """Jours + heure de départ (+ heure de fin optionnelle)."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input.get(CONF_DAYS):
                errors[CONF_DAYS] = "no_days"
            else:
                self._data.pop(CONF_END_TIME, None)
                return self._async_finish(user_input)
        values = {**self._data, **(user_input or {})}
        end_key = vol.Optional(CONF_END_TIME, description={"suggested_value": values.get(CONF_END_TIME)})
        schema = vol.Schema(
            {
                vol.Required(CONF_DAYS, default=values.get(CONF_DAYS, [])): _select(WEEKDAYS, CONF_DAYS, multiple=True),
                vol.Required(CONF_START_TIME, default=values.get(CONF_START_TIME, "20:00:00")): selector.TimeSelector(),
                end_key: selector.TimeSelector(),
            }
        )
        return self.async_show_form(step_id="simple", data_schema=schema, errors=errors)

    async def async_step_calendar(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        """Entité calendrier + filtre optionnel sur le titre."""
        if user_input is not None:
            self._data.pop(CONF_TITLE_FILTER, None)
            return self._async_finish(user_input)
        values = self._data
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_CALENDAR, description={"suggested_value": values.get(CONF_CALENDAR)}
                ): selector.EntitySelector(selector.EntitySelectorConfig(domain="calendar")),
                vol.Optional(
                    CONF_TITLE_FILTER, description={"suggested_value": values.get(CONF_TITLE_FILTER)}
                ): selector.TextSelector(),
            }
        )
        return self.async_show_form(step_id="calendar", data_schema=schema)

    async def async_step_detection(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        """Entité surveillée + état cible + durée d'affichage."""
        if user_input is not None:
            return self._async_finish(user_input)
        values = self._data
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_ENTITY, description={"suggested_value": values.get(CONF_ENTITY)}
                ): selector.EntitySelector(),
                vol.Required(
                    CONF_TARGET_STATE, default=values.get(CONF_TARGET_STATE, DEFAULT_TARGET_STATE)
                ): selector.TextSelector(),
                vol.Required(
                    CONF_DURATION_MINUTES, default=values.get(CONF_DURATION_MINUTES, DEFAULT_DURATION_MINUTES)
                ): _minutes(),
            }
        )
        return self.async_show_form(step_id="detection", data_schema=schema)

    @callback
    def _async_finish(self, user_input: dict[str, Any]) -> SubentryFlowResult:
        data = {**self._data, **user_input}
        title = data[CONF_NAME]
        if self._is_reconfigure():
            return self.async_update_and_abort(
                self._get_entry(), self._get_reconfigure_subentry(), title=title, data=data
            )
        return self.async_create_entry(title=title, data=data)
