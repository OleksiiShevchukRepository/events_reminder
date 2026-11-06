"""Steps of the guided flows."""

from aiogram.fsm.state import State, StatesGroup


class CreateFlow(StatesGroup):
    text = State()
    recurrence = State()
    interval = State()
    date = State()
    time = State()


class UpdateFlow(StatesGroup):
    text = State()
    recurrence = State()
    interval = State()
    date = State()
    time = State()
    # The time step of a switch to "only once" or "every N days", shown only
    # when the message's existing time would already be past on the new date.
    switch_time = State()
