"""Tests de la logique pure (fenêtres et machine à états)."""

from datetime import UTC, datetime, time, timedelta

from custom_components.ha_task_popup.const import (
    STATE_ACTIVE,
    STATE_DONE,
    STATE_INACTIVE,
    STATE_SNOOZED,
)
from custom_components.ha_task_popup.logic import (
    TaskRuntime,
    Window,
    acknowledge,
    calendar_window,
    detection_window,
    evaluate,
    parse_calendar_events,
    simple_window,
    snooze,
)

# Lundi 12 octobre 2026
MON = datetime(2026, 10, 12, 0, 0, tzinfo=UTC)


def at(day_offset: int, hour: int, minute: int = 0) -> datetime:
    return MON + timedelta(days=day_offset, hours=hour, minutes=minute)


class TestSimpleWindow:
    def test_closed_before_start(self):
        assert simple_window(at(0, 19), ["mon"], time(20), None, since=at(0, 0)) is None

    def test_open_after_start_until_done(self):
        win = simple_window(at(1, 9), ["mon"], time(20), None)
        assert win is not None
        assert win.start == at(0, 20)
        assert win.end is None

    def test_new_occurrence_replaces_previous(self):
        win = simple_window(at(2, 21), ["mon", "wed"], time(20), None)
        assert win.start == at(2, 20)

    def test_end_time_closes_window(self):
        assert simple_window(at(0, 22), ["mon"], time(20), time(21)) is None
        win = simple_window(at(0, 20, 30), ["mon"], time(20), time(21))
        assert win.end == at(0, 21)

    def test_end_time_past_midnight(self):
        win = simple_window(at(1, 0, 30), ["mon"], time(22), time(1))
        assert win is not None
        assert win.end == at(1, 1)

    def test_ignores_occurrences_before_creation(self):
        assert simple_window(at(1, 9), ["mon"], time(20), None, since=at(1, 8)) is None
        assert simple_window(at(7, 21), ["mon"], time(20), None, since=at(1, 8)) is not None

    def test_no_days(self):
        assert simple_window(at(0, 21), [], time(20), None) is None

    def test_every_two_weeks_follows_reference_week(self):
        # Semaine de référence : celle du mercredi 14 octobre (lundi 12).
        ref = (MON + timedelta(days=2)).date()
        assert simple_window(at(0, 21), ["mon"], time(20), time(22), every_weeks=2, reference=ref) is not None
        assert simple_window(at(7, 21), ["mon"], time(20), time(22), every_weeks=2, reference=ref) is None
        assert simple_window(at(14, 21), ["mon"], time(20), time(22), every_weeks=2, reference=ref) is not None
        # Aussi avant la date de référence.
        assert simple_window(at(-14, 21), ["mon"], time(20), time(22), every_weeks=2, reference=ref) is not None
        assert simple_window(at(-7, 21), ["mon"], time(20), time(22), every_weeks=2, reference=ref) is None

    def test_every_three_weeks_keeps_last_occurrence_open(self):
        ref = MON.date()
        # Sans heure de fin, l'occurrence du lundi reste ouverte pendant les semaines inactives.
        win = simple_window(at(16, 9), ["mon"], time(20), None, every_weeks=3, reference=ref)
        assert win is not None
        assert win.start == at(0, 20)
        win = simple_window(at(21, 21), ["mon"], time(20), None, every_weeks=3, reference=ref)
        assert win.start == at(21, 20)

    def test_every_weeks_ignored_without_reference(self):
        assert simple_window(at(7, 21), ["mon"], time(20), time(22), every_weeks=2) is not None


class TestCalendarWindow:
    def test_filter_and_ongoing(self):
        events = parse_calendar_events(
            [
                {"summary": "Poubelle jaune", "start": at(0, 18).isoformat(), "end": at(0, 23).isoformat()},
                {"summary": "Dentiste", "start": at(0, 17).isoformat(), "end": at(0, 23).isoformat()},
            ],
            UTC,
        )
        win = calendar_window(at(0, 19), events, "poubelle")
        assert win.start == at(0, 18)
        assert win.end == at(0, 23)
        assert calendar_window(at(0, 23, 30), events, "poubelle") is None

    def test_all_day_event(self):
        events = parse_calendar_events([{"summary": "Ménage", "start": "2026-10-12", "end": "2026-10-13"}], UTC)
        assert calendar_window(at(0, 10), events, None) is not None
        assert calendar_window(at(1, 10), events, None) is None

    def test_invalid_events_ignored(self):
        assert parse_calendar_events([{"summary": "x"}], UTC) == []


class TestDetectionWindow:
    def test_duration(self):
        trig = at(0, 10)
        assert detection_window(at(0, 10, 20), trig, timedelta(minutes=30)) is not None
        assert detection_window(at(0, 10, 30), trig, timedelta(minutes=30)) is None
        assert detection_window(at(0, 10), None, timedelta(minutes=30)) is None


class TestStateMachine:
    win = Window(key="k1", start=at(0, 20), end=at(0, 23))

    def test_inactive_without_window(self):
        rt = TaskRuntime()
        assert evaluate(rt, None, at(0, 10)) == STATE_INACTIVE

    def test_active_then_done(self):
        rt = TaskRuntime()
        assert evaluate(rt, self.win, at(0, 20)) == STATE_ACTIVE
        assert rt.active_since == at(0, 20)
        assert acknowledge(rt)
        assert evaluate(rt, self.win, at(0, 21)) == STATE_DONE
        assert evaluate(rt, None, at(0, 23)) == STATE_INACTIVE

    def test_snooze_comes_back(self):
        rt = TaskRuntime()
        evaluate(rt, self.win, at(0, 20))
        assert snooze(rt, at(0, 20), 15)
        assert evaluate(rt, self.win, at(0, 20, 10)) == STATE_SNOOZED
        assert evaluate(rt, self.win, at(0, 20, 15)) == STATE_ACTIVE
        # Revenue en fin de file
        assert rt.active_since == at(0, 20, 15)

    def test_snooze_past_window_end_goes_inactive(self):
        rt = TaskRuntime()
        evaluate(rt, self.win, at(0, 22, 50))
        snooze(rt, at(0, 22, 50), 30)
        assert evaluate(rt, self.win, at(0, 23, 5)) == STATE_INACTIVE

    def test_new_window_resets_done(self):
        rt = TaskRuntime()
        evaluate(rt, self.win, at(0, 20))
        acknowledge(rt)
        nxt = Window(key="k2", start=at(1, 20), end=None)
        assert evaluate(rt, nxt, at(1, 20)) == STATE_ACTIVE

    def test_actions_without_window(self):
        rt = TaskRuntime()
        evaluate(rt, None, at(0, 10))
        assert not acknowledge(rt)
        assert not snooze(rt, at(0, 10), 5)

    def test_cannot_snooze_done(self):
        rt = TaskRuntime()
        evaluate(rt, self.win, at(0, 20))
        acknowledge(rt)
        assert not snooze(rt, at(0, 20), 5)

    def test_serialization_roundtrip(self):
        rt = TaskRuntime()
        evaluate(rt, self.win, at(0, 20))
        snooze(rt, at(0, 20), 10)
        evaluate(rt, self.win, at(0, 20, 1))
        restored = TaskRuntime.from_dict(rt.as_dict())
        assert restored.snoozed_until == rt.snoozed_until
        assert restored.state == STATE_SNOOZED
        assert evaluate(restored, self.win, at(0, 20, 5)) == STATE_SNOOZED
